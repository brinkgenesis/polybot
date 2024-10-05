import threading
import time
import logging
from typing import Dict, Any
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

# Initialize module-level logger
logger = logging.getLogger(__name__)

class OrderLevel:
    """
    Represents a single level in the order book.
    """
    def __init__(self, price: float, size: float):
        self.price = price
        self.size = size
        self.amount = round(price * size, 2)

    def update(self, price: float, size: float):
        self.price = price
        self.size = size
        self.amount = round(price * size, 2)

    def to_dict(self) -> Dict[str, float]:
        return {
            'price': self.price,
            'size': self.size,
            'amount': self.amount
        }

class LocalOrderBook:
    """
    Manages local order books for multiple asset_ids.
    """
    def __init__(self, snapshot_interval: int = 600):
        """
        Initialize the LocalOrderBook.

        :param snapshot_interval: Interval in seconds to take order book snapshots.
        """
        self.logger = logging.getLogger(self.__class__.__name__)  # Initialize logger for the class
        self.order_books: Dict[str, Dict[str, Dict[float, OrderLevel]]] = {}
        self.lock = threading.Lock()
        self.snapshot_interval = snapshot_interval  # e.g., 600 seconds for 10 minutes
        self.last_snapshot_time = datetime.now(timezone.utc)
        self.stop_event = threading.Event()
        self.snapshot_thread = threading.Thread(target=self._snapshot_periodically, daemon=True)
        self.snapshot_thread.start()
        self.logger.info(f"LocalOrderBook initialized with snapshot interval of {self.snapshot_interval} seconds.")

    def add_asset(self, asset_id: str):
        """
        Add a new asset_id to track its order book.

        :param asset_id: The asset identifier.
        """
        with self.lock:
            if asset_id not in self.order_books:
                self.order_books[asset_id] = {'bids': {}, 'asks': {}}
                self.logger.info(f"Added new asset_id to LocalOrderBook: {asset_id}")

    def remove_asset(self, asset_id: str):
        """
        Remove an asset_id and discard its order book.

        :param asset_id: The asset identifier.
        """
        with self.lock:
            if asset_id in self.order_books:
                del self.order_books[asset_id]
                self.logger.info(f"Removed asset_id from LocalOrderBook: {asset_id}")

    def process_book_event(self, asset_id: str, book_data: Dict[str, Any]):
        """
        Process a 'book' event to initialize or update the order book for an asset.

        :param asset_id: The asset identifier.
        :param book_data: The order book data from the 'book' event.
        """
        with self.lock:
            if asset_id not in self.order_books:
                self.logger.warning(f"Received 'book' event for untracked asset_id: {asset_id}. Adding to LocalOrderBook.")
                self.order_books[asset_id] = {'bids': {}, 'asks': {}}

            # Assuming book_data contains 'bids' and 'asks' lists
            bids = book_data.get('bids', [])
            asks = book_data.get('asks', [])

            # Update bids
            self.order_books[asset_id]['bids'] = {
                float(level['price']): OrderLevel(price=float(level['price']), size=float(level['size']))
                for level in bids
            }

            # Update asks
            self.order_books[asset_id]['asks'] = {
                float(level['price']): OrderLevel(price=float(level['price']), size=float(level['size']))
                for level in asks
            }

            self.logger.info(f"Processed 'book' event for asset_id: {asset_id}")

    def process_price_change_event(self, asset_id: str, update_data: Dict[str, Any]):
        """
        Process a 'price_change' event to update the local order book for an asset.

        :param asset_id: The asset identifier.
        :param update_data: The update data from the 'price_change' event.
        """
        side = update_data.get('side').upper()  # Normalize to uppercase

        if side == 'BUY':
            # Handle bid price change
            self.update_bid(asset_id, update_data)
        elif side == 'SELL':
            # Handle ask price change
            self.update_ask(asset_id, update_data)
        else:
            self.logger.warning(f"Unknown side '{side}' in 'price_change' event for asset_id: {asset_id}. Ignoring.")

    def update_bid(self, asset_id: str, update_data: Dict[str, Any]):
        price = float(update_data.get('price'))
        size = float(update_data.get('size'))
        if price and size:
            with self.lock:
                if asset_id not in self.order_books:
                    self.order_books[asset_id] = {'bids': {}, 'asks': {}}
                    self.logger.info(f"Added new asset_id to LocalOrderBook during bid update: {asset_id}")
                if price in self.order_books[asset_id]['bids']:
                    self.order_books[asset_id]['bids'][price].size = size
                else:
                    # Add new bid level
                    self.order_books[asset_id]['bids'][price] = OrderLevel(price=price, size=size)
            self.logger.info(f"Updated bid: {price} with size: {size} for asset: {asset_id}")

    def update_ask(self, asset_id: str, update_data: Dict[str, Any]):
        price = float(update_data.get('price'))
        size = float(update_data.get('size'))
        if price and size:
            with self.lock:
                if asset_id not in self.order_books:
                    self.order_books[asset_id] = {'bids': {}, 'asks': {}}
                    self.logger.info(f"Added new asset_id to LocalOrderBook during ask update: {asset_id}")
                if price in self.order_books[asset_id]['asks']:
                    self.order_books[asset_id]['asks'][price].size = size
                else:
                    # Add new ask level
                    self.order_books[asset_id]['asks'][price] = OrderLevel(price=price, size=size)
            self.logger.info(f"Updated ask: {price} with size: {size} for asset: {asset_id}")

    def _snapshot_periodically(self):
        while not self.stop_event.is_set():
            time.sleep(self.snapshot_interval)
            self.snapshot()

    def snapshot(self):
        with self.lock:
            # Implement snapshot logic, e.g., saving to disk or performing analytics
            self.logger.info("Taking snapshot of LocalOrderBook...")
            # Example: serialize order_books to JSON
            # with open('order_book_snapshot.json', 'w') as f:
            #     json.dump(self.order_books, f, default=lambda o: o.__dict__)

    def stop_snapshotting(self):
        self.stop_event.set()
        self.snapshot_thread.join()
        self.logger.info("Stopped snapshotting.")
        
    def get_order_book_snapshot(self, asset_id: str) -> Dict[str, Any]:
        with self.lock:
            if asset_id in self.order_books:
                return {
                    'bids': {price: {'price': ol.price, 'size': ol.size} for price, ol in self.order_books[asset_id]['bids'].items()},
                    'asks': {price: {'price': ol.price, 'size': ol.size} for price, ol in self.order_books[asset_id]['asks'].items()}
                }
            else:
                self.logger.warning(f"Asset ID {asset_id} not found in order books.")
                return {}
# Example usage (to be integrated with RiskManagerWS or main application)