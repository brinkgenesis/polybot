import logging
import threading
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
import time
import os
import json
from clob_client.clob_websocket_client import ClobWebSocketClient
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, OrderArgs, BookParams, OrderType, OrderBookSummary
from utils.utils import shorten_id
from decimal import Decimal
import math
from threading import Lock, Event
import sys

from order_management.limitOrder import build_order, execute_order  # Import existing order functions

# Load environment variables (assuming using python-dotenv)


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
    def __init__(self, client: ClobClient):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws_client = None
        self.is_running = True
        self.lock = threading.Lock()
        self.ws_initialized = threading.Event()
        self.assets_ids = set()

        # Initialize Rate Limiter: 60 calls per 60 seconds
        #self.api_rate_limiter = RateLimiter(max_calls=60, period=60)

    def fetch_open_orders(self):
        """
        Fetch open orders and extract unique asset_ids based on asset_id.
        """
        try:
            self.logger.info("Fetching open orders...")
            open_orders = self.client.get_orders(OpenOrderParams())
            self.logger.info(f"Number of open orders fetched: {len(open_orders)}")
            self.logger.debug(f"Open Orders: {open_orders}")

            # Extract unique asset_ids from open orders
            new_assets_ids = set()
            for order in open_orders:
                asset_id = order.get('asset_id')
                if asset_id:
                    new_assets_ids.add(asset_id)
                else:
                    self.logger.warning(f"Order without valid asset_id encountered: {order.get('id', 'N/A')}")

            # Update assets_ids
            with self.lock:
                previous_assets = self.assets_ids.copy()
                self.assets_ids = new_assets_ids

                # Manage LocalOrderBook assets
                current_assets = set(self.local_order_book.order_books.keys())
                new_assets = self.assets_ids - current_assets
                removed_assets = current_assets - self.assets_ids

                for asset in new_assets:
                    self.logger.info(f"Adding new asset to LocalOrderBook: {asset}")
                    self.local_order_book.add_asset(asset)

                for asset in removed_assets:
                    self.logger.info(f"Removing asset from LocalOrderBook: {asset}")
                    self.local_order_book.remove_asset(asset)

                self.logger.info(f"Current assets tracked: {self.assets_ids}")

        except Exception as e:
            self.logger.error(f"Error fetching open orders: {e}", exc_info=True)
            self.assets_ids = set()

    def connect_websocket(self):  # this is good do not touch
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

    def subscribe_all_assets(self):  # this is good do not touch
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
            asset_id = data.get("asset_id")  # Changed from 'asset_id' to 'asset_id'
            event_type = data.get("event_type")
            if event_type == "book":
                self.handle_book_event(data)
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
        """
        Handle 'book' event messages.
        """
        try:
            asset_id = data.get("asset_id")
            if not asset_id:
                self.logger.warning("Received 'book' event without asset_id.")
                return

            bids = data.get("bids", [])
            asks = data.get("asks", [])
            timestamp = data.get("timestamp", "N/A")
            hash_value = data.get("hash", "N/A")

            if not bids:
                self.logger.warning(f"No bids data received for asset {asset_id} in 'book' event.")
            if not asks:
                self.logger.warning(f"No asks data received for asset {asset_id} in 'book' event.")

            # Process bids and asks directly
            processed_bids = [
                {"price": float(bid["price"]), "size": float(bid["size"])}
                for bid in bids if "price" in bid and "size" in bid
            ]
            processed_asks = [
                {"price": float(ask["price"]), "size": float(ask["size"])}
                for ask in asks if "price" in ask and "size" in ask
            ]

            # Log the book event
            self.logger.info(
                f"Book Event - Asset ID: {shorten_id(asset_id)}, "
                f"Bids: [{', '.join([f'{{price: {bid['price']:.3f}, size: {bid['size']}}}' for bid in processed_bids[:3]])}], "
                f"Asks: [{', '.join([f'{{price: {ask['price']:.3f}, size: {ask['size']}}}' for ask in processed_asks[:3]])}], "
                f"Timestamp: {self._convert_timestamp(timestamp)}, "
                f"Hash: {hash_value}"
            )

            # Implement Best Bid Level Check
            if processed_bids:
                best_bid = max(processed_bids, key=lambda x: x["price"])
                best_bid_amount = best_bid["price"] * best_bid["size"]
                if best_bid_amount < 500:
                    self.logger.warning(f"Best bid level below $500 for asset {shorten_id(asset_id)}: ${best_bid_amount:.2f}")
        except Exception as e:
            self.logger.error(f"Error handling 'book' event: {e}", exc_info=True)

    def handle_price_change_event(self, data: Dict[str, Any]):
        try:
            asset_id = data.get("asset_id")
            price = data.get("price")
            size = data.get("size")
            side = data.get("side")
            amount = float(size) * float(price) if size and price else 0

            if not asset_id or price is None or size is None or side is None:
                self.logger.warning("Received 'price_change' event with incomplete data.")
                return

            self.logger.info(f"{shorten_id(asset_id)} level changed: {price} at {size} size on {side} side for ${round(amount, 2)}")

            # Update the local order book
            update_data = {
                'price': price,
                'size': size,
                'side': side  # This remains 'BUY' or 'SELL'
            }
            self.local_order_book.process_price_change_event(asset_id, update_data)
        except Exception as e:
            self.logger.error(f"Error processing price change event: {e}", exc_info=True)

    def handle_last_trade_price_event(self, data: Dict[str, Any]):
        try:
            asset_id = data.get("asset_id")
            price = data.get("price")
            if asset_id and price:
                self.logger.info(f"{shorten_id(asset_id)} last trade price: {price}")
        except Exception as e:
            self.logger.error(f"Error handling 'last_trade_price' event: {e}", exc_info=True)

    def run(self):
        """
        Run the WS_Sub by fetching orders, connecting WebSocket, and subscribing to assets.
        """
        #self.fetch_open_orders()
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

    def inspect_order_book(self, asset_id: str):
        snapshot = self.local_order_book.get_order_book_snapshot(asset_id)
        self.logger.info(f"Order Book for {asset_id}: {snapshot}")
    
    # Call inspect_order_book periodically or based on certain triggers

def main():

    # Instantiate credentials using ApiCreds
    try:
        creds = ApiCreds(
        api_key = str(os.getenv("POLY_API_KEY")),
        api_secret= str(os.getenv("POLY_API_SECRET")),
        api_passphrase= str(os.getenv("POLY_PASSPHRASE"))
    ) 

        client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=int(os.getenv("CHAIN_ID")),
        key=os.getenv("PRIVATE_KEY"),
        creds=creds,  # Pass the ApiCreds instance
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
    )
    
        client.set_api_creds(client.create_or_derive_api_creds())
        logger.info("ClobClient initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to set API credentials: {e}", exc_info=True)
        return
    socket_sub = WS_Sub(client)
    try:
        socket_sub.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt. Exiting.")

if __name__ == "__main__":
    main()

