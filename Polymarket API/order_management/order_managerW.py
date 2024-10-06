import os
import sys
import logging
import time
import signal
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, OrderArgs, BookParams, OrderType, OrderBookSummary
from shared.are_orders_scoring import run_order_scoring
from gamma_client.gamma_market_api import get_gamma_market_data
from order_management.limitOrder import build_order, execute_order, logger as limitOrder_logger
from decimal import Decimal
from utils.logger_config import main_logger as logger
from utils.utils import shorten_id
from typing import List, Dict, Any
import threading
import json

# Add the parent directory of order_management to Python's module search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
MIN_ORDER_SIZE = Decimal(os.getenv('MIN_ORDER_SIZE', '200'))

# Initialize ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)  # Adjust the number of threads as needed

# Add this at the top of your file, after other imports
cancelled_orders_cooldown: Dict[str, float] = {}

def get_market_info_sync(clob_client: ClobClient, token_id: str) -> Dict[str, Any]:
    """
    Synchronously fetches market information for a given token ID.
    """
    try:
        market_info = clob_client.get_market_info(token_id)
        logger.info(f"Fetched market info for token ID {token_id}: {market_info}")
        return market_info
    except Exception as e:
        logger.error(f"Error fetching market info for token ID {token_id}: {e}", exc_info=True)
        return {}

def get_order_book_sync(clob_client: ClobClient, token_id: str) -> OrderBookSummary:
    """
    Synchronously fetches the order book for a given token ID.
    """
    try:
        order_book = clob_client.get_order_book(token_id)
        logger.info(f"Fetched order book for token ID {token_id}.")
        return order_book
    except Exception as e:
        logger.error(f"Error fetching order book for token ID {token_id}: {e}", exc_info=True)
        # Return an empty OrderBookSummary object in case of error
        return OrderBookSummary(bids=[], asks=[])

def get_open_orders(client: ClobClient) -> List[Dict[str, Any]]:
    """
    Retrieves open orders from the ClobClient.
    """
    try:
        open_orders = client.get_orders(OpenOrderParams())
        logger.info(f"Retrieved {len(open_orders)} open orders.")
        return open_orders
    except Exception as e:
        logger.error(f"Error fetching open orders: {str(e)}")
        return []

def get_order_book_size_at_price(order_book: OrderBookSummary, price: float) -> float:
    """
    Retrieves the size of orders at a specific price in the order book.
    """
    price_str = str(price)
    logger.info(f"Searching for price: {price_str}")
    
    for bid in order_book.bids:
        if float(bid.price) == price:
            logger.info(f"Matching bid found at price {price_str}, size: {bid.size}")
            return float(bid.size)
    
    for ask in order_book.asks:
        if float(ask.price) == price:
            logger.info(f"Matching ask found at price {price_str}, size: {ask.size}")
            return float(ask.size)
    
    logger.info(f"No matching price found for {price_str}")
    return 0.0

def get_and_format_order_book(order_book: OrderBookSummary, token_id: str, best_bid: float, best_ask: float) -> str:
    """
    Formats the order book for logging.
    """
    formatted_output = f"Order Book for token_id {shorten_id(token_id)}:\n"
    formatted_output += "==================================\n"

    # Sort asks in ascending order and take the 10 closest to midpoint
    sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price))[:10]
    # Sort bids in descending order and take the 10 closest to midpoint
    sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)[:10]

    # Calculate midpoint using the provided best_bid and best_ask
    midpoint = (best_ask + best_bid) / 2

    # Format asks
    for ask in reversed(sorted_asks):
        formatted_output += f"Ask: Price: ${float(ask.price):.2f}, Size: {float(ask.size):.2f}\n"

    formatted_output += f"\n{'Midpoint':^20} ${midpoint:.2f}\n\n"

    # Format bids
    for bid in sorted_bids:
        formatted_output += f"Bid: Price: ${float(bid.price):.2f}, Size: {float(bid.size):.2f}\n"

    return formatted_output

def get_market_info(client: ClobClient, token_id: str):
    try:
        market_info = client.get_market_info(token_id)
        return {
            'best_bid': market_info.get('best_bid'),
            'best_ask': market_info.get('best_ask'),
            'tick_size': market_info.get('tick_size'),
            'max_incentive_spread': market_info.get('max_incentive_spread'),
        
        }
    except Exception as e:
        logger.error(f"Error fetching market info for token_id {token_id}: {e}")
        return {
            'best_bid': None,
            'best_ask': None,
            'tick_size': None,
            'max_incentive_spread': None,
         
        }

