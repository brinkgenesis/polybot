import logging
import threading
from typing import Any, Dict, Set
import time
import os
import json
from clob_client.clob_websocket_client import ClobWebSocketClient
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderType
from utils.utils import shorten_id
from decimal import Decimal

# Load environment variables (assuming using python-dotenv)
from dotenv import load_dotenv
load_dotenv()

POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
CHAIN_ID = int(os.getenv("CHAIN_ID"))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")
WS_URL = os.getenv("WS_URL")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# Configure logging format if not already done
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class WS_Sub:
    def __init__(self, client: ClobClient, memory_lock: threading.Lock):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_client: ClobWebSocketClient = None
        self.is_running = True
        self.lock = threading.Lock()
        self.assets_ids: Set[str] = set()
        self.event_data: Dict[str, Any] = {}  # Store latest events for assets
        self.memory_lock = memory_lock  # Reference to the shared lock
        self.ws_initialized = threading.Event()  # Event to signal WebSocket is open

    def run(self, assets_ids: Set[str]):
        self.logger.info("Starting WS_Sub...")
        self.assets_ids = assets_ids
        self.connect_websocket()
        self.subscribe_all_assets()
        self.logger.info("WebSocket subscriber is running.")

        try:
            while self.is_running:
                time.sleep(1)  # Keep the main thread alive
        except KeyboardInterrupt:
            self.shutdown()

    def connect_websocket(self):
        self.ws_client = ClobWebSocketClient(
            ws_url=WS_URL,  # Use the WS_URL from environment variables
            message_handler=self.message_handler,
            on_open_callback=self.on_ws_open
        )
        websocket_thread = threading.Thread(target=self.ws_client.run_sync, daemon=True)
        websocket_thread.start()
        self.logger.info("WebSocket client connection initiated.")

    def subscribe_all_assets(self):
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
                # Log minimal subscription payload
                self.logger.info(f"Subscribing to {len(assets_ids)} assets.")
                
                self.ws_client.ws.send(json.dumps(subscription_payload))
                self.logger.info(f"Subscribed to all assets.")
            else:
                self.logger.error("WebSocket client is not connected. Cannot subscribe to assets.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to all assets: {e}", exc_info=True)

    def message_handler(self, data: Dict[str, Any]):
        try:
            asset_id = data.get("asset_id")
            event_type = data.get("event_type")
            if asset_id and event_type:
                with self.lock:
                    self.event_data[asset_id] = data
                self.logger.debug(f"Received {event_type} event for asset {shorten_id(asset_id)}")
            else:
                self.logger.warning("Received message without asset_id or event_type.")
        except Exception as e:
            self.logger.error(f"Error in message_handler: {e}", exc_info=True)

    def get_latest_event(self, asset_id: str) -> Dict[str, Any]:
        with self.lock:
            return self.event_data.get(asset_id, {})

    def on_ws_open(self):
        self.logger.info("WebSocket connection opened.")
        self.ws_initialized.set()  # Signal that WebSocket is open

    def on_ws_close(self):
        self.logger.info("WebSocket connection closed.")

    def on_ws_error(self, error):
        self.logger.error(f"WebSocket error: {error}")

    def shutdown(self):
        self.logger.info("Shutting down WS_Sub...")
        self.is_running = False
        if self.ws_client:
            self.ws_client.disconnect()
        self.logger.info("WS_Sub shutdown complete.")


# Removed the main() function to prevent WS_Sub.py from running independently