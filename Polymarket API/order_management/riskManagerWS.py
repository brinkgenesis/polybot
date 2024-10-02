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
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_client = None
        self.is_running = True
        self.lock = threading.Lock()
        self.ws_initialized = threading.Event()
        self.assets_ids = set()

    def handle_book_event(self, data: Dict[str, Any]):
        """
        Handle 'book' event messages.

        Args:
            data (Dict[str, Any]): The message data received from the WebSocket.
        """
        try:
            asset_id = data.get("asset_id")
            if not asset_id:
                self.logger.warning("Received 'book' event without asset_id.")
                return
            # Further processing of the 'book' event
            # ...
        except Exception as e:
            self.logger.error(f"Error handling 'book' event: {e}", exc_info=True)

    def handle_price_change_event(self, data: Dict[str, Any]):
        """
        Handle 'price_change' event messages.

        Args:
            data (Dict[str, Any]): The message data received from the WebSocket.
        """
        try:
            asset_id = data.get("asset_id")
            price = data.get("price")
            if not asset_id or price is None:
                self.logger.warning("Received 'price_change' event with incomplete data.")
                return
            # Implement the logic to handle the price change
            self.logger.info(f"Asset {asset_id} price changed to {price}")
            # Further processing can be added here
        except Exception as e:
            self.logger.error(f"Error handling 'price_change' event: {e}", exc_info=True)

    def fetch_open_orders(self):
        try:
            self.logger.info("Fetching open orders...")
            open_orders = self.client.get_orders()  # Ensure this is a synchronous method
            self.logger.debug(f"Open orders fetched: {json.dumps(open_orders, indent=2)}")

            # Ensure open_orders is a list
            if not isinstance(open_orders, list):
                self.logger.error("Unexpected data format for open orders.")
                self.assets_ids = set()
                return

            # Extract asset_ids
            assets_ids = set()
            for order in open_orders:
                asset_id = order.get('asset_id')
                if asset_id and isinstance(asset_id, str):
                    assets_ids.add(asset_id)
                else:
                    self.logger.warning(f"Order without valid asset_id encountered: {order}")

            self.assets_ids = assets_ids  # Store assets_ids as an instance variable
            self.logger.info(f"Fetched {len(self.assets_ids)} unique asset_ids from open orders.")
        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}", exc_info=True)
            self.assets_ids = set()

    def subscribe_new_asset(self, asset_id: str):
        try:
            subscription_payload = {
                "type": "subscribe",
                "channel": "market",
                "assets_ids": [asset_id]
            }
            with self.lock:
                if self.ws_client and self.ws_client.ws:
                    self.ws_client.ws.send(json.dumps(subscription_payload))
                    self.logger.info(f"Subscribed to new asset: {shorten_id(asset_id)}")
                else:
                    self.logger.error("WebSocket client is not initialized. Cannot subscribe to new asset.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to new asset {shorten_id(asset_id)}: {e}", exc_info=True)

    def message_handler(self, data: Dict[str, Any]):
        """
        Handle incoming WebSocket messages.
        """
        self.logger.debug(f"Handling message: {data}")
        try:
            event_type = data.get("event_type")
            if event_type == "book":
                self.handle_book_event(data)
            elif event_type == "price_change":
                self.handle_price_change_event(data)
            else:
                self.logger.warning(f"Unhandled event_type: {event_type}")
        except Exception as e:
            self.logger.error(f"Error in message_handler: {e}", exc_info=True)

    def on_ws_open(self):
        """
        Callback when WebSocket connection is opened.
        """
        self.logger.info("WebSocket connection established. Ready to subscribe.")
        self.ws_initialized.set()

    def subscribe_all_assets(self):
        """
        Subscribe to all assets at once to avoid overwhelming the server with multiple requests.
        """
        # Wait until WebSocket client is initialized
        if not self.ws_initialized.wait(timeout=15):  # Wait up to 15 seconds
            self.logger.error("WebSocket client initialization timed out. Cannot subscribe to assets.")
            return

        assets_ids = list(self.assets_ids)  # Convert set to list
        if not assets_ids:
            self.logger.warning("No assets to subscribe to.")
            return

        subscription_payload = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": assets_ids  # Pass the entire list
        }

        try:
            if (
                self.ws_client
                and self.ws_client.ws
                and getattr(self.ws_client.ws, 'sock', None)
                and self.ws_client.ws.sock.connected
            ):
                # Log the payload being sent
                self.logger.debug(f"Sending subscription payload: {subscription_payload}")
                
                self.ws_client.ws.send(json.dumps(subscription_payload))
                self.logger.info(f"Subscribed to all assets: {assets_ids}")
            else:
                self.logger.error("WebSocket client is not connected. Cannot subscribe to assets.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to all assets: {e}", exc_info=True)

    def connect_websocket(self):
        """
        Initialize and run the WebSocket client.
        """
        self.ws_client = ClobWebSocketClient(
            ws_url="wss://ws-subscriptions-clob.polymarket.com/ws/market",
            message_handler=self.message_handler,
            on_open_callback=self.on_ws_open  # Set the event when connected
        )
        ws_thread = threading.Thread(target=self.ws_client.run_sync, daemon=True)
        ws_thread.start()
        self.logger.info("WebSocket client thread started.")

    def run(self):
        """
        Run the RiskManagerWS by fetching orders, connecting WebSocket, and subscribing to assets.
        """
        self.fetch_open_orders()
        self.connect_websocket()
        # Start subscription in a separate thread to prevent blocking
        subscription_thread = threading.Thread(
            target=self.subscribe_all_assets,  # Updated method
            daemon=True
        )
        subscription_thread.start()
        self.logger.info("Subscription thread started.")
        try:
            while self.is_running:
                time.sleep(1)  # Keep the main thread alive
        except KeyboardInterrupt:
            self.shutdown()

    def shutdown(self):
        self.logger.info("Shutting down RiskManagerWS...")
        self.is_running = False
        if self.ws_client:
            self.ws_client.disconnect()
        self.logger.info("RiskManagerWS shutdown complete.")

def main():
    logging.basicConfig(
        level=logging.DEBUG,  # Set to DEBUG for detailed logs
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
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