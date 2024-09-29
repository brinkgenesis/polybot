import logging
import asyncio
import threading
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
import time
import ssl
import certifi
import os
import json
from clob_client.clob_websocket_client import ClobWebSocketClient
from py_clob_client.client import ClobClient, OpenOrderParams
from utils.utils import shorten_id
from decimal import Decimal

from order_management.limitOrder import build_order, execute_order  # Import existing order functions

# Load environment variables (assuming using python-dotenv)
API_KEY = os.getenv("POLY_API_KEY")
API_SECRET = os.getenv("POLY_API_SECRET")
API_PASSPHRASE = os.getenv("POLY_PASSPHRASE")
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
CHAIN_ID = int(os.getenv("CHAIN_ID"))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Configure logging format if not already done
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

class RiskManagerWS:
    def __init__(self, client: ClobClient):
        self.client = client
        self.asset_ids = set()
        self.cooldown_tokens: Dict[str, datetime] = {}
        self.cooldown_duration = timedelta(minutes=10)
        self.token_event_amounts: Dict[str, float] = {}
        self.token_event_timestamps: Dict[str, datetime] = {}
        self.ws_client: ClobWebSocketClient = None  # Will be initialized after fetching asset IDs

    def fetch_open_orders(self):
        """
        Fetch open orders and extract unique asset_ids.
        """
        try:
            all_open_orders = []
            for asset_id in self.asset_ids:
                open_orders = self.client.get_orders(OpenOrderParams(asset_id=asset_id))
                all_open_orders.extend(open_orders)
            
            # Update asset_ids based on fetched orders
            self.asset_ids = {order['asset_id'] for order in all_open_orders}
            logger.info(f"Fetched {len(self.asset_ids)} unique asset_ids from open orders.")
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}", exc_info=True)

    async def handle_message(self, data: Dict[str, Any]):
        event_type = data.get('event_type')

        if event_type == 'price_change':
            await self.handle_price_change(data)
        elif event_type == 'book':
            await self.handle_book_event(data)
        else:
            logger.warning(f"Unhandled event type: {event_type}")

    async def handle_price_change(self, data: Dict[str, Any]):
        asset_id = data.get('asset_id')
        side = data.get('side')
        price = float(data.get('price', 0))
        size = float(data.get('size', 0))
        timestamp_ms = int(data.get('timestamp', 0))
        timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)

        amount = price * size

        if side.lower() == 'sell' and asset_id in self.asset_ids:
            logger.info(f"Received price_change for token {shorten_id(asset_id)}: Side={side}, Price={price}, Size={size}, Amount={amount}")

            # Update the total amount and timestamps for the asset_id
            if asset_id not in self.token_event_amounts:
                self.token_event_amounts[asset_id] = amount
                self.token_event_timestamps[asset_id] = timestamp
            else:
                time_diff = (timestamp - self.token_event_timestamps[asset_id]).total_seconds()
                if time_diff <= 5:
                    self.token_event_amounts[asset_id] += amount
                else:
                    self.token_event_amounts[asset_id] = amount
                    self.token_event_timestamps[asset_id] = timestamp

            # Check if amount exceeds $500 in a single transaction or within 5 seconds
            if amount >= 500 or self.token_event_amounts[asset_id] >= 500:
                logger.info(f"Threshold exceeded for token {shorten_id(asset_id)}. Cancelling orders.")
                await self.cancel_and_reorder(asset_id)

    async def handle_book_event(self, data: Dict[str, Any]):
        """
        Handle 'book' event messages.
        Currently, this method can be extended based on requirements.
        """
        asset_id = data.get("asset_id")
        market = data.get("market")
        timestamp = data.get("timestamp")
        buys = data.get("buys", [])
        sells = data.get("sells", [])
        hash_summary = data.get("hash")
        
        self.logger.info(f"Book Update for Market: {market} | Asset ID: {asset_id} | Timestamp: {timestamp}")
        self.logger.debug(f"Buys: {buys}")
        self.logger.debug(f"Sells: {sells}")
        self.logger.debug(f"Hash: {hash_summary}")
        # Implement further processing as needed

    async def cancel_and_reorder(self, asset_id: str):
        """
        Cancel existing orders for the given asset_id and place new ones.
        """
        try:
            # Cancel all orders for this asset_id
            open_orders = self.client.get_orders(OpenOrderParams(asset_id=asset_id))
            orders_to_cancel = [order['id'] for order in open_orders if order['asset_id'] == asset_id]
            if orders_to_cancel:
                cancel_response = self.client.cancel_orders(orders_to_cancel)
                logger.info(f"Cancelled orders for asset {shorten_id(asset_id)}: {orders_to_cancel}")
            else:
                logger.info(f"No orders to cancel for asset {shorten_id(asset_id)}.")

            # Reorder
            await self.reorder(asset_id)

        except Exception as e:
            logger.error(f"Failed during cancel and reorder for asset {shorten_id(asset_id)}: {e}", exc_info=True)


    async def reorder(self, asset_id: str):
        # Fetch market info
        try:
            market_info = self.client.get_market_info(asset_id)
            best_bid = float(market_info['best_bid'])
            best_ask = float(market_info['best_ask'])
            tick_size = float(market_info['tick_size'])
            max_incentive_spread = float(market_info['max_incentive_spread'])

            logger.info(f"Market info for token {shorten_id(asset_id)}: Best Bid={best_bid}, Best Ask={best_ask}, Tick Size={tick_size}, Max Incentive Spread={max_incentive_spread}")
        except Exception as e:
            logger.error(f"Error fetching market info for token {shorten_id(asset_id)}: {e}", exc_info=True)
            return

        # Build orders
        try:
            side = 'BUY'  # Adjust side as needed based on your strategy
            order_value = 500  # Total value to allocate

            order_size_30 = (order_value * 0.3) / best_bid  # 30% of $500
            order_size_70 = (order_value * 0.7) / best_bid  # 70% of $500

            maker_price_30 = best_bid - tick_size  # Adjust price as per tick_size
            maker_amount_30 = maker_price_30

            maker_price_70 = best_bid - (tick_size * 2)  # Further adjust if needed
            maker_amount_70 = maker_price_70

            # Build and execute 30% order
            signed_order_30 = build_order(
                self.client,
                asset_id,
                Decimal(str(order_size_30)),
                Decimal(str(maker_amount_30)),
                side
            )
            success_30, result_30 = execute_order(self.client, signed_order_30)
            if success_30:
                logger.info(f"Placed reorder (30%) for token {shorten_id(asset_id)} at price {maker_amount_30}")
            else:
                logger.error(f"Failed to place reorder (30%) for token {shorten_id(asset_id)}: {result_30}")

            # Build and execute 70% order
            signed_order_70 = build_order(
                self.client,
                asset_id,
                Decimal(str(order_size_70)),
                Decimal(str(maker_amount_70)),
                side
            )
            success_70, result_70 = execute_order(self.client, signed_order_70)
            if success_70:
                logger.info(f"Placed reorder (70%) for token {shorten_id(asset_id)} at price {maker_amount_70}")
            else:
                logger.error(f"Failed to place reorder (70%) for token {shorten_id(asset_id)}: {result_70}")

        except Exception as e:
            logger.error(f"Error during reorder for token {shorten_id(asset_id)}: {e}", exc_info=True)

    async def subscribe_new_asset(self, asset_id: str):
        """
        Optional: Implement dynamic subscription to a new asset.
        This method can be called when re-adding a token after cooldown.
        """
        try:
            subscription_payload = {
                "asset_ids": [asset_id],  # Use 'asset_ids' with snake_case
                "type": "Market"
            }
            await self.ws_client.connection.send(json.dumps(subscription_payload))
            logger.info(f"Subscribed to new asset: {shorten_id(asset_id)}")
        except Exception as e:
            logger.error(f"Failed to subscribe to new asset {shorten_id(asset_id)}: {e}", exc_info=True)

    async def connect_websocket(self):
        if not self.ws_client:
            self.ws_client = ClobWebSocketClient(
                ws_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
                asset_ids=list(self.asset_ids),
                message_handler=self.handle_message
            )
        try:
            await self.ws_client.run_async()
        except Exception as e:
            logger.error(f"WebSocket client encountered an error: {e}", exc_info=True)

    async def monitor_trades(self):
        await self.connect_websocket()

    def check_cooldown_tokens(self):
        now = datetime.now(timezone.utc)
        for asset_id, cooldown_time in list(self.cooldown_tokens.items()):
            if cooldown_time <= now:
                logger.info(f"Cooldown ended for token {shorten_id(asset_id)}. Adding back to monitoring.")
                self.asset_ids.add(asset_id)
                del self.cooldown_tokens[asset_id]
                # Optionally, resubscribe to the token's events
                if self.ws_client:
                    self.ws_client.asset_ids.append(asset_id)
                    asyncio.run_coroutine_threadsafe(
                        self.subscribe_new_asset(asset_id),
                        asyncio.get_event_loop()
                    )

    def run(self):
        # Fetch open orders and get token IDs
        self.fetch_open_orders()

        if not self.asset_ids:
            logger.warning("No token IDs found in open orders. Exiting RiskManagerWS.")
            return

        # Start the websocket event loop in a separate thread
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_until_complete, args=(self.monitor_trades(),), daemon=True)
        thread.start()

        # Periodically check cooldown tokens
        try:
            while True:
                self.check_cooldown_tokens()
                # Sleep for a minute before checking again
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down RiskManagerWS...")
            # Close websocket connection
            loop.call_soon_threadsafe(loop.stop)
            if self.ws_client and self.ws_client.connection:
                loop.run_until_complete(self.ws_client.disconnect())
            thread.join()
            logger.info("RiskManagerWS shutdown complete.")

def main():
    logging.basicConfig(level=logging.INFO)
    creds = {
        'apiKey': API_KEY,
        'secret': API_SECRET,
        'passphrase': API_PASSPHRASE,
    }
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=POLYMARKET_PROXY_ADDRESS
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    risk_manager = RiskManagerWS(client)
    risk_manager.run()

if __name__ == "__main__":
    main()