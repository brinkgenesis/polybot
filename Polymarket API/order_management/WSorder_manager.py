# File: order_management/WSorder_manager.py
import logging
import threading
import time
import os
from typing import Any, Dict, List, Set
from utils.utils import shorten_id
from decimal import Decimal

# Import existing modules
from py_clob_client.client import ClobClient, OpenOrderParams, OrderBookSummary
from py_clob_client.clob_types import ApiCreds, BookParams
from order_management.WS_Sub import WS_Sub
from order_management.limitOrder import build_order, execute_order
from order_management.autoSell import auto_sell_filled_orders
from shared.are_orders_scoring import run_order_scoring
from concurrent.futures import ThreadPoolExecutor, as_completed

class WSOrderManager:
    def __init__(self, client: ClobClient):
        self.client = client
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        self.is_running = True
        self.assets_ids: Set[str] = set()
        self.subscribed_assets_ids: Set[str] = set()
        self.open_orders: List[Dict[str, Any]] = []
        self.local_order_memory: Dict[str, Dict[str, Any]] = {}  # key: order_id, value: order details
        self.memory_lock = threading.Lock()

        self.market_imbalance: Dict[str, bool] = {}
        
        # Initialize WS_Sub instance, passing the shared lock and event callback
        self.ws_subscriber = WS_Sub(
            memory_lock=self.memory_lock,
            event_callback=self.handle_event,
            on_connected=self.on_ws_connected
        )
        self.ws_subscriber_thread = threading.Thread(target=self.ws_subscriber.run, daemon=True)
        self.ws_subscriber_thread.start()
        self.logger.info("WS_Sub thread started.")
         # Initialize scoring thread
        self.scoring_thread = threading.Thread(target=self.check_order_scoring_loop, daemon=True)
        self.scoring_thread.start()
        self.subscribe_to_assets()

        pass


                # Initialize reorder cooldown management
        #self.cooldown_lock = threading.Lock()
        #self.cancelled_orders_cooldown: Dict[str, float] = {}  # key: order_id, value: cooldown_end_time
        #self.cooldown_duration = 600  # 10 minutes in seconds

        # Initialize best_bid_events
        #self.best_bid_events: Dict[str, Dict[str, Any]] = {}

        # Commenting out the reorder_watcher as per instructions
        # self.reorder_executor = ThreadPoolExecutor(max_workers=5)
        # self.reorder_watcher_thread = threading.Thread(target=self.reorder_watcher, daemon=True)
        # self.reorder_watcher_thread.start()
        # self.logger.info("Reorder watcher thread started.")

    def start_bot(self):
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self.run)
            self.thread.start()
            self.logger.info("WSOrderManager started.")
        else:
            self.logger.info("WSOrderManager is already running.")

    def stop_bot(self):
        if self.is_running:
            self.is_running = False
            self.thread.join()
            self.logger.info("WSOrderManager stopped.")
        else:
            self.logger.info("WSOrderManager is not running.")


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
            if not params:
               self.logger.info("No active orders. Skipping fetch_order_books.")
               return
            order_books = self.client.get_order_books(params)  # Pass BookParams instances
            self.logger.info(f"Fetched order books for assets: {list(self.assets_ids)}")
            with self.memory_lock:
                for order_book in order_books:
                    self.process_order_book(order_book)
        except Exception as e:
            self.logger.error(f"Error fetching order books: {e}", exc_info=True)

    def process_order_book(self, order_book: OrderBookSummary):
        # Use the correct attribute to get the asset ID
        try:    
            asset_id = order_book.asset_id

            self.logger.debug(f"Processing order book for asset_id: {asset_id}")

            # Retrieve all orders associated with this asset_id
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
                self.logger.info(
                    f"Updated order details for order_id {shorten_id(order_id)}: "
                    f"Best Bid={best_bid}, Best Ask={best_ask}, Midpoint={midpoint}"
                )
        except Exception as e:
            self.logger.error(f"Error processing order book for asset_id {order_book.token_id}: {e}", exc_info=True)

    def on_ws_connected(self):

        self.logger.info("WebSocket connected successfully.")

    def subscribe_to_assets(self):

        self.logger.info(f"Attempting to subscribe to assets: {self.assets_ids}")
        try:
            if self.assets_ids:
                # Determine new assets to subscribe to
                new_assets = set(self.assets_ids) - self.subscribed_assets_ids
                
                if new_assets:
                    # Update the persistent set
                    self.assets_ids.update(new_assets)
                    
                    # Subscribe to the new assets
                    self.ws_subscriber.subscribe(list(new_assets))
                    self.subscribed_assets_ids.update(new_assets)
                    self.logger.info(f"Subscribed to new assets: {list(new_assets)}")
                else:
                    self.logger.info("All assets already subscribed.")
            else:
                self.logger.warning("No asset IDs provided for subscription.")
        except Exception as e:
            self.logger.error(f"Error subscribing to assets: {e}", exc_info=True)

    def handle_event(self, data: Dict[str, Any]):
        """
        Callback function to handle events received from WS_Sub.
        """
        event_type = data.get("event_type")
        asset_id = data.get("asset_id")
        self.logger.info(f"Received {event_type} event for asset {shorten_id(asset_id)}")

        if event_type == "book":
            bids = data.get("bids", [])
            asks = data.get("asks", [])

            # Calculate total bids and asks volume
            # Updated to sum of (price * size) for each bid and ask
            total_bids = sum(float(bid['price']) * float(bid['size']) for bid in bids)
            total_asks = sum(float(ask['price']) * float(ask['size']) for ask in asks)

            # Avoid division by zero
            if total_asks == 0:
                self.logger.warning(f"Total asks volume is zero for asset {shorten_id(asset_id)}. Setting bid-ask ratio to infinity.")
                bid_ask_ratio = float('inf')
            else:
                bid_ask_ratio = total_bids / total_asks

            self.logger.info(f"Bid-Ask Ratio for asset {shorten_id(asset_id)}: {bid_ask_ratio}")

            # Extract the best bid (max price) and its corresponding size
            if bids:
                best_bid_data = max(bids, key=lambda x: float(x['price']))
                best_bid_event = float(best_bid_data['price'])
                best_bid_size = float(best_bid_data['size'])
                best_bid_value = best_bid_event * best_bid_size
                self.logger.info(f"Best Bid: {best_bid_event} with size {best_bid_size}")
                self.logger.info(f"Best Bid Value: {best_bid_value}")
            else:
                self.logger.warning(f"No bids available for asset {shorten_id(asset_id)}. Using default best_bid_event = 0.0.")
                best_bid_event = 0.0
                best_bid_size = 0.0
                best_bid_value = 0.0

            # Define the conditions dictionary
            conditions = {
                'ratio_gt_0.8_and_value_ge_200': {
                    'condition': lambda ratio, value: ratio > 0.8 and value >= 200,
                    'state': 'acceptable'
                },
                'ratio_gt_0.8_and_value_lt_200': {
                    'condition': lambda ratio, value: ratio > 0.8 and value < 200,
                    'state': 'unstable'
                },
                'ratio_between_0.3_and_0.8_and_value_ge_500': {
                    'condition': lambda ratio, value: 0.3 < ratio < 0.8 and value >= 500,
                    'state': 'acceptable'
                },
                'ratio_between_0.3_and_0.8_and_value_lt_500': {
                    'condition': lambda ratio, value: 0.3 < ratio < 0.8 and value < 500,
                    'state': 'unstable'
                },
                'ratio_between_0.2_and_0.3_and_value_ge_800': {
                    'condition': lambda ratio, value: 0.2 < ratio < 0.3 and value >= 800,
                    'state': 'acceptable'
                },
                'ratio_between_0.2_and_0.3_and_value_lt_800': {
                    'condition': lambda ratio, value: 0.2 < ratio < 0.3 and value < 800,
                    'state': 'unstable'
                },
                'ratio_lt_0.2_or_value_lt_200': {
                    'condition': lambda ratio, value: ratio < 0.2 or value < 200,
                    'state': 'unstable'
                },
            }

            # Determine the current market state based on conditions
            market_state = 'unstable'  # Default state
            for cond_name, cond_details in conditions.items():
                if cond_details['condition'](bid_ask_ratio, best_bid_value):
                    market_state = cond_details['state']
                    self.logger.info(f"Condition '{cond_name}' met. Market state set to '{market_state}'.")
                    break  # Exit after the first matching condition

            # Variables to keep track of market imbalance state
            with self.memory_lock:
                if asset_id not in self.market_imbalance:
                    self.market_imbalance[asset_id] = False

            if market_state == 'unstable':
                if not self.market_imbalance[asset_id]:
                    self.logger.info(f"Market deemed unstable for asset {shorten_id(asset_id)} based on conditions.")
                    self.market_imbalance[asset_id] = True
                    self.handle_bid_ask(asset_id)
                return  # Exit early due to unstable market
            else:
                if self.market_imbalance[asset_id]:
                    self.logger.info(f"Market has stabilized for asset {shorten_id(asset_id)}. Resuming normal operations.")
                    self.market_imbalance[asset_id] = False

                # **New Logic Begins Here**
                # Check if there are existing open orders for this asset
                with self.memory_lock:
                    open_orders_for_asset = [
                        order for order in self.local_order_memory.values()
                        if order['asset_id'] == asset_id
                    ]

                if open_orders_for_asset:
                    self.logger.info(f"Existing open orders found for asset {shorten_id(asset_id)}. Skipping reordering.")
                else:
                    self.logger.info(f"No open orders for asset {shorten_id(asset_id)}. Proceeding to reorder.")

                    # **Required Parameters for reorder**
                    # 1. cancelled_orders: Since this is a fresh reorder, there are no cancelled orders in this context.
                    #    We'll pass an empty list.
                    cancelled_orders = []

                    # 2. best_bid_event: Already extracted above
                    # (best_bid_event is already computed before)

                    # **Call the reorder function with required parameters**
                    self.reorder(cancelled_orders, asset_id, best_bid_event)
                # **New Logic Ends Here**

            try:
                # Extract the best ask (min price) and its corresponding size
                if asks:
                    best_ask_data = min(asks, key=lambda x: float(x['price']))
                    best_ask_event = float(best_ask_data['price'])
                    best_ask_size = float(best_ask_data['size'])
                    self.logger.info(f"Best Ask: {best_ask_event} with size {best_ask_size}")
                else:
                    self.logger.warning(f"No asks available for asset {shorten_id(asset_id)}. Using default best_ask_event = 0.0.")
                    best_ask_event = 0.0
                    best_ask_size = 0.0

                midpoint_event = (best_bid_event + best_ask_event) / 2

                # Pass the extracted data to manage_orders
                self.manage_orders(asset_id, best_bid_event, best_ask_event, midpoint_event, best_bid_size)
            except Exception as e:
                self.logger.error(f"Error processing book event data: {e}", exc_info=True)
        else:
            self.logger.info(f"Unhandled event type: {event_type}")

    def handle_price_change(self, data: Dict[str, Any]):

        asset_id = data.get("asset_id")
        new_price =data.get("price")
        self.logger.info(f"Price change detected for asset {asset_id}: New Price = {new_price}")

    def handle_bid_ask(self, asset_id: str):

        self.logger.info(f"Cancelling orders for asset {shorten_id(asset_id)} due to market imbalance.")

        with self.memory_lock:
            # Find all order IDs related to the asset_id
            orders_to_cancel = [
                order_id for order_id, details in self.local_order_memory.items()
                if details['asset_id'] == asset_id
            ]

        if orders_to_cancel:
            self.logger.info(f"Orders to cancel for asset {shorten_id(asset_id)}: {orders_to_cancel}")
            self.cancel_orders(orders_to_cancel)
            self.logger.info(f"Cancelled orders: {orders_to_cancel}")

            # Optionally, remove cancelled orders from local memory
            with self.memory_lock:
                for order_id in orders_to_cancel:
                    self.local_order_memory.pop(order_id, None)
                    self.logger.info(f"Removed order {shorten_id(order_id)} from local memory due to market imbalance.")
        else:
            self.logger.info(f"No orders to cancel for asset {shorten_id(asset_id)}.")

            #add a tag here and pass it to manage orders so that it does not reorder like if, reorder = FALSE skip reorder

    def manage_orders(self, asset_id: str, best_bid_event: float, best_ask_event: float, midpoint_event: float, best_bid_size: float):

        cancelled_orders = []
        
        try:
            with self.memory_lock:
                relevant_orders = [
                    {'id': order_id, **details}
                    for order_id, details in self.local_order_memory.items()
                    if details['asset_id'] == asset_id
                ]

            if not relevant_orders:
                self.logger.info(f"No open orders found for asset_id: {shorten_id(asset_id)}")
                return

            self.logger.info(f"Managing {len(relevant_orders)} orders for asset_id: {shorten_id(asset_id)}")

            orders_to_cancel = []
            
            # Constants
            TICK_SIZE = os.getenv("TICK_SIZE")
            REWARD_RANGE = 3 * TICK_SIZE  # 0.03
            MAX_INCENTIVE_SPREAD = os.getenv("MAX_INCENTIVE_SPREAD")
            
            for order in relevant_orders:
                order_id = order['id']
                order_price = float(order['price'])
                order_size = float(order['original_size'])

                cancel_conditions = {
                    "outside the reward range": abs(order_price - midpoint_event) > REWARD_RANGE,
                    "too far from best bid": (best_bid_event - order_price) > MAX_INCENTIVE_SPREAD,
                    "at the best bid": order_price == best_bid_event,
                    "best bid value is less than $500": (best_bid_event * best_bid_size) < 500,
                }

                cancel_reasons = [reason for reason, condition in cancel_conditions.items() if condition]
                should_cancel = len(cancel_reasons) > 0

                for reason in cancel_reasons:
                    self.logger.info(f"{reason.capitalize()}: {cancel_conditions[reason]}")

                if should_cancel:
                    self.log_cancellation(order_id, cancel_reasons)
                    orders_to_cancel.append(order_id)
                    cancelled_orders.append(order_id)
                else:
                    self.logger.info(f"Order {shorten_id(order_id)} does not meet any cancellation criteria")
                    
            if orders_to_cancel:
                self.cancel_orders(orders_to_cancel)
                self.logger.info(f"Attempting to cancel orders: {orders_to_cancel}")
                # Trigger reorder immediately after cancelling orders
                #add tag here to prevent reordering for certain cases.
                reorder_results = self.reorder(cancelled_orders, asset_id, best_bid_event)
                self.logger.info(f"Reorder results: {reorder_results}")
            else:
                self.logger.info("No orders to cancel")

        except Exception as e:
            self.logger.error(f"Error managing orders for asset_id {shorten_id(asset_id)}: {str(e)}", exc_info=True)

    def place_new_orders(self, asset_id: str, best_bid_event: float):
         """
         Place new orders based on the best_bid_event for the given asset_id.
         """
         try:
             # Define order parameters based on best_bid_event
             new_order_price = round(best_bid_event - (2 * os.getenv("TICK_SIZE")), 2) # Adjust as needed
             new_order_size =  round(os.getenv("MAX_ORDER_SIZE",450)/ new_order_price,0)  # Implement this method

             # Build and execute the new order
             signed_order = build_order(
                 self.client,
                 str(asset_id),
                 float(new_order_size),
                 float(new_order_price),
                 'BUY'  # or 'SELL' based on your strategy
             )
             result = execute_order(self.client, signed_order)
             self.logger.info(f"New order executed: {result}")

             if result['success']:
                 order_id = result['order_id']
                 with self.memory_lock:
                     self.local_order_memory[order_id] = {
                         'asset_id': asset_id,
                         'price': float(new_order_price),
                         'original_size': float(new_order_size),
                         'amount': float(new_order_price) * float(new_order_size),
                         # Include other necessary details
                     }
                     self.logger.info(f"Added new order {shorten_id(order_id)} to local memory.")
             else:
                 self.logger.error(f"Failed to execute new order for {shorten_id(asset_id)}. Reason: {result['error']}")
         except Exception as e:
             self.logger.error(f"Error placing new orders for asset {shorten_id(asset_id)}: {e}", exc_info=True)


    def log_cancellation(self, order_id: str, reasons: List[str]):
        shortened_id = shorten_id(order_id)
        reasons_formatted = ', '.join(reasons)
        self.logger.info(f"Marking order {shortened_id} for cancellation: {reasons_formatted}")

    def check_order_scoring_loop(self):

        self.logger.info("Starting order scoring thread...")
        while self.is_running:
            try:
                with self.memory_lock:
                    order_ids = list(self.local_order_memory.keys())
        
                if order_ids:
                    self.logger.info(f"Checking scoring for all orders: {[shorten_id(oid) for oid in order_ids]}")
                    scoring_results = run_order_scoring(self.client, order_ids)
        
                    orders_to_cancel = []
                    for order_id in order_ids:
                        is_scoring = scoring_results.get(order_id, False)
                        if not is_scoring:
                            orders_to_cancel.append(order_id)
                            self.logger.info(f"Order {shorten_id(order_id)} is not scoring and will be canceled.")
        
                    if orders_to_cancel:
                        self.cancel_orders(orders_to_cancel)
                        self.logger.info(f"Canceled orders: {orders_to_cancel}")

                else:
                    self.logger.info("No active orders to check scoring.")
        
                time.sleep(10)  # Wait for 5 seconds before next check
        
            except Exception as e:
                self.logger.error(f"Error in scoring thread: {e}", exc_info=True)
                time.sleep(10)

    def cancel_orders(self, orders_to_cancel: List[str]) -> None:
        try:
            # Call the client's cancel_orders method, assuming it accepts a list of order IDs
            self.client.cancel_orders(orders_to_cancel)
            self.logger.info(f"Canceled orders: {orders_to_cancel}")

            # **Removed**: Do not remove orders from local_order_memory here

        except Exception as e:
            self.logger.error(f"Failed to cancel orders {orders_to_cancel}: {e}", exc_info=True)

    def reorder(self, cancelled_orders: List[str], asset_id: str, best_bid_event: float) -> List[str]:
        results = []
        new_order_ids = []  # To keep track of new orders for memory updates

        try:
            for order_id in cancelled_orders:
                cancelled_order = self.local_order_memory.get(order_id)
                if not cancelled_order:
                    self.logger.error(f"Cancelled order {shorten_id(order_id)} not found in memory. Skipping reorder.")
                    continue

                # Ensure the asset is subscribed (it should already be in self.assets_ids)
                if asset_id not in self.assets_ids:
                   self.subscribe_to_assets()

                # Set total order size
                total_order_size = cancelled_order.get('original_size')
                if total_order_size == 0:
                    self.logger.error(f"Invalid order size for order {shorten_id(order_id)}. Order details: {cancelled_order}")
                    continue

                self.logger.info(f"Reordering cancelled order. ID: {shorten_id(order_id)}, Size: {total_order_size}")

                # Calculate order sizes
                order_size_30 = total_order_size * 0.3
                order_size_70 = total_order_size * 0.7

                # Extract best_bid from best_bid_event
                best_bid = float(best_bid_event)
                tick_size = 0.01  # This could be dynamic or fetched from API if available
                max_incentive_spread = 0.02  # Adjust as needed

                # Calculate maker amounts based on best_bid
                maker_amount_30 = round(best_bid - (1 * tick_size), 2)
                maker_amount_70 = round(best_bid - (2 * tick_size), 2)

                # Ensure maker amounts do not exceed max_incentive_spread
                min_allowed_price = best_bid - max_incentive_spread
                if maker_amount_30 < min_allowed_price:
                    self.logger.info("30% order exceeds maximum allowed difference from best bid. Adjusting price.")
                    maker_amount_30 = min_allowed_price
                if maker_amount_70 < min_allowed_price:
                    self.logger.info("70% order exceeds maximum allowed difference from best bid. Adjusting price.")
                    maker_amount_70 = min_allowed_price
               
                # Build and execute 30% order
                if order_size_30 >= 0.0001:
                    signed_order_30 = build_order(
                        self.client,
                        str(asset_id),
                        float(order_size_30),
                        float(maker_amount_30),
                        str('BUY')
                    )
                    result_30 = execute_order(self.client, signed_order_30)
                    self.logger.info(f"30% order executed: {result_30}")
                    
                    if result_30['success']:
                        order_id_30 = result_30['order_id']
                        results.append(order_id_30)
                        new_order_ids.append(order_id_30)
                        # Add new order to local_order_memory
                        with self.memory_lock:
                            self.local_order_memory[order_id_30] = {
                                'asset_id': asset_id,
                                'price': float(maker_amount_30),
                                'original_size': float(order_size_30),
                                'amount': float(maker_amount_30) * float(order_size_30),
                                # Use 'side' from canceled order
                                # Add other necessary details as required
                            }
                            self.logger.info(f"Added new order {shorten_id(order_id_30)} to local memory.")
                    else:
                        self.logger.error(f"Failed to execute 30% order for {shorten_id(order_id)}. Reason: {result_30['error']}")

                # Build and execute 70% order
                if order_size_70 >= 0.0001:
                    signed_order_70 = build_order(
                        self.client,
                        str(asset_id),
                        float(order_size_70),
                        float(maker_amount_70),
                        str('BUY')
                    )
                    result_70 = execute_order(self.client, signed_order_70)
                    self.logger.info(f"70% order executed: {result_70}")
                    
                    if result_70['success']:
                        order_id_70 = result_70['order_id']
                        results.append(order_id_70)
                        new_order_ids.append(order_id_70)
                        # Add new order to local_order_memory
                        with self.memory_lock:
                            self.local_order_memory[order_id_70] = {
                                'asset_id': asset_id,
                                'price': float(maker_amount_70),
                                'original_size': float(order_size_70),
                                'amount': float(maker_amount_70) * float(order_size_70),
    # Use 'side' from canceled order
                                # Add other necessary details as required
                            }
                            self.logger.info(f"Added new order {shorten_id(order_id_70)} to local memory.")
                    else:
                        self.logger.error(f"Failed to execute 70% order for {shorten_id(order_id)}. Reason: {result_70['error']}")


                # Remove the old order after successful reordering
                with self.memory_lock:
                    self.local_order_memory.pop(order_id, None)
                    self.logger.info(f"Removed order {shorten_id(order_id)} from local memory.")

        except Exception as e:
            self.logger.error(f"Error building or executing orders for {shorten_id(order_id)}: {str(e)}")

        return results
      
    def shutdown(self):
        self.logger.info("Shutting down Order Manager...")
        self.is_running = False
        self.ws_subscriber.shutdown()  # Ensure WS_Sub has a shutdown method
        self.ws_subscriber_thread.join()
        self.scoring_thread.join()
        # self.reorder_watcher_thread.join()  # Commented out because it's no longer initialized         

        # Cancel all open orders
        with self.memory_lock:
            open_order_ids = list(self.local_order_memory.keys())
        
        if open_order_ids:
            self.logger.info(f"Cancelling all open orders: {open_order_ids}")
            self.cancel_orders(open_order_ids)
        
        # Close WebSocket connections
        self.ws_subscriber.unsubscribe_all()
        self.logger.info("WSOrderManager shutdown complete.") 

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(message)s'
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
        
        client.set_api_creds(client.derive_api_key())
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
        logging.info("Order Manager stopped by user.")

if __name__ == "__main__":
    main()
