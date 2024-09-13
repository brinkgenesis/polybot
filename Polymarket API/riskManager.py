import asyncio
from typing import List, Dict
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import BookParams, OrderType, Side, OpenOrderParams
from py_clob_client.utilities import parse_raw_orderbook_summary
from decimal import Decimal
import logging
from utils import shorten_id
import os
import time
from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SubgraphClient:
    def __init__(self, url):
        transport = RequestsHTTPTransport(url=url)
        self.client = Client(transport=transport, fetch_schema_from_transport=True)

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

class RiskManager:
    def __init__(self, clob_client, subgraph_client):
        self.clob_client = clob_client
        self.subgraph_client = subgraph_client
        self.volatility_cooldown = {}
        self.VOLUME_THRESHOLD = 1000  # Define an appropriate threshold
        self.VOLATILITY_COOLDOWN_PERIOD = 600  # 10 minutes in seconds
        self.INACTIVITY_THRESHOLD = 86400  # 1 day in seconds
        self.OPEN_INTEREST_THRESHOLD = 1000000  # Define an appropriate threshold

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
        logger.info(f"High volatility detected for market {shorten_id(token_id)}. Orders cancelled and cooldown set.")

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
            logger.info(f"Order {shorten_id(order_id)} cancelled successfully")
        except Exception as e:
            logger.error(f"Failed to cancel order {shorten_id(order_id)}: {str(e)}")

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
            logger.error(f"Failed to create market sell order: {str(e)}")
            return None

    async def check_market_activity(self, token_id):
        recent_trades = await self.subgraph_client.get_recent_trades(token_id)
        market_info = await self.subgraph_client.get_market_info(token_id)

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
        logger.info(f"Handling high activity for token_id {shorten_id(token_id)}")

        open_orders = self.clob_client.get_orders(OpenOrderParams(asset_id=token_id))
        orders_to_cancel = []

        for order in open_orders:
            order_size = float(order['size'])
            # Assuming 'owner' field identifies your orders
            if order_size > threshold and order['owner'].lower() == self.clob_client.creds.api_key.lower():
                orders_to_cancel.append(order['id'])
                logger.info(f"Marking order {shorten_id(order['id'])} for cancellation due to high activity.")

        if orders_to_cancel:
            try:
                self.clob_client.cancel_orders(orders_to_cancel)
                logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")
                # Set cooldown to wait for market stabilization
                self.volatility_cooldown[token_id] = time.time()
            except Exception as e:
                logger.error(f"Failed to cancel orders for high activity: {str(e)}")
        
        # Optional: Trigger reordering after cooldown in the main monitoring loop

    async def handle_inactive_market(self, token_id):
        # Implement logic to handle inactive markets
        # For example, you might want to cancel orders in these markets
        pass

    async def handle_high_open_interest(self, token_id):
        # Implement logic to handle markets with high open interest
        # For example, you might want to reduce exposure in these markets
        pass

async def main():
    # Initialize ClobClient here (use the same initialization as in order_manager.py)
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
    
    subgraph_client = SubgraphClient('https://api.thegraph.com/subgraphs/name/polymarket/matic-markets')
    risk_manager = RiskManager(clob_client, subgraph_client)
    await risk_manager.monitor_active_orders()

if __name__ == "__main__":
    asyncio.run(main())
