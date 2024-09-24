import os
import sys
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, OrderArgs, BookParams, OrderType
from are_orders_scoring import run_order_scoring
from gamma_market_api import get_gamma_market_data
from limitOrder import build_order, execute_order, logger as limitOrder_logger
from decimal import Decimal
import time
from logger_config import main_logger as logger
from utils import shorten_id
from typing import List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load environment variables
load_dotenv()

POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")

# Initialize ThreadPoolExecutor
executor = ThreadPoolExecutor(max_workers=10)  # Adjust the number of threads as needed

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

def get_order_book_sync(clob_client: ClobClient, token_id: str) -> Dict:
    """
    Synchronously fetches the order book for a given token ID.
    """
    try:
        order_book = clob_client.get_order_book(token_id)
        logger.info(f"Fetched order book for token ID {token_id}.")
        return order_book
    except Exception as e:
        logger.error(f"Error fetching order book for token ID {token_id}: {e}", exc_info=True)
        return {}

def get_open_orders(client):
    try:
        open_orders = client.get_orders(OpenOrderParams())
        logger.info(f"Retrieved {len(open_orders)} open orders.")
        return open_orders
    except Exception as e:
        logger.error(f"Error fetching open orders: {str(e)}")
        return []

def get_order_book_size_at_price(order_book, price: float) -> float:
    price_str = str(price)
    logger.info(f"Searching for price: {price_str}")
    
    for bid in order_book.bids:
        if bid.price == price_str:
            logger.info(f"Matching bid found at price {price_str}, size: {bid.size}")
            return float(bid.size)
    
    for ask in order_book.asks:
        if ask.price == price_str:
            logger.info(f"Matching ask found at price {price_str}, size: {ask.size}")
            return float(ask.size)
    
    logger.info(f"No matching price found for {price_str}")
    return 0.0

def get_and_format_order_book(order_book, token_id: str, best_bid: float, best_ask: float):
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

def print_open_orders(open_orders):
    if not open_orders:
        logger.info("No open orders found.")
        return
    
    logger.info("Open Orders:")
    for order in open_orders:
        logger.info(f"Order ID: {shorten_id(order['id'])}\nAsset ID: {shorten_id(order['asset_id'])}\nSide: {order['side']}\nPrice: {order['price']}\nSize: {order['original_size']}\n---")

def cancel_orders(client: ClobClient, order_ids: List[str], token_id: str) -> List[str]:
    try:
        client.cancel_orders(order_ids)
        logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in order_ids]}")
        return order_ids
    except Exception as e:
        logger.error(f"Failed to cancel orders for token_id {shorten_id(token_id)}: {str(e)}")
        return []

def reorder(client, cancelled_order, token_id, market_info):
    # Set total order size
    total_order_size = float(cancelled_order['size'])

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
        # Build and execute 30% order
        signed_order_30 = build_order(client, token_id, Decimal(str(order_size_30)), Decimal(str(maker_amount_30)), cancelled_order['side'])
        logger.info(f"30% Signed Order: {signed_order_30}")
        result_30 = execute_order(client, signed_order_30)
        results.append(result_30)
        logger.info(f"30% order executed: {result_30}")

        # Build and execute 70% order
        signed_order_70 = build_order(client, token_id, Decimal(str(order_size_70)), Decimal(str(maker_amount_70)), cancelled_order['side'])
        logger.info(f"70% Signed Order: {signed_order_70}")
        result_70 = execute_order(client, signed_order_70)
        results.append(result_70)
        logger.info(f"70% order executed: {result_70}")

    except Exception as e:
        logger.error(f"Error building or executing orders: {str(e)}")

    return results

def check_api_creds(client):
    if not client.creds or not client.creds.api_secret:
        logger.error("API credentials are not properly set. Please check your environment variables.")
        return False
    return True

def format_section(title):
    return f"\n{'=' * 50}\n{title}\n{'=' * 50}"

def format_order_info(order_id, price, size):
    return f"Order ID: {shorten_id(order_id)}\nPrice: {price}\nSize: {size}"

def format_market_info(best_bid, best_ask):
    return f"Best Bid: {best_bid}\nBest Ask: {best_ask}"

