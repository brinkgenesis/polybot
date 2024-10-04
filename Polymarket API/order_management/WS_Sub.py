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
#from ratelimiter import RateLimiter

from order_management.limitOrder import build_order, execute_order  # Import existing order functions
from order_management.localorderbook import LocalOrderBook  # Import LocalOrderBook

# Load environment variables (assuming using python-dotenv)
API_KEY = os.getenv("POLY_API_KEY")
API_SECRET = os.getenv("POLY_API_SECRET")
API_PASSPHRASE = os.getenv("POLY_PASSPHRASE")
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
CHAIN_ID = int(os.getenv("CHAIN_ID"))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")
WS_URL = os.getenv("WS_URL")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Configure logging format if not already done
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

# Define a Credentials class
class Credentials:
    def __init__(self, api_key: str, api_secret: str, api_passphrase: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase

class WS_Sub:
    def __init__(self, client: ClobClient):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_client = None
        self.is_running = True
        self.lock = threading.Lock()
        self.ws_initialized = threading.Event()
        self.assets_ids = set()
        self.local_order_book = LocalOrderBook(snapshot_interval=600)  # 10 minutes

        # Initialize Rate Limiter: 60 calls per 60 seconds
        #self.api_rate_limiter = RateLimiter(max_calls=60, period=60)

    def fetch_open_orders(self):
        try:
            self.logger.info("Fetching open orders...")

            # Rate-limited API call
            #with self.api_rate_limiter:
            open_orders = self.client.get_orders()  # Ensure this is a synchronous method

            self.logger.info(f"Fetched {len(open_orders)} open orders.")

            # Ensure open_orders is a list
            if not isinstance(open_orders, list):
                self.logger.error("Unexpected data format for open orders.")
                self.assets_ids = set()
                return

            # Extract asset_ids
            new_assets_ids = set()
            for order in open_orders:
                asset_id = order.get('asset_id')
                if asset_id and isinstance(asset_id, str):
                    new_assets_ids.add(asset_id)
                else:
                    self.logger.warning(f"Order without valid asset_id encountered: {shorten_id(order.get('order_id', 'N/A'))}")

            # Update assets_ids
            previous_assets = self.assets_ids
            self.assets_ids = new_assets_ids

            # Manage LocalOrderBook assets
            current_assets = set(self.local_order_book.order_books.keys())
            new_assets = self.assets_ids - current_assets
            removed_assets = current_assets - self.assets_ids

            for asset in new_assets:
                self.local_order_book.add_asset(asset)

            for asset in removed_assets:
                self.local_order_book.remove_asset(asset)

            self.logger.info(f"Current assets tracked: {self.assets_ids}")

        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}", exc_info=True)
            self.assets_ids = set()

    def connect_websocket(self):  #this is good do not touch
        """
        Initialize and run the WebSocket client.
        """
        self.ws_client = ClobWebSocketClient(
            ws_url=WS_URL,
            message_handler=self.message_handler,
            on_open_callback=self.on_ws_open  # Set the event when connected
        )
        ws_thread = threading.Thread(target=self.ws_client.run_sync, daemon=True)
        ws_thread.start()
        self.logger.info("WebSocket client thread started.")

    def on_ws_open(self):
        """
        Callback when WebSocket connection is opened.
        """
        self.logger.info("WebSocket connection established. Ready to subscribe.")
        self.ws_initialized.set()

    def subscribe_all_assets(self): #this is good do not touch

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
        """
        Handle incoming WebSocket messages.
        """
       
        try:
                   
            asset_id = data.get("asset_id")
            event_type = data.get("event_type")
            if event_type == "book":
                #self.handle_book_event(data)
                book_data = data.get("data")
                if asset_id and book_data:
                    self.local_order_book.process_book_event(asset_id, book_data)
            elif event_type == "price_change":
                #self.handle_price_change_event(data)
                update_data = {
                    'price': data.get('price'),
                    'size': data.get('size'),
                    'side': data.get('side')
                }
                if asset_id:
                    self.local_order_book.process_price_change_event(asset_id, update_data)

            elif event_type == "last_trade_price":
                self.handle_last_trade_price_event(data)
            else:
                self.logger.warning(f"Unhandled event_type: {event_type}")
        except Exception as e:
            self.logger.error(f"Error in message_handler: {e}", exc_info=True)

    def handle_book_event(self, data: Dict[str, Any]):
        try:
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            # Sort asks in ascending order (lowest first) and take top 3
            sorted_asks = sorted(asks, key=lambda x: float(x['price']))
            top_asks = sorted_asks[:3]

            # Sort bids in descending order (highest first) and take top 3
            sorted_bids = sorted(bids, key=lambda x: float(x['price']), reverse=True)
            top_bids = sorted_bids[:3]

            output = "Asks:\n"
            for ask in reversed(top_asks):
                price = float(ask.get('price', '0'))
                size = float(ask.get('size', '0'))
                level = price * size

                # Remove leading zero if price < 1
                price_str = f"{price:.2f}"[1:] if price < 1 else f"{price:.2f}"

                # Format size: no decimal if integer, else two decimals
                size_str = f"{int(size)}" if size.is_integer() else f"{size:.2f}".rstrip('0').rstrip('.')

                # Format level with two decimal places
                level_str = f"{level:.2f}"
                

                # Construct the formatted string with "Level:" label
                output += f"   Price: {price_str}, Size: {size_str}, Level: {level_str}\n"

            output += "\nBids:\n"
            for bid in top_bids:
                price = float(bid.get('price', '0'))
                size = float(bid.get('size', '0'))
                level = price * size

                # Remove leading zero if price < 1
                price_str = f"{price:.2f}"[1:] if price < 1 else f"{price:.2f}"

                # Format size: no decimal if integer, else two decimals
                size_str = f"{int(size)}" if size.is_integer() else f"{size:.2f}".rstrip('0').rstrip('.')

                # Format level with two decimal places
                level_str = f"{level:.2f}"

                # Construct the formatted string with "Level:" label
                output += f"   Price: {price_str}, Size: {size_str}, Level: {level_str}\n"

            self.logger.info(output)

        except Exception as e:
            self.logger.error(f"Error handling 'book' event: {e}", exc_info=True)

    def handle_price_change_event(self, data: Dict[str, Any]):

        try:
            asset_id = data.get("asset_id")
            price = data.get("price")
            size = data.get("size")
            side = data.get("side")
            amount= float(size)*float(price)
            if not asset_id or price is None:
                self.logger.warning("Received 'price_change' event with incomplete data.")
                return
            # Implement the logic to handle the price change
            self.logger.info(f"{shorten_id(asset_id)} level changed: {price} at {size} size on {side} side for ${round(amount,2)}")
            # Further processing can be added here
        except Exception as e:
            self.logger.error(f"Error handling 'price_change' event: {e}", exc_info=True)

    def handle_last_trade_price_event(self, data: Dict[str, Any]):
        try:
            asset_id = data.get("asset_id")
            price = data.get("price")

            self.logger.info(f"{shorten_id(asset_id)} last trade price: {price}")
        except Exception as e:
            self.logger.error(f"Error handling 'last_trade_price' event: {e}", exc_info=True)

    def run(self):
        """
        Run the WS_Sub by fetching orders, connecting WebSocket, and subscribing to assets.
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
        self.logger.info("Shutting down WS_Sub...")
        self.is_running = False
        if self.ws_client:
            self.ws_client.disconnect()
        self.logger.info("WS_Sub shutdown complete.")

def main():

    # Instantiate credentials
    creds = Credentials(
        api_key=API_KEY,
        api_secret=API_SECRET,
        api_passphrase=API_PASSPHRASE
    )

    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=POLYMARKET_PROXY_ADDRESS
    )
    client.set_api_creds(creds)
    socket_sub = WS_Sub(client)
    try:
        socket_sub.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Exiting.")

if __name__ == "__main__":
    main()

def list_tracked_assets(local_order_book: LocalOrderBook):
    all_order_books = local_order_book.get_all_order_books()
    print("Currently Tracked Assets:")
    for asset_id in all_order_books.keys():
        print(f" - {asset_id}")