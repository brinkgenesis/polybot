# File: order_management/WSorder_manager.py

import logging
import threading
import time
import os
from typing import Any, Dict, List, Set
from utils.utils import shorten_id

# Import existing modules
from py_clob_client.client import ClobClient, OpenOrderParams, OrderBookSummary
from py_clob_client.clob_types import ApiCreds, BookParams
from order_management.WS_Sub import WS_Sub
from order_management.limitOrder import build_order, execute_order
from order_management.autoSell import auto_sell_filled_orders
from order_management.order_manager import manage_orders  # Ensure this is correctly imported


class WSOrderManager:
    def __init__(self, client: ClobClient):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.is_running = True
        self.assets_ids: Set[str] = set()
        self.open_orders: List[Dict[str, Any]] = []
        self.local_order_memory: Dict[str, Dict[str, Any]] = {}  # key: order_id, value: order details
        self.memory_lock = threading.Lock() 
        self.subscribed_assets_ids: Set[str] = set()  # Keep track of subscribed assets

        # Initialize WS_Sub instance, passing the shared lock
        self.ws_subscriber = WS_Sub(event_callback=self.handle_event)
        self.ws_subscriber_thread = threading.Thread(target=self.ws_subscriber.run, daemon=True)
        self.ws_subscriber_thread.start()
        self.logger.info("WS_Sub thread started.")

    def run(self):
        self.logger.info("Starting WSOrderManager...")
        while self.is_running:
            try:
                self.fetch_open_orders()
                self.fetch_order_books()
                self.subscribe_to_assets()
                time.sleep(10)
            except Exception as e:
                self.logger.error(f"Error in main loop: {e}", exc_info=True)
                time.sleep(10)

    def fetch_open_orders(self):
        self.logger.info("Fetching open orders...")
        try:
            open_orders = self.client.get_orders(OpenOrderParams())
            self.logger.info(f"Number of open orders fetched: {len(open_orders)}")
            current_order_ids = set()
            current_assets_ids = set() 
            with self.memory_lock:
                for order in open_orders:
                    asset_id = order.get('asset_id')
                    order_id = order.get('id')
                    if not asset_id or not order_id:
                        self.logger.warning(f"Order without valid asset_id or id encountered: {order}")
                        continue
                    current_order_ids.add(order_id)
                    current_assets_ids.add(asset_id)
                    if order_id not in self.local_order_memory:
                        # New order detected
                        self.logger.info(f"New order detected: {order_id}")
                    # Store or update basic order details
                    self.local_order_memory[order_id] = {
                        'asset_id': asset_id,
                        'price': float(order.get('price', 0.0)),
                        'original_size': float(order.get('original_size', 0.0)),
                        'amount': float(order.get('price', 0.0)) * float(order.get('original_size', 0.0)),
                    }
                # Remove orders that are no longer open
                orders_to_remove = set(self.local_order_memory.keys()) - current_order_ids
                for order_id in orders_to_remove:
                    self.logger.info(f"Order closed or canceled: {order_id}")
                    del self.local_order_memory[order_id]
                # Update the assets_ids to reflect only current open orders
                self.assets_ids = current_assets_ids
            self.logger.info("Open orders successfully fetched and stored.")
        except Exception as e:
            self.logger.error(f"Failed to fetch open orders: {e}", exc_info=True)

    def fetch_order_books(self):
        self.logger.info("Fetching order books...")
        try:
            # Convert asset_ids to BookParams instances
            params = [BookParams(token_id=asset_id) for asset_id in self.assets_ids]
            order_books = self.client.get_order_books(params)  # Pass BookParams instances
            self.logger.info(f"Fetched order books for assets: {list(self.assets_ids)}")
            with self.memory_lock:
                for book in order_books:
                    self.process_order_book(book)
            self.logger.info("Order books processed successfully.")
        except Exception as e:
            self.logger.error(f"Error fetching order books: {e}", exc_info=True)

    def process_order_book(self, order_book: OrderBookSummary):
        # Use the correct attribute to get the asset ID
        asset_id = order_book.asset_id

        self.logger.debug(f"Processing order book for asset_id: {asset_id}")

        associated_orders = [
            order_id for order_id, details in self.local_order_memory.items()
            if details['asset_id'] == asset_id
        ]

        if not associated_orders:
            self.logger.warning(f"No associated orders found for asset_id {asset_id}")
            return

        bids = getattr(order_book, 'bids', [])
        asks = getattr(order_book, 'asks', [])

        if not isinstance(bids, list) or not isinstance(asks, list):
            self.logger.error(f"Unexpected data format for bids or asks in order_book for asset_id {asset_id}")
            return

        # Extract the best bid and best ask prices, converting to float
        best_bid = float(max(bids, key=lambda x: float(x.price)).price) if bids else 0.0
        best_ask = float(min(asks, key=lambda x: float(x.price)).price) if asks else 0.0
        midpoint = (best_bid + best_ask) / 2 if best_bid and best_ask else 0.0

        for order_id in associated_orders:
            self.local_order_memory[order_id].update({
                'best_bid': best_bid,
                'best_ask': best_ask,
                'midpoint': midpoint
            })
            self.logger.debug(
                f"Updated order details for order_id {shorten_id(order_id)}: "
                f"Best Bid={best_bid}, Best Ask={best_ask}, Midpoint={midpoint}"
            )

    def subscribe_to_assets(self):
        self.logger.info("Subscribing to assets via WS_Sub...")
        try:
            new_assets_to_subscribe = self.assets_ids - self.subscribed_assets_ids
            if new_assets_to_subscribe:
                self.ws_subscriber.subscribe(list(new_assets_to_subscribe))
                self.subscribed_assets_ids.update(new_assets_to_subscribe)
                self.logger.info(f"Subscribed to new assets: {list(new_assets_to_subscribe)}")
            else:
                self.logger.info("No new asset IDs to subscribe.")
        except Exception as e:
            self.logger.error(f"Error subscribing to assets: {e}", exc_info=True)

    def shutdown(self):
        self.logger.info("Shutting down WSOrderManager...")
        self.is_running = False
        self.ws_subscriber.shutdown()  # Assuming WS_Sub has a shutdown method
        self.ws_subscriber_thread.join()
        self.logger.info("WSOrderManager shut down successfully.")

    def handle_event(self, data: Dict[str, Any]):
        """
        Callback function to handle events received from WS_Sub.
        """
        event_type = data.get("event_type")
        asset_id = data.get("asset_id")
        self.logger.info(f"Received {event_type} event for asset {asset_id}: {data}")
        # Implement your execution logic here


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(name)s %(levelname)s: %(message)s'
    )

    # Initialize client
    try:
        creds = ApiCreds(
            api_key=str(os.getenv("POLY_API_KEY")),
            api_secret=str(os.getenv("POLY_API_SECRET")),
            api_passphrase=str(os.getenv("POLY_PASSPHRASE"))
        ) 

        client = ClobClient(
            host=os.getenv("POLYMARKET_HOST"),
            chain_id=int(os.getenv("CHAIN_ID")),
            key=os.getenv("PRIVATE_KEY"),
            creds=creds,  # Pass the ApiCreds instance
            signature_type=2,  # POLY_GNOSIS_SAFE
            funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
        )
        
        client.set_api_creds(client.create_or_derive_api_creds())
        logging.info("ClobClient initialized successfully.")

    except Exception as e:
        logging.error(f"Failed to initialize ClobClient: {e}", exc_info=True)
        exit(1)

    # Run WSOrderManager
    ws_order_manager = WSOrderManager(client)
    try:
        ws_order_manager.run()
    except KeyboardInterrupt:
        ws_order_manager.shutdown()
        logging.info("WSOrderManager stopped by user.")