def main():
    logger.info(format_section("Initializing order_manager.py"))
    logger.info(f"Root logger handlers: {logging.getLogger().handlers}")
    logger.info(f"Main logger handlers: {logger.handlers}")
    logger.info(f"LimitOrder logger handlers: {limitOrder_logger.handlers}")

    # Ensure limitOrder logger uses the same handler as the main logger
    limitOrder_logger.handlers = []
    limitOrder_logger.addHandler(logger.handlers[0])
    limitOrder_logger.setLevel(logging.INFO)
    limitOrder_logger.propagate = False

    # Initialize the ClobClient with all necessary credentials
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=int(os.getenv("CHAIN_ID")),
        key=os.getenv("PRIVATE_KEY"),
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
    )
    
    # Set API credentials
    api_key = os.getenv("POLY_API_KEY")
    api_secret = os.getenv("POLY_API_SECRET")
    api_passphrase = os.getenv("POLY_PASSPHRASE")
    
    if not api_key or not api_secret or not api_passphrase:
        logger.error("API credentials are missing. Please check your environment variables.")
        return

    client.set_api_creds(ApiCreds(api_key, api_secret, api_passphrase))
    
    if not check_api_creds(client):
        return

    logger.info("ClobClient initialized successfully")

    # Fetch open orders
    logger.info("Fetching open orders...")
    open_orders = get_open_orders(client)
    if not open_orders:
        logger.info("No open orders found.")
        return
    logger.info(f"Found {len(open_orders)} open orders.")

    # Process each unique token_id
    unique_token_ids = set(order['asset_id'] for order in open_orders)
    logger.info(f"Processing {len(unique_token_ids)} unique token IDs.")

    all_cancelled_orders = []

    for token_id in unique_token_ids:
        logger.info(format_section(f"Processing token_id: {shorten_id(token_id)}"))
        try:
            # Fetch order book data
            order_book = client.get_order_book(token_id)
            
            if order_book is None or not order_book.bids or not order_book.asks:
                logger.error(f"Failed to fetch order book data for token_id: {shorten_id(token_id)}")
                continue
            
            # Sort bids in descending order and asks in ascending order
            sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
            sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price))
            
            best_bid = float(sorted_bids[0].price)  # Highest bid is now the first in the sorted list
            best_ask = float(sorted_asks[0].price)  # Lowest ask is the first in the sorted list
            
            tick_size = 0.01  # You might want to fetch this from the API if possible
            max_incentive_spread = 0.03  # You might want to fetch this from the API if possible

            market_info = {
                'best_bid': best_bid,
                'best_ask': best_ask,
                'tick_size': tick_size,
                'max_incentive_spread': max_incentive_spread
            }
            
            logger.info(format_section(f"Order book data for token_id {shorten_id(token_id)}"))
            logger.info(format_market_info(best_bid, best_ask))

            formatted_order_book = get_and_format_order_book(order_book, token_id, best_bid, best_ask)
            logger.info(formatted_order_book)
            logger.info("Finished processing order book")

            # Manage orders and get cancelled orders
            cancelled_orders = manage_orders(client, open_orders, token_id, market_info, order_book)
            all_cancelled_orders.extend([(order_id, token_id, market_info) for order_id in cancelled_orders])
            
            logger.info(f"Cancelled orders for token_id {shorten_id(token_id)}: {[shorten_id(order_id) for order_id in cancelled_orders]}")

        except Exception as e:
            logger.error(f"Error processing token_id {shorten_id(token_id)}: {str(e)}")

        # Add a small delay between processing each token to avoid rate limiting
        time.sleep(1)

    # Reorder cancelled orders after all cancellations are processed
    for cancelled_order_id, token_id, market_info in all_cancelled_orders:
        try:
            logger.info(format_section(f"Processing cancelled order: {shorten_id(cancelled_order_id)}"))
            cancelled_order = next((order for order in open_orders if order['id'] == cancelled_order_id), None)
            if cancelled_order:
                order_data = {
                    'side': cancelled_order['side'],
                    'size': cancelled_order['original_size'],
                    'token_id': token_id
                }
                
                logger.info(f"Reordering cancelled order: {shorten_id(cancelled_order_id)}")
                result = reorder(client, order_data, token_id, market_info)
                logger.info(f"Reorder result for cancelled order {shorten_id(cancelled_order_id)}: {result}")
            else:
                logger.warning(f"Cancelled order {shorten_id(cancelled_order_id)} not found in open orders")
        except Exception as e:
            logger.error(f"Error processing cancelled order {shorten_id(cancelled_order_id)}: {str(e)}")

        time.sleep(1)

    logger.info("Finished processing all token IDs and reordering cancelled orders.")

def manage_orders(client: ClobClient, open_orders: List[Dict], token_id: str, market_info: Dict, order_book: Dict) -> List[str]:
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
            at_best_bid = order_price == market_info['best_bid']
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
            client.cancel_orders(orders_to_cancel)
            logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {str(e)}")
            orders_to_cancel = []

    return orders_to_cancel
if __name__ == "__main__":
    limitOrder_logger.parent = logger
    __all__ = ['manage_orders', 'get_order_book', 'get_market_info']
    main()

