import asyncio
import time
import config
from datetime import datetime

from utils import shorten_id
from order_manager import cancel_orders, reorder
from subgraph_client import SubgraphClient
from py_clob_client.clob_types import OpenOrderParams, OrderType, OrderArgs
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from logger_config import main_logger


class RiskManager:
    def __init__(self, clob_client: 'ClobClient', subgraph_client: SubgraphClient):
        self.clob_client = clob_client
        self.subgraph_client = subgraph_client
        self.volatility_cooldown = {}
        self.logger = main_logger

        # RiskManager parameters
        self.VOLUME_THRESHOLD = config.RISK_VOLUME_THRESHOLD
        self.VOLATILITY_COOLDOWN_PERIOD = config.RISK_VOLATILITY_COOLDOWN_PERIOD
        self.INACTIVITY_THRESHOLD = config.RISK_INACTIVITY_THRESHOLD
        self.OPEN_INTEREST_THRESHOLD = config.RISK_OPEN_INTEREST_THRESHOLD
        self.HIGH_ACTIVITY_THRESHOLD_PERCENT = config.RISK_HIGH_ACTIVITY_THRESHOLD_PERCENT

    async def monitor_active_orders(self):
        while True:
            open_orders = self.clob_client.get_orders(OpenOrderParams())
            if open_orders is None:
                self.logger.error("Failed to fetch open orders.")
                await asyncio.sleep(config.RISK_FETCH_RETRY_DELAY)
                continue

            unique_token_ids = set(order['asset_id'] for order in open_orders)
            
            for token_id in unique_token_ids:
                raw_order_book = self.clob_client.get_order_book(token_id)
                if raw_order_book:
                    order_book = self.clob_client.parse_orderbook(raw_order_book)
                    await self.check_market_volatility(token_id, order_book)
                    await self.check_filled_orders(token_id, order_book, open_orders)
                    
                    if token_id in self.volatility_cooldown:
                        elapsed = time.time() - self.volatility_cooldown[token_id]
                        if elapsed >= self.VOLATILITY_COOLDOWN_PERIOD:
                            self.logger.info(f"Cooldown expired for {shorten_id(token_id)}. Reordering bids.")
                            await reorder(self.clob_client, token_id, order_book)
                            del self.volatility_cooldown[token_id]
                else:
                    self.logger.error(f"Failed to fetch order book for token_id: {shorten_id(token_id)}")
                await asyncio.sleep(config.RISK_ORDER_BOOK_FETCH_DELAY)

            await asyncio.sleep(config.RISK_MONITOR_INTERVAL)

    async def check_market_volatility(self, token_id: str, order_book: dict):
        if token_id in self.volatility_cooldown:
            elapsed = time.time() - self.volatility_cooldown[token_id]
            if elapsed < self.VOLATILITY_COOLDOWN_PERIOD:
                self.logger.info(f"Cooldown active for {shorten_id(token_id)}. Time left: {self.VOLATILITY_COOLDOWN_PERIOD - elapsed:.2f} seconds")
                return

        sorted_bids = sorted(order_book['bids'], key=lambda x: float(x['price']), reverse=True)
        sorted_asks = sorted(order_book['asks'], key=lambda x: float(x['price']))

        best_bid = float(sorted_bids[0]['price']) if sorted_bids else None
        best_ask = float(sorted_asks[0]['price']) if sorted_asks else None

        if best_bid and best_ask:
            spread = best_ask - best_bid
            self.logger.info(f"Token ID {shorten_id(token_id)} - Spread: {spread}")
            if spread > self.VOLUME_THRESHOLD:
                await self.handle_high_volatility(token_id)

    async def handle_high_volatility(self, token_id: str):
        self.logger.info(f"High volatility detected for token_id {shorten_id(token_id)}. Initiating cancellation of large orders.")
        
        try:
            open_orders = self.clob_client.get_orders(OpenOrderParams(asset_id=token_id))
            if open_orders is None:
                self.logger.error(f"Failed to fetch open orders for token_id {shorten_id(token_id)} during volatility handling.")
                return

            sorted_orders = sorted(open_orders, key=lambda x: float(x['price']), reverse=True)
            best_bid_size = float(sorted_orders[0]['size']) if sorted_orders else 0
            threshold = (self.HIGH_ACTIVITY_THRESHOLD_PERCENT / 100) * best_bid_size

            self.logger.info(f"Best bid size for token_id {shorten_id(token_id)}: {best_bid_size}. Threshold for cancellation: {threshold}")

            orders_to_cancel = [
                order for order in open_orders
                if float(order['size']) > threshold and
                   order.get('owner', '').lower() == self.clob_client.creds.api_key.lower()
            ]

            for order in orders_to_cancel:
                self.logger.info(f"Marking order {shorten_id(order['id'])} for cancellation due to size > {self.HIGH_ACTIVITY_THRESHOLD_PERCENT}% of best bid.")

            if orders_to_cancel:
                cancelled_order_ids = await cancel_orders(self.clob_client, [order['id'] for order in orders_to_cancel], token_id)
                self.logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in cancelled_order_ids]}")

                self.volatility_cooldown[token_id] = time.time()

                for cancelled_order in orders_to_cancel:
                    market_info = await self.fetch_market_info(token_id)
                    await reorder(self.clob_client, cancelled_order, token_id, market_info)
        
        except Exception as e:
            self.logger.error(f"Failed to handle high volatility for token_id {shorten_id(token_id)}: {str(e)}")

    async def check_filled_orders(self, token_id: str, order_book: dict, open_orders: list):
        for order in open_orders:
            if order['asset_id'] == token_id and float(order['size_matched']) > 0:
                await self.handle_filled_order(order, order_book)

    async def handle_filled_order(self, order: dict, order_book: dict):
        sorted_bids = sorted(order_book['bids'], key=lambda x: float(x['price']), reverse=True)
        best_bid = float(sorted_bids[0]['price']) if sorted_bids else None
        
        if best_bid:
            size_to_sell = float(order['size_matched'])
            while size_to_sell > 0:
                sell_order = await self.create_market_sell_order(order['asset_id'], size_to_sell, best_bid)
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
            order_args = OrderArgs(
                price=price,
                size=size,
                side=OrderType.SELL,
                token_id=token_id
            )
            signed_order = self.clob_client.create_order(order_args)
            return self.clob_client.post_order(signed_order, OrderType.GTC)
        except Exception as e:
            self.logger.error(f"Failed to create market sell order: {str(e)}")
            return None

    async def fetch_market_info(self, market_id: str) -> dict:
        try:
            market_info = await self.subgraph_client.get_market_info(market_id)
            return market_info
        except Exception as e:
            self.logger.error(f"Failed to fetch market info for {market_id}: {e}")
            return {}

    async def start_core_risk_management(self, market_ids: list, user_addresses: list):
        asyncio.create_task(self.monitor_active_orders())

        while True:
            for market_id in market_ids:
                raw_order_book = self.clob_client.get_order_book(token_id=market_id)
                if raw_order_book:
                    order_book = self.clob_client.parse_orderbook(raw_order_book)
                    await self.check_market_volatility(market_id, order_book)
                else:
                    self.logger.error(f"Failed to fetch order book for market_id: {shorten_id(market_id)}")
                
            await asyncio.sleep(config.RISK_CORE_MANAGEMENT_INTERVAL)

async def main():

    subgraph_client = SubgraphClient(config.SUBGRAPH_URL)

    clob_client = ClobClient(
        host=config.POLYMARKET_HOST,
        chain_id=config.CHAIN_ID,
        key=config.PRIVATE_KEY,
        signature_type=2,
        funder=config.POLYMARKET_PROXY_ADDRESS
    )
    api_creds = ApiCreds(
        api_key=config.POLY_API_KEY,
        api_secret=config.POLY_API_SECRET,
        api_passphrase=config.POLY_PASSPHRASE
    )
    clob_client.set_api_creds(api_creds)

    risk_manager = RiskManager(clob_client, subgraph_client)

    market_ids = config.MARKET_IDS
    user_addresses = config.USER_ADDRESSES

    await risk_manager.start_core_risk_management(market_ids, user_addresses)

if __name__ == "__main__":
    asyncio.run(main())