def manage_orders(client: ClobClient, open_orders: List[Dict], token_id: str, market_info: Dict, order_book: OrderBookSummary) -> List[str]:
    orders_to_cancel = []
    
    midpoint = (market_info['best_bid'] + market_info['best_ask']) / 2
    reward_range = 3 * market_info['tick_size']

    # Get all order IDs for the current token
    order_ids = [order['id'] for order in open_orders if order['asset_id'] == token_id]

    # Check scoring for all orders at once
    logger.info(f"Checking scoring for order IDs: {[shorten_id(order_id) for order_id in order_ids]}")
    scoring_results = run_order_scoring(client, order_ids)

    for order in open_orders:
        if order['asset_id'] == token_id:
            order_price = float(order['price'])
            order_id = order['id']
            order_size = float(order['original_size'])
            
            logger.info(format_section(f"Processing order: {format_order_info(order_id, order_price, order_size)}"))
            logger.info(f"Market info: {format_market_info(market_info['best_bid'], market_info['best_ask'])}")

            # Check if order is scoring
            is_scoring = scoring_results.get(order_id, False)
            logger.info(f"Order {shorten_id(order_id)} scoring status: {is_scoring}")

            # If the order is not scoring, cancel it immediately
            if not is_scoring:
                orders_to_cancel.append(order_id)
                logger.info(f"Order {shorten_id(order_id)} is not scoring and will be cancelled")
                cancelled_orders_cooldown[order_id] = time.time()
                continue

            # For scoring orders, check other conditions
            should_cancel = False
            cancel_reasons = []

            # Check all conditions independently
            logger.info("Checking cancellation conditions:")

            # 1. Reward range check
            outside_reward_range = abs(order_price - midpoint) > reward_range
            if outside_reward_range:
                should_cancel = True
                cancel_reasons.append("outside the reward range")
            logger.info(f"1. Outside reward range: {outside_reward_range}")

            # 2. Too far from best bid
            too_far_from_best_bid = (market_info['best_bid'] - order_price) > market_info['max_incentive_spread']
            if too_far_from_best_bid:
                should_cancel = True
                cancel_reasons.append("too far from best bid")
            logger.info(f"2. Too far from best bid: {too_far_from_best_bid}")

            # 3. At the best bid
            best_bid_excluding_current = max([float(bid.price) for bid in order_book.bids if float(bid.price) != order_price], default=0.0)
            at_best_bid = order_price == market_info['best_bid']
            logger.info(f"Order price: {order_price}, Best bid: {market_info['best_bid']}, Best bid excluding current: {best_bid_excluding_current}")
            if at_best_bid:
                should_cancel = True
                cancel_reasons.append("at the best bid")
            logger.info(f"3. At the best bid: {at_best_bid}")

            # 4. Best bid value less than $500
            best_bid_size = get_order_book_size_at_price(order_book, market_info['best_bid'])
            best_bid_value = market_info['best_bid'] * best_bid_size
            best_bid_value_low = best_bid_value < 500
            if best_bid_value_low:
                should_cancel = True
                cancel_reasons.append("best bid value is less than $500")
            logger.info(f"4. Best bid value < $500: {best_bid_value_low}")

            # 5. Order book size check
            order_book_size = get_order_book_size_at_price(order_book, order_price)
            order_size_percentage = (order_size / order_book_size) * 100 if order_book_size > 0 else 0
            order_size_too_large = order_size_percentage >= 50
            if order_size_too_large:
                should_cancel = True
                cancel_reasons.append("order size is >= 50% of order book size")
            logger.info(f"5. Order size >= 50% of order book size: {order_size_too_large}")

            # Final decision for scoring orders
            if should_cancel:
                logger.info(f"Marking order {shorten_id(order_id)} for cancellation: {', '.join(cancel_reasons)}")
                orders_to_cancel.append(order_id)
            else:
                logger.info(f"Order {shorten_id(order_id)} does not meet any cancellation criteria")

    # Cancel all orders that meet the conditions
    if orders_to_cancel:
        try:
            logger.info(f"Attempting to cancel orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")
            client.cancel_orders(orders_to_cancel)
            logger.info(f"Successfully cancelled orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {str(e)}")
            orders_to_cancel = []
    else:
        logger.info("No orders to cancel")

    logger.info("Finished processing all orders for this token ID")
    return orders_to_cancel

