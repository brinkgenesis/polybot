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
from order_management.WS_Sub import WS_Sub

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

