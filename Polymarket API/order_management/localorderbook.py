import threading
import time
import logging
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone
import json
from clob_client.clob_websocket_client import ClobWebSocketClient


# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.hasHandlers():
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

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
        self.order_books: Dict[str, Dict[str, OrderLevel]] = {}
        self.lock = threading.Lock()
        self.snapshot_interval = snapshot_interval  # e.g., 600 seconds for 10 minutes
        self.last_snapshot_time = datetime.now(timezone.utc)
        self.stop_event = threading.Event()
        self.snapshot_thread = threading.Thread(target=self._snapshot_periodically, daemon=True)
        self.snapshot_thread.start()
        logger.info("LocalOrderBook initialized with snapshot interval of {} seconds.".format(self.snapshot_interval))

    def add_asset(self, asset_id: str):
        """
        Add a new asset_id to track its order book.

        :param asset_id: The asset identifier.
        """
        with self.lock:
            if asset_id not in self.order_books:
                self.order_books[asset_id] = {}
                logger.info(f"Added new asset_id to LocalOrderBook: {asset_id}")

    def remove_asset(self, asset_id: str):
        """
        Remove an asset_id and discard its order book.

        :param asset_id: The asset identifier.
        """
        with self.lock:
            if asset_id in self.order_books:
                del self.order_books[asset_id]
                logger.info(f"Removed asset_id from LocalOrderBook: {asset_id}")

    def process_book_event(self, asset_id: str, book_data: Dict[str, Any]):
        """
        Process a 'book' event to initialize or update the order book for an asset.

        :param asset_id: The asset identifier.
        :param book_data: The order book data from the 'book' event.
        """
        with self.lock:
            if asset_id not in self.order_books:
                logger.warning(f"Received 'book' event for untracked asset_id: {asset_id}. Adding to LocalOrderBook.")
                self.order_books[asset_id] = {}

            # Assuming book_data contains 'bids' and 'asks' lists
            bids = book_data.get('bids', [])
            asks = book_data.get('asks', [])

            # Update bids
            self.order_books[asset_id]['bids'] = {
                level['price']: OrderLevel(price=level['price'], size=level['size'])
                for level in bids
            }

            # Update asks
            self.order_books[asset_id]['asks'] = {
                level['price']: OrderLevel(price=level['price'], size=level['size'])
                for level in asks
            }

            logger.info(f"Processed 'book' event for asset_id: {asset_id}")

    def process_price_change_event(self, asset_id: str, update_data: Dict[str, Any]):
        """
        Process a 'price_change' event to update the local order book for an asset.

        :param asset_id: The asset identifier.
        :param update_data: The update data from the 'price_change' event.
        """
        with self.lock:
            if asset_id not in self.order_books:
                logger.warning(f"Received 'price_change' event for untracked asset_id: {asset_id}. Ignoring.")
                return

            price = update_data.get('price')
            size = update_data.get('size')

            if price is None or size is None:
                logger.warning(f"Incomplete 'price_change' event data for asset_id: {asset_id}. Ignoring.")
                return

            side = update_data.get('side')  # Assuming 'side' indicates 'bid' or 'ask'

            if side not in ['bid', 'ask']:
                logger.warning(f"Unknown side '{side}' in 'price_change' event for asset_id: {asset_id}. Ignoring.")
                return

            order_side = self.order_books[asset_id].get(side + 's')  # 'bids' or 'asks'
            if order_side is None:
                logger.warning(f"No '{side}s' side in order book for asset_id: {asset_id}. Ignoring.")
                return

            # Update the specific price level
            if price in order_side:
                order_level = order_side[price]
                order_level.update(price=price, size=size)
                logger.info(f"Updated {side} level for asset_id {asset_id}: Price={price}, Size={size}, Amount={order_level.amount}")
            else:
                # If the price level does not exist, add it
                order_side[price] = OrderLevel(price=price, size=size)
                logger.info(f"Added new {side} level for asset_id {asset_id}: Price={price}, Size={size}, Amount={order_side[price].amount}")

    def take_snapshot(self):
        """
        Take a snapshot of all current order books.
        """
        with self.lock:
            snapshot_time = datetime.now(timezone.utc)
            snapshot_data = {
                asset_id: {
                    'bids': {price: level.to_dict() for price, level in orders['bids'].items()},
                    'asks': {price: level.to_dict() for price, level in orders['asks'].items()}
                }
                for asset_id, orders in self.order_books.items()
            }
            logger.info(f"Snapshot taken at {snapshot_time.isoformat()} UTC.")
            # For demonstration, we log the snapshot. In production, consider saving to a file or database.
            logger.debug(f"Snapshot Data: {json.dumps(snapshot_data, indent=2)}")

            self.last_snapshot_time = snapshot_time

    def _snapshot_periodically(self):
        """
        Internal method to take snapshots at regular intervals.
        """
        while not self.stop_event.is_set():
            current_time = datetime.now(timezone.utc)
            elapsed = (current_time - self.last_snapshot_time).total_seconds()
            if elapsed >= self.snapshot_interval:
                self.take_snapshot()
            time.sleep(1)  # Sleep briefly to prevent tight loop

    def stop_snapshotting(self):
        """
        Stop the periodic snapshot thread.
        """
        self.stop_event.set()
        self.snapshot_thread.join()
        logger.info("Stopped periodic snapshotting.")

    def get_order_book(self, asset_id: str) -> Dict[str, Any]:
        """
        Retrieve the local order book for a specific asset_id.

        :param asset_id: The asset identifier.
        :return: A dictionary containing 'bids' and 'asks'.
        """
        with self.lock:
            if asset_id not in self.order_books:
                logger.warning(f"Requested order book for untracked asset_id: {asset_id}.")
                return {}
            return {
                'bids': {price: level.to_dict() for price, level in self.order_books[asset_id]['bids'].items()},
                'asks': {price: level.to_dict() for price, level in self.order_books[asset_id]['asks'].items()}
            }

    def get_all_order_books(self) -> Dict[str, Any]:
        """
        Retrieve all local order books.

        :return: A dictionary of all order books keyed by asset_id.
        """
        with self.lock:
            return {
                asset_id: {
                    'bids': {price: level.to_dict() for price, level in orders['bids'].items()},
                    'asks': {price: level.to_dict() for price, level in orders['asks'].items()}
                }
                for asset_id, orders in self.order_books.items()
            }

# Example usage (to be integrated with RiskManagerWS or main application)
if __name__ == "__main__":
    # Initialize LocalOrderBook with default snapshot interval of 600 seconds (10 minutes)
    local_order_book = LocalOrderBook()

    # Simulate adding an asset and processing events
    asset_id_example = "asset_123"
    local_order_book.add_asset(asset_id_example)

    # Simulate a 'book' event
    book_event_data = {
        'bids': [
            {'price': 100.5, 'size': 10},
            {'price': 100.0, 'size': 15}
        ],
        'asks': [
            {'price': 101.0, 'size': 12},
            {'price': 101.5, 'size': 8}
        ]
    }
    local_order_book.process_book_event(asset_id_example, book_event_data)

    # Simulate a 'price_change' event
    price_change_event_data = {
        'price': 100.5,
        'size': 12,
        'side': 'bid'
    }
    local_order_book.process_price_change_event(asset_id_example, price_change_event_data)

    # Let the snapshot thread run for a short while
    try:
        time.sleep(5)  # Sleep for demonstration purposes
    except KeyboardInterrupt:
        pass
    finally:
        local_order_book.stop_snapshotting()