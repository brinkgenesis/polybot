import threading
import time
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from utils.utils import shorten_id
from threading import Lock, Event
import json

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
    def __init__(self, snapshot_interval: int = 60):
        """
        Initialize the LocalOrderBook.

        :param snapshot_interval: Interval in seconds to take order book snapshots.
        """
        self.logger = logging.getLogger(self.__class__.__name__)  # Initialize logger for the class
        self.order_books = {}
        self.lock = Lock()
        self.stop_event = Event()
        self.snapshot_interval = snapshot_interval  # Set to 60 seconds
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
                    self.logger.info(f"Added new asset_id to LocalOrderBook during bid update: {shorten_id(asset_id)}")
                if price in self.order_books[asset_id]['bids']:
                    self.order_books[asset_id]['bids'][price].size = size
                else:
                    # Add new bid level
                    self.order_books[asset_id]['bids'][price] = OrderLevel(price=price, size=size)
            self.logger.info(f"Updated bid: {price} with size: {size} for asset: {shorten_id(asset_id)}")

    def update_ask(self, asset_id: str, update_data: Dict[str, Any]):
        price = float(update_data.get('price'))
        size = float(update_data.get('size'))
        if price and size:
            with self.lock:
                if asset_id not in self.order_books:
                    self.order_books[asset_id] = {'bids': {}, 'asks': {}}
                    self.logger.info(f"Added new asset_id to LocalOrderBook during ask update: {shorten_id(asset_id)}")
                if price in self.order_books[asset_id]['asks']:
                    self.order_books[asset_id]['asks'][price].size = size
                else:
                    # Add new ask level
                    self.order_books[asset_id]['asks'][price] = OrderLevel(price=price, size=size)
            self.logger.info(f"Updated ask: {price} with size: {size} for asset: {shorten_id(asset_id)}")

    def _snapshot_periodically(self):
        """
        Periodically take snapshots of the order book based on the snapshot interval.
        """
        self.logger.debug("Snapshot periodic thread is running.")
        while not self.stop_event.is_set():
            self.logger.debug("Waiting for next snapshot interval.")
            time.sleep(self.snapshot_interval)
            self.logger.debug("Snapshot interval reached. Taking snapshot.")
            self.snapshot()

    def snapshot(self):
        """
        Take a snapshot of the current state of the LocalOrderBook.
        """
        with self.lock:
            self.logger.info("Taking snapshot of LocalOrderBook...")
            for asset_id, books in self.order_books.items():
                snapshot = self.get_order_book_snapshot(asset_id)
                bids = sorted(snapshot['bids'].values(), key=lambda x: float(x['price']), reverse=True)
                asks = sorted(snapshot['asks'].values(), key=lambda x: float(x['price']))
                
                # Format bids and asks
                bids_formatted = ', '.join([f"{{price: {bid['price']}, size: {bid['size']}}}" for bid in bids[:3]])
                asks_formatted = ', '.join([f"{{price: {ask['price']}, size: {ask['size']}}}" for ask in asks[:3]])
                
                self.logger.info(
                    f"Snapshot - Asset ID: {shorten_id(asset_id)}, "
                    f"Bids: [{bids_formatted}], "
                    f"Asks: [{asks_formatted}]"
                )

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

    def update_order_book(self, asset_id: str, bids: List[Dict[str, str]], asks: List[Dict[str, str]]):
        with self.lock:
            if asset_id not in self.order_books:
                self.order_books[asset_id] = {'bids': {}, 'asks': {}}
                
            # Update Bids
            for bid in bids:
                price = bid.get('price')
                size = bid.get('size')
                if price and size:
                    self.order_books[asset_id]['bids'][price] = {
                        'price': price,
                        'size': float(size)
                    }

            # Update Asks
            for ask in asks:
                price = ask.get('price')
                size = ask.get('size')
                if price and size:
                    self.order_books[asset_id]['asks'][price] = {
                        'price': price,
                        'size': float(size)
                    }

            self.logger.debug(f"Order book updated for asset {shorten_id(asset_id)}")

# Example usage (to be integrated with RiskManagerWS or main application)