def reorder(client: ClobClient, cancelled_order: Dict[str, Any], token_id: str, market_info: Dict[str, Any]) -> List[str]:
    """
    Reorders based on the cancelled order details.
    """
    order_id = cancelled_order['id']
    
    try:
        # Check if the order is on cooldown
        if order_id in cancelled_orders_cooldown:
            cooldown_time = cancelled_orders_cooldown[order_id]
            if time.time() - cooldown_time < 600:  # 600 seconds = 10 minutes
                logger.info(f"Order {shorten_id(order_id)} is on cooldown. Skipping reorder.")
                return []
            else:
                # Remove from cooldown if 10 minutes have passed
                del cancelled_orders_cooldown[order_id]
                logger.info(f"Cooldown period ended for order {shorten_id(order_id)}. Proceeding with reorder.")

        # Set total order size
        total_order_size = float(cancelled_order.get('size') or cancelled_order.get('original_size', 0))
        if total_order_size == 0:
            logger.error(f"Invalid order size for order {shorten_id(order_id)}. Order details: {cancelled_order}")
            return []

        logger.info(f"Reordering cancelled order. ID: {shorten_id(order_id)}, Size: {total_order_size}")

        # Calculate order sizes
        order_size_30 = total_order_size * 0.3
        order_size_70 = total_order_size * 0.7

        # Calculate maker amounts
        best_bid = market_info['best_bid']
        tick_size = market_info['tick_size']
        max_incentive_spread = market_info['max_incentive_spread']

        maker_amount_30 = round(best_bid - (1 * tick_size), 3)
        maker_amount_70 = round(best_bid - (2 * tick_size), 3)

        # Check if orders exceed the maximum allowed difference from best bid
        min_allowed_price = best_bid - max_incentive_spread
        if maker_amount_30 < min_allowed_price:
            logger.info("30% order exceeds maximum allowed difference from best bid. Adjusting price.")
            maker_amount_30 = min_allowed_price
        if maker_amount_70 < min_allowed_price:
            logger.info("70% order exceeds maximum allowed difference from best bid. Adjusting price.")
            maker_amount_70 = min_allowed_price

        logger.info(f"Best Bid: {best_bid}")
        logger.info(f"Maker Amount 30%: {maker_amount_30}")
        logger.info(f"Maker Amount 70%: {maker_amount_70}")

        # Build and execute orders
        results = []
        try:
            # Adjust 30% order size if below minimum
            if order_size_30 < MIN_ORDER_SIZE:
                logger.info(f"30% order size {order_size_30} is below minimum {MIN_ORDER_SIZE}. Setting to minimum.")
                order_size_30 = MIN_ORDER_SIZE

            # Build and execute 30% order
            signed_order_30 = build_order(client, token_id, Decimal(str(order_size_30)), Decimal(str(maker_amount_30)), cancelled_order['side'])
            #logger.debug(f"Signed Order Type: {type(signed_order_30)}")
            #logger.debug(f"Signed Order Content: {signed_order_30}")
            result_30 = execute_order(client, signed_order_30)
            logger.info(f"30% order executed: {result_30}")
            results.append(result_30)

            # Adjust 70% order size if below minimum
            if order_size_70 < MIN_ORDER_SIZE:
                logger.info(f"70% order size {order_size_70} is below minimum {MIN_ORDER_SIZE}. Setting to minimum.")
                order_size_70 = MIN_ORDER_SIZE

            # Build and execute 70% order
            signed_order_70 = build_order(client, token_id, Decimal(str(order_size_70)), Decimal(str(maker_amount_70)), cancelled_order['side'])
            #logger.debug(f"Signed Order Type: {type(signed_order_70)}")
            #logger.debug(f"Signed Order Content: {signed_order_70}")
            result_70 = execute_order(client, signed_order_70)
            logger.info(f"70% order executed: {result_70}")
            results.append(result_70)

        except Exception as e:
            logger.error(f"Error building or executing orders: {str(e)}")

        return results

    except Exception as e:
        logger.error(f"Error in reorder function for order {shorten_id(order_id)}: {str(e)}", exc_info=True)
        return []

