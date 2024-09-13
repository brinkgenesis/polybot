import asyncio
from typing import List, Dict
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import BookParams, OrderType, Side, OpenOrderParams, OrderArgs
from py_clob_client.utilities import parse_raw_orderbook_summary
from decimal import Decimal
import logging
from utils import shorten_id
import os
import time
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from gql.transport.websockets import WebsocketsTransport
from functools import lru_cache
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SubgraphClient:
    def __init__(self, url):
        transport = WebsocketsTransport(url=url)
        self.client = Client(transport=transport, fetch_schema_from_transport=True)
        self.logger = logging.getLogger(__name__)

    async def subscribe_to_trades(self, market_id):
        subscription = gql('''
        subscription onTrade($market: String!) {
          trades(
            where: { market: $market }
            orderBy: timestamp
            orderDirection: asc
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        async for result in self.client.subscribe(subscription, variable_values={"market": market_id}):
            yield result['trades']

    async def get_recent_trades(self, market_id, limit=100):
        query = gql('''
        query getRecentTrades($market: String!, $limit: Int!) {
          trades(
            where: { market: $market }
            orderBy: timestamp
            orderDirection: desc
            first: $limit
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        
        variables = {"market": market_id, "limit": limit}
        result = await self.client.execute_async(query, variable_values=variables)
        return result['trades']

    async def get_market_info(self, market_id):
        query = gql('''
        query getMarketInfo($id: ID!) {
          market(id: $id) {
            id
            question
            outcomeSlots
            lastActiveTimestamp
            totalVolume
            openInterest
          }
        }
        ''')
        
        variables = {"id": market_id}
        result = await self.client.execute_async(query, variable_values=variables)
        return result['market']

    async def get_market_metrics(self, market_id):
        query = gql('''
        query getMarketMetrics($id: ID!) {
          market(id: $id) {
            id
            totalVolume
            openInterest
            lastActiveTimestamp
            liquidity
          }
        }
        ''')
        
        variables = {"id": market_id}
        result = await self.client.execute_async(query, variable_values=variables)
        return result['market']

    async def get_historical_trades(self, market_id: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict]:
        query = gql('''
        query getHistoricalTrades($market: String!, $startTime: Int!, $endTime: Int!, $limit: Int!) {
          trades(
            where: { 
              market: $market,
              timestamp_gte: $startTime,
              timestamp_lte: $endTime
            }
            orderBy: timestamp
            orderDirection: asc
            first: $limit
          ) {
            id
            timestamp
            type
            outcomeIndex
            amount
            price
          }
        }
        ''')
        variables = {
            "market": market_id,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        try:
            result = await self.client.execute_async(query, variable_values=variables)
            return result['trades']
        except Exception as e:
            self.logger.error(f"Error fetching historical trades for market {market_id}: {e}")
            return []

    async def get_user_activities(self, user_address: str, start_time: int, end_time: int, limit: int = 1000) -> Dict[str, List[Dict]]:
        query = gql('''
        query getUserActivities($user: String!, $startTime: Int!, $endTime: Int!, $limit: Int!) {
          orderPlacements(
            where: {
              user: $user,
              timestamp_gte: $startTime,
              timestamp_lte: $endTime
            }
            orderBy: timestamp
            orderDirection: asc
            first: $limit
          ) {
            id
            timestamp
            market
            type
            size
            price
          }
          orderCancellations(
            where: {
              user: $user,
              timestamp_gte: $startTime,
              timestamp_lte: $endTime
            }
            orderBy: timestamp
            orderDirection: asc
            first: $limit
          ) {
            id
            timestamp
            orderId
          }
        }
        ''')
        variables = {
            "user": user_address,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit
        }
        try:
            result = await self.client.execute_async(query, variable_values=variables)
            return {
                "orderPlacements": result.get('orderPlacements', []),
                "orderCancellations": result.get('orderCancellations', [])
            }
        except Exception as e:
            self.logger.error(f"Error fetching user activities for {user_address}: {e}")
            return {}

    async def get_aggregated_metrics(self, market_id: str) -> Dict[str, float]:
        query = gql('''
        query getAggregatedMetrics($market: String!) {
          market(id: $market) {
            id
            totalVolume
            openInterest
            liquidity
          }
        }
        ''')
        variables = {
            "market": market_id
        }
        try:
            result = await self.client.execute_async(query, variable_values=variables)
            market = result.get('market', {})
            return {
                "totalVolume": float(market.get('totalVolume', 0)),
                "openInterest": float(market.get('openInterest', 0)),
                "liquidity": float(market.get('liquidity', 0))
            }
        except Exception as e:
            self.logger.error(f"Error fetching aggregated metrics for market {market_id}: {e}")
            return {}

    async def subscribe_to_events(self, event_type: str, callback, **filters):
        """
        Generic subscription method for different event types.
        :param event_type: Type of event to subscribe to ('liquidityChange', 'largeTrade', etc.)
        :param callback: Function to call when an event is received
        :param filters: Additional filters for the subscription
        """
        if event_type == "liquidityChange":
            subscription = gql('''
            subscription onLiquidityChange($market: String!) {
              liquidityChanges(where: { market: $market }) {
                id
                timestamp
                market
                newLiquidity
              }
            }
            ''')
        elif event_type == "largeTrade":
            subscription = gql('''
            subscription onLargeTrade($market: String!, $minAmount: Float!) {
              trades(where: { market: $market, amount_gt: $minAmount }) {
                id
                timestamp
                market
                type
                outcomeIndex
                amount
                price
              }
            }
            ''')
        elif event_type == "protocolUpgrade":
            subscription = gql('''
            subscription onProtocolUpgrade {
              protocolUpgrades {
                id
                timestamp
                description
              }
            }
            ''')
        else:
            self.logger.error(f"Unsupported event type: {event_type}")
            return

        try:
            async for result in self.client.subscribe(subscription, variable_values=filters):
                callback(result)
        except Exception as e:
            self.logger.error(f"Error in event subscription for {event_type}: {e}")

class RiskManager:
    def __init__(self, clob_client, subgraph_client):
        self.clob_client = clob_client
        self.subgraph_client = subgraph_client
        self.volatility_cooldown = {}
        self.VOLUME_THRESHOLD = 1000  # Define an appropriate threshold
        self.VOLATILITY_COOLDOWN_PERIOD = 600  # 10 minutes in seconds
        self.INACTIVITY_THRESHOLD = 86400  # 1 day in seconds
        self.OPEN_INTEREST_THRESHOLD = 1000000  # Define an appropriate threshold
        self.logger = logging.getLogger(__name__)

    @lru_cache(maxsize=128)
    async def get_cached_market_info(self, market_id):
        return await self.subgraph_client.get_market_info(market_id)

    async def fetch_market_info(self, market_id):
        try:
            market_info = await self.get_cached_market_info(market_id)
            return market_info
        except Exception as e:
            self.logger.error(f"Failed to fetch market info for {market_id}: {e}")
            # Implement retry logic or fallback mechanisms here
            return None
    
    async def monitor_active_orders(self):
        while True:
            open_orders = self.clob_client.get_orders(OpenOrderParams())
            unique_token_ids = set(order['asset_id'] for order in open_orders)
            
            for token_id in unique_token_ids:
                await self.check_market_activity(token_id)
                await self.check_all_active_orders(token_id)
                await asyncio.sleep(60)  # Check every minute

    async def check_all_active_orders(self, token_id):
        open_orders = self.clob_client.get_orders(OpenOrderParams(asset_id=token_id))
        unique_token_ids = set(order['asset_id'] for order in open_orders)
        
        for token_id in unique_token_ids:
            raw_order_book = self.clob_client.get_order_book(token_id)
            if raw_order_book:
                order_book = parse_raw_orderbook_summary(raw_order_book)
                await self.check_market_volatility(token_id, order_book)
                await self.check_filled_orders(token_id, order_book, open_orders)

    async def check_market_volatility(self, token_id: str, order_book: Dict):
        if token_id in self.volatility_cooldown:
            if time.time() - self.volatility_cooldown[token_id] < self.VOLATILITY_COOLDOWN_PERIOD:
                return

        # Sort bids in descending order and asks in ascending order
        sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
        sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price))

        best_bid = float(sorted_bids[0].price) if sorted_bids else None
        best_ask = float(sorted_asks[0].price) if sorted_asks else None

        if best_bid and best_ask:
            spread = best_ask - best_bid
            if spread > self.VOLUME_THRESHOLD:
                await self.handle_high_volatility(token_id)

    async def handle_high_volatility(self, token_id: str):
        open_orders = self.clob_client.get_orders(OpenOrderParams(asset_id=token_id))
        for order in open_orders:
            await self.cancel_order(order['id'])

        self.volatility_cooldown[token_id] = time.time()
        self.logger.info(f"High volatility detected for market {shorten_id(token_id)}. Orders cancelled and cooldown set.")

    async def check_filled_orders(self, token_id: str, order_book: Dict, open_orders: List[Dict]):
        for order in open_orders:
            if order['asset_id'] == token_id and float(order['size_matched']) > 0:
                await self.handle_filled_order(order, order_book)

    async def handle_filled_order(self, order: Dict, order_book: Dict):
        sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
        best_bid = float(sorted_bids[0].price) if sorted_bids else None
        
        if best_bid:
            size_to_sell = float(order['size_matched'])
            while size_to_sell > 0:
                sell_order = await self.create_market_sell_order(
                    order['asset_id'],
                    size_to_sell,
                    best_bid
                )
                if sell_order:
                    size_to_sell -= float(sell_order['size_matched'])
                else:
                    await self.cancel_order(order['id'])
                    break

    async def cancel_order(self, order_id: str):
        try:
            self.clob_client.cancel_order(order_id)
            self.logger.info(f"Order {shorten_id(order_id)} cancelled successfully")
        except Exception as e:
            self.logger.error(f"Failed to cancel order {shorten_id(order_id)}: {str(e)}")

    async def create_market_sell_order(self, token_id: str, size: float, price: float):
        try:
            order_args = {
                'price': price,
                'size': size,
                'side': Side.SELL,
                'token_id': token_id
            }
            signed_order = self.clob_client.create_order(order_args)
            return self.clob_client.post_order(signed_order, OrderType.GTC)
        except Exception as e:
            self.logger.error(f"Failed to create market sell order: {str(e)}")
            return None

    async def check_market_activity(self, token_id):
        recent_trades = await self.subgraph_client.get_recent_trades(token_id)
        market_info = await self.get_cached_market_info(token_id)

        # Check for sudden spikes in trading volume
        total_volume = sum(float(trade['amount']) for trade in recent_trades)
        if total_volume > self.VOLUME_THRESHOLD:
            await self.handle_high_activity(token_id)

        # Check if market has been inactive for a long time
        current_time = int(time.time())
        if current_time - int(market_info['lastActiveTimestamp']) > self.INACTIVITY_THRESHOLD:
            await self.handle_inactive_market(token_id)

        # Check open interest
        if float(market_info['openInterest']) > self.OPEN_INTEREST_THRESHOLD:
            await self.handle_high_open_interest(token_id)

    async def handle_high_activity(self, token_id: str, order_book: Dict):
        best_bid_size = float(order_book.bids[0].size) if order_book.bids else 0
        threshold = 0.5 * best_bid_size  # 50% of best bid size
        self.logger.info(f"Handling high activity for token_id {shorten_id(token_id)}")

        open_orders = self.clob_client.get_orders(OpenOrderParams(asset_id=token_id))
        orders_to_cancel = []

        for order in open_orders:
            order_size = float(order['size'])
            # Assuming 'owner' field identifies your orders
            if order_size > threshold and order['owner'].lower() == self.clob_client.creds.api_key.lower():
                orders_to_cancel.append(order['id'])
                self.logger.info(f"Marking order {shorten_id(order['id'])} for cancellation due to high activity.")

        if orders_to_cancel:
            try:
                self.clob_client.cancel_orders(orders_to_cancel)
                self.logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")
                # Set cooldown to wait for market stabilization
                self.volatility_cooldown[token_id] = time.time()
            except Exception as e:
                self.logger.error(f"Failed to cancel orders for high activity: {str(e)}")
        
        # Optional: Trigger reordering after cooldown in the main monitoring loop

    async def handle_inactive_market(self, token_id):
        # Implement logic to handle inactive markets
        # For example, you might want to cancel orders in these markets
        pass

    async def handle_high_open_interest(self, token_id):
        # Implement logic to handle markets with high open interest
        # For example, you might want to reduce exposure in these markets
        pass

    async def analyze_historical_trends(self, market_id: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        trades = await self.subgraph_client.get_historical_trades(market_id, start_time, end_time)
        if not trades:
            self.logger.warning(f"No historical trades found for market {shorten_id(market_id)}.")
            return

        # Example: Calculate total volume and average price
        total_volume = sum(float(trade['amount']) for trade in trades)
        average_price = sum(float(trade['price']) for trade in trades) / len(trades)

        self.logger.info(f"Market {shorten_id(market_id)} - Total Volume (7d): {total_volume}")
        self.logger.info(f"Market {shorten_id(market_id)} - Average Price (7d): {average_price:.4f}")

        # Further trend analysis can be implemented here

    async def monitor_user_activities(self, user_address: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 24 * 3600  # Past 24 hours

        activities = await self.subgraph_client.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        self.logger.info(f"User {shorten_id(user_address)} - Orders Placed (24h): {len(placements)}")
        self.logger.info(f"User {shorten_id(user_address)} - Orders Canceled (24h): {len(cancellations)}")

        # Example: Flag if user cancels more than a threshold number of orders
        CANCEL_THRESHOLD = 10
        if len(cancellations) > CANCEL_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded cancellation threshold with {len(cancellations)} cancellations.")
            # Implement further actions like alerting or restricting activities

    async def collect_aggregate_metrics(self, market_id: str):
        metrics = await self.subgraph_client.get_aggregated_metrics(market_id)
        if not metrics:
            self.logger.warning(f"No aggregated metrics found for market {shorten_id(market_id)}.")
            return

        self.logger.info(f"Market {shorten_id(market_id)} - Total Volume: {metrics['totalVolume']}")
        self.logger.info(f"Market {shorten_id(market_id)} - Open Interest: {metrics['openInterest']}")
        self.logger.info(f"Market {shorten_id(market_id)} - Liquidity: {metrics['liquidity']}")

        # Example: Flag markets with low liquidity
        LIQUIDITY_THRESHOLD = 5000
        if metrics['liquidity'] < LIQUIDITY_THRESHOLD:
            self.logger.warning(f"Market {shorten_id(market_id)} liquidity below threshold: {metrics['liquidity']}")
            # Implement further actions like adjusting order sizes or alerting

    def handle_liquidity_change(self, event: Dict):
        market_id = event['market']
        new_liquidity = float(event['newLiquidity'])
        self.logger.info(f"Liquidity Change Detected for Market {shorten_id(market_id)}: New Liquidity = {new_liquidity}")

        # Example: Adjust order sizes based on liquidity
        LIQUIDITY_THRESHOLD = 5000
        if new_liquidity < LIQUIDITY_THRESHOLD:
            self.logger.warning(f"Market {shorten_id(market_id)} liquidity below threshold: {new_liquidity}")
            # Implement actions like reducing exposure or alerting

    def handle_large_trade(self, event: Dict):
        trade_id = event['id']
        market_id = event['market']
        amount = float(event['amount'])
        price = float(event['price'])
        self.logger.info(f"Large Trade Detected: Trade ID {shorten_id(trade_id)}, Market {shorten_id(market_id)}, Amount {amount}, Price {price}")

        # Example: Flag large trades for further analysis
        LARGE_TRADE_THRESHOLD = 10000
        if amount > LARGE_TRADE_THRESHOLD:
            self.logger.warning(f"Trade {shorten_id(trade_id)} exceeds large trade threshold with amount {amount}")
            # Implement actions like pausing trading or notifying stakeholders

    def handle_protocol_upgrade(self, event: Dict):
        upgrade_id = event['id']
        description = event['description']
        timestamp = datetime.utcfromtimestamp(event['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        self.logger.info(f"Protocol Upgrade Detected: Upgrade ID {shorten_id(upgrade_id)}, Description: {description}, Timestamp: {timestamp}")

        # Example: Implement necessary adjustments post-upgrade
        # This could include refreshing connections, updating configurations, etc.

    async def start_event_subscriptions(self, market_id: str):
        # Subscribe to liquidity changes
        asyncio.create_task(
            self.subgraph_client.subscribe_to_events(
                event_type="liquidityChange",
                callback=self.handle_liquidity_change,
                market=market_id
            )
        )

        # Subscribe to large trades
        LARGE_TRADE_MIN_AMOUNT = 10000  # Define an appropriate threshold
        asyncio.create_task(
            self.subgraph_client.subscribe_to_events(
                event_type="largeTrade",
                callback=self.handle_large_trade,
                market=market_id,
                minAmount=LARGE_TRADE_MIN_AMOUNT
            )
        )

        # Subscribe to protocol upgrades
        asyncio.create_task(
            self.subgraph_client.subscribe_to_events(
                event_type="protocolUpgrade",
                callback=self.handle_protocol_upgrade
            )
        )

    async def analyze_user_metrics(self, user_address: str):
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 7 * 24 * 3600  # Past 7 days

        activities = await self.subgraph_client.get_user_activities(user_address, start_time, end_time)
        if not activities:
            self.logger.warning(f"No activities found for user {user_address}.")
            return

        placements = activities.get('orderPlacements', [])
        cancellations = activities.get('orderCancellations', [])

        # Calculate metrics
        total_orders = len(placements)
        total_cancellations = len(cancellations)
        total_volume = sum(float(order['size']) for order in placements)
        avg_order_size = total_volume / total_orders if total_orders > 0 else 0

        self.logger.info(f"User {shorten_id(user_address)} Metrics (7d):")
        self.logger.info(f"  Total Orders Placed: {total_orders}")
        self.logger.info(f"  Total Cancellations: {total_cancellations}")
        self.logger.info(f"  Total Volume: {total_volume}")
        self.logger.info(f"  Average Order Size: {avg_order_size:.2f}")

        # Define risk thresholds
        ORDER_THRESHOLD = 100  # Max orders in 7 days
        CANCELLATION_THRESHOLD = 20  # Max cancellations in 7 days
        VOLUME_THRESHOLD = 50000  # Max total volume
        AVG_ORDER_SIZE_THRESHOLD = 1000  # Max average order size

        # Flag users exceeding thresholds
        if total_orders > ORDER_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded order placement threshold with {total_orders} orders.")
            # Implement actions like flagging, auditing, or restricting

        if total_cancellations > CANCELLATION_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded cancellation threshold with {total_cancellations} cancellations.")
            # Implement actions like flagging, auditing, or restricting

        if total_volume > VOLUME_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded total volume threshold with volume {total_volume}.")
            # Implement actions like flagging, auditing, or restricting

        if avg_order_size > AVG_ORDER_SIZE_THRESHOLD:
            self.logger.warning(f"User {shorten_id(user_address)} exceeded average order size threshold with average size {avg_order_size}.")
            # Implement actions like flagging, auditing, or restricting

    async def straddle_midpoint(self, market_id: str):
        # Fetch current order book
        order_book = self.clob_client.get_order_book(market_id)
        if not order_book or not order_book.bids or not order_book.asks:
            self.logger.error(f"Order book data missing for market {shorten_id(market_id)}. Cannot straddle midpoint.")
            return

        # Determine best bid and ask
        best_bid = float(order_book.bids[0].price)
        best_ask = float(order_book.asks[0].price)
        midpoint = (best_bid + best_ask) / 2

        self.logger.info(f"Market {shorten_id(market_id)} - Best Bid: {best_bid}, Best Ask: {best_ask}, Midpoint: {midpoint}")

        # Define price offsets for straddling
        BUY_OFFSET = 0.01  # Place buy order slightly below midpoint
        SELL_OFFSET = 0.01  # Place sell order slightly above midpoint

        buy_price = midpoint - BUY_OFFSET
        sell_price = midpoint + SELL_OFFSET

        # Define order sizes based on historical volatility or aggregate metrics
        order_size = self.determine_order_size(market_id)

        # Build and place buy order
        buy_order = self.clob_client.create_order(
            OrderArgs(
                token_id=market_id,
                price=buy_price,
                size=order_size,
                side="BUY"
            )
        )
        self.clob_client.post_order(buy_order, OrderType.GTC)
        self.logger.info(f"Placed BUY order at {buy_price} with size {order_size} for market {shorten_id(market_id)}.")

        # Build and place sell order
        sell_order = self.clob_client.create_order(
            OrderArgs(
                token_id=market_id,
                price=sell_price,
                size=order_size,
                side="SELL"
            )
        )
        self.clob_client.post_order(sell_order, OrderType.GTC)
        self.logger.info(f"Placed SELL order at {sell_price} with size {order_size} for market {shorten_id(market_id)}.")

    def determine_order_size(self, market_id: str) -> float:
        """
        Determine the size of the order based on historical volatility and aggregate metrics.
        """
        # Fetch aggregate metrics
        metrics = asyncio.run(self.subgraph_client.get_aggregated_metrics(market_id))
        if not metrics:
            self.logger.warning(f"Using default order size for market {shorten_id(market_id)} due to missing metrics.")
            return 10.0  # Default size

        volatility = self.calculate_volatility(market_id)
        liquidity = metrics.get('liquidity', 0)

        # Example logic: larger order sizes for higher liquidity and lower volatility
        base_size = 10.0
        size = base_size * (liquidity / 10000) * (1 / (volatility + 1))

        self.logger.info(f"Determined order size for market {shorten_id(market_id)}: {size:.2f}")
        return size

    def calculate_volatility(self, market_id: str) -> float:
        """
        Calculate volatility based on historical trades.
        """
        # Example: Simple standard deviation of trade prices over the past day
        end_time = int(datetime.utcnow().timestamp())
        start_time = end_time - 24 * 3600  # Past 24 hours

        trades = asyncio.run(self.subgraph_client.get_historical_trades(market_id, start_time, end_time))
        if not trades:
            self.logger.warning(f"No trades data available for volatility calculation for market {shorten_id(market_id)}.")
            return 0.0

        prices = [float(trade['price']) for trade in trades]
        mean_price = sum(prices) / len(prices)
        variance = sum((price - mean_price) ** 2 for price in prices) / len(prices)
        volatility = variance ** 0.5

        self.logger.info(f"Calculated volatility for market {shorten_id(market_id)}: {volatility:.4f}")
        return volatility

async def main():
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)

    # Initialize SubgraphClient with WebSocket URL for subscriptions
    subgraph_url = 'wss://api.thegraph.com/subgraphs/name/polymarket/matic-markets'
    subgraph_client = SubgraphClient(subgraph_url)

    # Initialize ClobClient with necessary credentials from environment
    clob_client = ClobClient(
        host=os.getenv("POLYMARKET_HOST"),
        chain_id=int(os.getenv("CHAIN_ID")),
        key=os.getenv("PRIVATE_KEY"),
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
    )
    api_creds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_API_SECRET"),
        api_passphrase=os.getenv("POLY_PASSPHRASE")
    )
    clob_client.set_api_creds(api_creds)

    # Initialize RiskManager
    risk_manager = RiskManager(clob_client, subgraph_client)

    # List of markets to manage
    market_ids = ["0xMarketId1", "0xMarketId2"]  # Replace with actual market IDs

    # Start event subscriptions for each market
    for market_id in market_ids:
        await risk_manager.start_event_subscriptions(market_id)

    # Periodically perform risk assessments
    while True:
        for market_id in market_ids:
            await risk_manager.analyze_historical_trends(market_id)
            await risk_manager.collect_aggregate_metrics(market_id)
            await risk_manager.straddle_midpoint(market_id)

        # Monitor user activities (extend as needed)
        user_addresses = ["0xUserAddress1", "0xUserAddress2"]  # Replace with actual user addresses
        for user_address in user_addresses:
            await risk_manager.monitor_user_activities(user_address)
            await risk_manager.analyze_user_metrics(user_address)

        # Sleep for a defined interval before next assessment
        await asyncio.sleep(3600)  # Wait for 1 hour

if __name__ == "__main__":
    asyncio.run(main())
