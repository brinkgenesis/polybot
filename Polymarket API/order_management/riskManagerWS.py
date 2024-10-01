import logging
import threading
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
import time
import os
import json
from clob_client.clob_websocket_client import ClobWebSocketClient
from py_clob_client.client import ClobClient, OpenOrderParams
from utils.utils import shorten_id
from decimal import Decimal
import math
from threading import Lock, Event

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
        self.ws_client: ClobWebSocketClient = None
        self.lock = Lock()
        self.ws_initialized = Event()
        
        # Initialize class-specific logger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        if not self.logger.hasHandlers():
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def handle_message(self, data: Dict[str, Any]):
        """
        Handle incoming WebSocket messages.

        Args:
            data (Dict[str, Any]): The message data received from the WebSocket.
        """
        self.logger.debug(f"Received message: {data}")  # Log all incoming messages

        event_type = data.get('event_type')
        if not event_type:
            self.logger.warning("Received message without 'event_type'.")
            return

        self.logger.debug(f"Handling event type: {event_type}")

        if event_type == 'price_change':
            self.handle_price_change(data)
        elif event_type == 'book':
            self.handle_book_event(data)
        elif event_type == 'error':  # Example: handle error messages from server
            error_message = data.get('message', 'Unknown error')
            self.logger.error(f"Received error from server: {error_message}")
        else:
            self.logger.warning(f"Unhandled event type: {event_type}")

    def handle_price_change(self, data: Dict[str, Any]):
        """
        Handle 'price_change' event messages.

        Args:
            data (Dict[str, Any]): The message data received from the WebSocket.
        """
        try:
            asset_id = data.get("asset_id")
            new_price = float(data.get("new_price"))
            timestamp = data.get("timestamp")

            self.logger.info(f"Price Change - Asset ID: {asset_id}, New Price: {new_price}, Timestamp: {timestamp}")
            # Implement your business logic here, e.g., updating internal state, triggering orders, etc.

        except Exception as e:
            self.logger.error(f"Error handling price change event: {e}", exc_info=True)

    def handle_book_event(self, data: Dict[str, Any]):
        """
        Handle 'book' event messages.

        Args:
            data (Dict[str, Any]): The message data received from the WebSocket.
        """
        try:
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

        except Exception as e:
            self.logger.error(f"Error handling book event: {e}", exc_info=True)

    def fetch_open_orders(self):
        try:
            self.logger.info("Fetching open orders...")
            # Replace with the actual synchronous API call
            open_orders = self.client.get_orders()  # Ensure this is a synchronous method
            self.logger.debug(f"Open orders fetched: {json.dumps(open_orders, indent=2)}")
            
            # Ensure open_orders is a list
            if not isinstance(open_orders, list):
                self.logger.error("Unexpected data format for open orders.")
                self.asset_ids = set()
                return

            # Extract asset_ids
            asset_ids = set()
            for order in open_orders:
                asset_id = order.get('asset_id')
                if asset_id:
                    asset_ids.add(asset_id)
                else:
                    self.logger.warning(f"Order without asset_id encountered: {order}")
            
            self.asset_ids = asset_ids
            self.logger.info(f"Fetched {len(self.asset_ids)} unique asset_ids from open orders.")
        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}", exc_info=True)
            self.asset_ids = set()

      

    def subscribe_assets_in_batches(self, batch_size: int = 5):
        # Wait until WebSocket client is initialized
        if not self.ws_initialized.wait(timeout=15):  # Wait up to 30 seconds
            self.logger.error("WebSocket client initialization timed out. Cannot subscribe to assets.")
            return

        asset_ids = list(self.asset_ids)
        total_assets = len(asset_ids)
        batches = math.ceil(total_assets / batch_size)

        self.logger.debug(f"Total assets: {total_assets}, Batch size: {batch_size}, Total batches: {batches}")

        for i in range(batches):
            batch = asset_ids[i*batch_size : (i+1)*batch_size]
            self.logger.debug(f"Processing batch {i+1}/{batches}: {batch}")
            try:
                subscription_payload = {
                    "asset_ids": batch,
                    "type": "Market"
                }
                if self.ws_client and self.ws_client.ws and self.ws_client.ws.sock and self.ws_client.ws.sock.connected:
                    self.ws_client.ws.send(json.dumps(subscription_payload))
                    self.logger.info(f"Subscribed to assets batch {i+1}/{batches}: {batch}")
                    time.sleep(1)  # Small delay between batches to avoid rate limits
                else:
                    self.logger.error("WebSocket client is not connected. Cannot subscribe.")
            except Exception as e:
                self.logger.error(f"Failed to subscribe to assets batch {i+1}/{batches}: {e}", exc_info=True)

    """def reorder(self, asset_id: str):
        try:
            # Fetch market info
            market_info = self.client.get_market_info(asset_id)  # Ensure synchronous
            best_bid = float(market_info['best_bid'])
            best_ask = float(market_info['best_ask'])
            tick_size = float(market_info['tick_size'])
            max_incentive_spread = float(market_info['max_incentive_spread'])

            self.logger.info(f"Market info for token {shorten_id(asset_id)}: Best Bid={best_bid}, Best Ask={best_ask}, Tick Size={tick_size}, Max Incentive Spread={max_incentive_spread}")

            # Example reorder logic
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
                self.logger.info(f"Placed reorder (30%) for token {shorten_id(asset_id)} at price {maker_amount_30}")
            else:
                self.logger.error(f"Failed to place reorder (30%) for token {shorten_id(asset_id)}: {result_30}")

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
                self.logger.info(f"Placed reorder (70%) for token {shorten_id(asset_id)} at price {maker_amount_70}")
            else:
                self.logger.error(f"Failed to place reorder (70%) for token {shorten_id(asset_id)}: {result_70}")

        except Exception as e:
            self.logger.error(f"Error during reorder for token {shorten_id(asset_id)}: {e}", exc_info=True)
"""
    def subscribe_new_asset(self, asset_id: str):
        try:
            subscription_payload = {
                "auth": None,
                "asset_ids": [asset_id],
                "type": "Market"
            }
            with self.lock:
                if self.ws_client and self.ws_client.ws:
                    self.ws_client.ws.send(json.dumps(subscription_payload))
                    self.logger.info(f"Subscribed to new asset: {shorten_id(asset_id)}")
                else:
                    self.logger.error("WebSocket client is not initialized. Cannot subscribe to new asset.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to new asset {shorten_id(asset_id)}: {e}", exc_info=True)

    def connect_websocket(self):
        if not self.ws_client:
            self.ws_client = ClobWebSocketClient(
                ws_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
                message_handler=self.handle_message
            )
            self.logger.info("Initialized ClobWebSocketClient.")
            # Start WebSocket client in the same thread
            try:
                self.ws_client.run_sync()
            except Exception as e:
                self.logger.error(f"WebSocket client encountered an error: {e}", exc_info=True)
        self.ws_initialized.set()  # Signal that WebSocket is initialized

    def monitor_trades(self):
        self.connect_websocket()

    def check_cooldown_tokens(self):
        now = datetime.now(timezone.utc)
        with self.lock:
            for asset_id, cooldown_time in list(self.cooldown_tokens.items()):
                if cooldown_time <= now:
                    self.logger.info(f"Cooldown ended for token {shorten_id(asset_id)}. Adding back to monitoring.")
                    self.asset_ids.add(asset_id)
                    del self.cooldown_tokens[asset_id]
                    if self.ws_client:
                        self.ws_client.asset_ids.add(asset_id)
                        self.subscribe_new_asset(asset_id)

    def run(self):
        self.fetch_open_orders()

        if not self.asset_ids:
            self.logger.warning("No token IDs found in open orders. Exiting RiskManagerWS.")
            return

        # Start websocket client in a separate thread
        websocket_thread = threading.Thread(target=self.monitor_trades, daemon=True)
        websocket_thread.start()

        # Start periodic cooldown checks in a separate thread
        cooldown_thread = threading.Thread(target=self.periodic_cooldown_checks, daemon=True)
        cooldown_thread.start()

        # Keep the main thread alive to allow daemon threads to run
        try:
            while not self.ws_initialized.is_set():
                self.logger.debug("Waiting for WebSocket to initialize...")
                time.sleep(0.5)
            self.logger.debug("WebSocket initialized. Proceeding with subscription.")
            # Now that WebSocket is initialized, proceed with subscriptions
            self.subscribe_assets_in_batches(batch_size=5)  # Adjust batch size as per API limits
            while True:
               #missing code here
                time.sleep(1) #while true for messaging handling
                self.handle_message()
        except KeyboardInterrupt:
            self.logger.info("Shutting down RiskManagerWS...")
            if self.ws_client:
                self.ws_client.disconnect()
            self.logger.info("RiskManagerWS shutdown complete.")

    def periodic_cooldown_checks(self):
        try:
            while True:
                self.check_cooldown_tokens()
                time.sleep(60)
        except Exception as e:
            self.logger.error(f"Error in periodic cooldown checks: {e}", exc_info=True)

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
    try:
        risk_manager.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Exiting.")

if __name__ == "__main__":
    main()