def auto_sell_filled_orders(client: ClobClient):
    """
    Checks open orders for filled portions and executes sell orders equal to the filled size.
    """
    try:
        open_orders = client.get_orders(OpenOrderParams())
    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")
        return

    for order in open_orders:
        size_matched = float(order.get('size_matched', 0))
        original_size = float(order.get('original_size', 0))
        if size_matched > 0:
            # Build and execute a sell order equal to the size that has been filled
            token_id = order.get('asset_id')
            side = 'SELL'
            size = size_matched  # Amount to sell is equal to size_matched

            # Get the order book for the token
            try:
                order_book = client.get_order_book(token_id)
            except Exception as e:
                logger.error(f"Error fetching order book for token {token_id}: {e}")
                continue

            if order_book and order_book.bids:
                # Sort bids in descending order to get the best (highest) bid price
                sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
                best_bid_price = float(sorted_bids[0].price)
                logger.info(f"Best bid price for token {token_id}: {best_bid_price}")

                # Build the order
                try:
                    signed_order = build_order(client, token_id, size, best_bid_price, side)
                    logger.info(f"Order built successfully for token {token_id}")
                except Exception as e:
                    logger.error(f"Failed to build order for token {token_id}: {e}")
                    continue

                # Execute the order
                success, result = execute_order(client, signed_order)

                if success:
                    logger.info(f"Placed sell order for {size} of token {token_id} at price {best_bid_price}")
                else:
                    logger.error(f"Order execution failed for token {token_id}. Reason: {result}")
            else:
                logger.info(f"No bids available for token {token_id}")
        else:
            logger.info(f"No filled orders to process for order ID: {order.get('id')}")


def print_open_orders(open_orders: List[Dict[str, Any]]):
    """
    Logs the details of open orders.
    """
    if not open_orders:
        logger.info("No open orders found.")
        return
    
    logger.info("Open Orders:")
    for order in open_orders:
        logger.info(f"Order ID: {shorten_id(order['id'])}\n"
                    f"Asset ID: {shorten_id(order['asset_id'])}\n"
                    f"Side: {order['side']}\n"
                    f"Price: {order['price']}\n"
                    f"Size: {order['original_size']}\n---")

def format_section(title: str) -> str:
    """
    Formats a section title for logging.
    """
    return f"\n{'=' * 50}\n{title}\n{'=' * 50}"

def format_order_info(order_id: str, price: float, size: float) -> str:
    """
    Formats order information for logging.
    """
    return f"Order ID: {shorten_id(order_id)}\nPrice: {price}\nSize: {size}"

def format_market_info(best_bid: float, best_ask: float) -> str:
    """
    Formats market information for logging.
    """
    return f"Best Bid: {best_bid}\nBest Ask: {best_ask}"

def main(client: ClobClient):
    """
    Main function to fetch, process, cancel, and reorder orders.
    """
    try:     
        # Fetch open orders
        open_orders = get_open_orders(client)
        if not open_orders:
            logger.info("No open orders found.")
            return
        logger.info(f"Found {len(open_orders)} open orders.")

        # Process each unique token_id
        unique_token_ids = set(order['asset_id'] for order in open_orders)
        logger.info(f"Processing {len(unique_token_ids)} unique token IDs.")

        # Initialize a list to store futures
        futures = []

        for token_id in unique_token_ids:
            logger.info(format_section(f"Processing token_id: {shorten_id(token_id)}"))
            try:
                # Fetch order book data
                order_book = get_order_book_sync(client, token_id)
                
                if not order_book.bids or not order_book.asks:
                    logger.error(f"Failed to fetch order book data for token_id: {shorten_id(token_id)}")
                    continue
                
                # Sort bids in descending order and asks in ascending order
                sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
                sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price))
                
                best_bid = float(sorted_bids[0].price) if sorted_bids else 0.0  # Handle empty list
                best_ask = float(sorted_asks[0].price) if sorted_asks else 0.0  # Handle empty list
                
                tick_size = 0.01  # You might want to fetch this from the API if possible
                max_incentive_spread = 0.03  # You might want to fetch this from the API if possible

                market_info = {
                    'best_bid': best_bid,
                    'best_ask': best_ask,
                    'tick_size': tick_size,
                    'max_incentive_spread': max_incentive_spread
                }
                
                #logger.info(format_section(f"Order book data for token_id {shorten_id(token_id)}"))
                #logger.info(format_market_info(best_bid, best_ask))

                #formatted_order_book = get_and_format_order_book(order_book, token_id, best_bid, best_ask)
                #logger.info(formatted_order_book)
               # logger.info("Finished processing order book")

                # Manage orders and get cancelled orders
                cancelled_orders = manage_orders(client, open_orders, token_id, market_info, order_book)
                
                if cancelled_orders:
                    # Check for active open orders
                    active_open_orders = [order for order in open_orders if order['asset_id'] == token_id and order['id'] not in cancelled_orders]
                    if not active_open_orders:
                        for cancelled_order_id in cancelled_orders:
                            cancelled_order = next((order for order in open_orders if order['id'] == cancelled_order_id), None)
                            if cancelled_order:
                                logger.info(f"Submitting reorder task for token_id: {shorten_id(token_id)}")
                                # Submit reorder task to the executor
                                future = executor.submit(reorder, client, cancelled_order, token_id, market_info)
                                futures.append(future)
                    else:
                        logger.info(f"Active open orders found for token_id: {shorten_id(token_id)}. Skipping reorder.")
                else:
                    logger.info(f"No orders cancelled for token_id: {shorten_id(token_id)}. Skipping reorder.")

            except Exception as e:
                logger.error(f"Error processing token_id {shorten_id(token_id)}: {str(e)}")

        # Wait for all reorder tasks to complete
        for future in as_completed(futures):
            try:
                result = future.result()
                logger.info(f"Reorder result: {result}")
            except Exception as e:
                logger.error(f"Reorder task raised an exception: {e}")

        logger.info("Finished processing all token IDs and reordering cancelled orders.")

    except Exception as e:
        logger.error(f"An error occurred in main: {e}", exc_info=True)
    finally:
        # If ClobClient has a close method, ensure it's called
        pass
                

shutdown_flag = False

def signal_handler(signum, frame):
    """
    Handles keyboard interrupt signals for graceful shutdown.
    """
    global shutdown_flag
    logger.info("Keyboard interrupt received. Exiting gracefully...")
    shutdown_flag = True
    executor.shutdown(wait=False)

def main_loop():
    """
    Main loop that continuously executes the main function and auto_sell_filled_orders at specified intervals.
    """
    # Set up the signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Initialize the ClobClient once before the loop
    try:
        client = ClobClient(
            host=POLYMARKET_HOST,
            chain_id=int(os.getenv("CHAIN_ID")),
            key=os.getenv("PRIVATE_KEY"),
            signature_type=2,  # POLY_GNOSIS_SAFE
            funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        logger.info("ClobClient initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize ClobClient: {e}", exc_info=True)
        sys.exit(1)

    while not shutdown_flag:
        try:
            # Submit the main order management task
            future_main = executor.submit(main, client)
            logger.info("Submitted main order management task to ThreadPoolExecutor.")

            # Submit the auto_sell_filled_orders task
            future_auto_sell = executor.submit(auto_sell_filled_orders, client)
            logger.info("Submitted auto_sell_filled_orders task to ThreadPoolExecutor.")

            logger.info("Sleeping for 10 seconds before next iteration...")
            time.sleep(7)  # Adjust this interval as needed

        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            logger.info("Sleeping for 10 seconds before retry...")
            time.sleep(7)

def load_config():
    with open('config.json', 'r') as file:
        config = json.load(file)
    return config

class BotManager:
    def __init__(self):
        self.shutdown_flag = threading.Event()
        self.client = None

    def initialize_client(self):
        # Initialize the ClobClient
        try:
            self.client = ClobClient(
                host=os.getenv("POLYMARKET_HOST"),
                chain_id=int(os.getenv("CHAIN_ID")),
                key=os.getenv("PRIVATE_KEY"),
                signature_type=2,  # POLY_GNOSIS_SAFE
                funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
            )
            self.client.set_api_creds(self.client.create_or_derive_api_creds())
            logger.info("ClobClient initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize ClobClient: {e}", exc_info=True)
            sys.exit(1)

    def run(self):
        logger.info("Bot is starting...")
        self.initialize_client()
        while not self.shutdown_flag.is_set():
            try:
                # Call your main bot logic here
                self.main_loop()
                # Sleep or wait for a certain interval before next iteration
                time.sleep(7)  # Adjust as needed
            except Exception as e:
                logger.error(f"Error in bot execution: {e}", exc_info=True)
                time.sleep(7)
        logger.info("Bot has been stopped.")

    def main_loop(self):
        # Your main bot loop logic here
        # For example:
        main(self.client)

    def stop(self):
        self.shutdown_flag.set()
        logger.info("Shutdown flag set. Bot will stop after the current iteration.")

# If you have code that should run when executing this script directly,
# you can protect it with `if __name__ == "__main__":`
if __name__ == "__main__":
    limitOrder_logger.parent = logger
    __all__ = ['manage_orders', 'get_order_book_sync', 'get_market_info_sync']
    bot_manager = BotManager()
    bot_manager.run()