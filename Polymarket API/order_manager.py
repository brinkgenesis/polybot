import os
import sys
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams
from gamma_market_api import get_gamma_market_data
from are_orders_scoring import run_order_scoring
from reOrder import reorder
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")

def get_order_book(client, token_id: str):
    try:
        return client.get_order_book(token_id)
    except Exception as e:
        logger.error(f"Error fetching order book for token_id {token_id}: {str(e)}")
        return None

def get_open_orders(client):
    try:
        return client.get_orders(OpenOrderParams())
    except Exception as e:
        logger.error(f"Error fetching open orders: {str(e)}")
        return None

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
    formatted_output = f"Order Book for token_id {token_id}:\n"
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
        print("No open orders found.")
        return
    
    print("Open Orders:")
    for order in open_orders:
        print(f"Order ID: {order['id']}")
        print(f"Asset ID: {order['asset_id']}")
        print(f"Side: {order['side']}")
        print(f"Price: {order['price']}")
        print(f"Size: {order['original_size']}")
        print("---")
        

def check_api_creds(client):
    if not client.creds or not client.creds.api_secret:
        logger.error("API credentials are not properly set. Please check your environment variables.")
        return False
    return True

def main():
    # Initialize the ClobClient with all necessary credentials
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=os.getenv("CHAIN_ID"),
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
    for token_id in unique_token_ids:
        logger.info(f"Processing token_id: {token_id}")
        try:
            # Fetch gamma market data
            gamma_market = get_gamma_market_data(token_id)
            if gamma_market is None:
                logger.error(f"Failed to fetch market data for token_id: {token_id}")
                continue
            
            best_bid = float(gamma_market.get('bestBid', '0'))
            best_ask = float(gamma_market.get('bestAsk', '0'))
            
            logger.info(f"Gamma market data for token_id {token_id}:")
            logger.info(f"Best Bid: {best_bid}")
            logger.info(f"Best Ask: {best_ask}")
            
            if best_bid == 0 or best_ask == 0 or best_bid >= best_ask:
                logger.error(f"Invalid best bid or best ask for token_id {token_id}. Skipping this token.")
                continue

            # Fetch order book
            order_book = get_order_book(client, token_id)
            if order_book is None:
                logger.error(f"Failed to fetch order book for token_id {token_id}")
                continue

            formatted_order_book = get_and_format_order_book(order_book, token_id, best_bid, best_ask)
            print(formatted_order_book)
            print("Finished processing order book", file=sys.stderr)

            # Manage orders and get cancelled orders
            cancelled_orders = manage_orders(client, open_orders, token_id, best_bid, best_ask, order_book)
            
            logger.info(f"Cancelled orders for token_id {token_id}: {cancelled_orders}")

            # Reorder cancelled orders
            for cancelled_order_id in cancelled_orders:
                logger.info(f"Processing cancelled order: {cancelled_order_id}")
                cancelled_order = next((order for order in open_orders if order['id'] == cancelled_order_id), None)
                if cancelled_order:
                    order_data = {
                        'side': cancelled_order['side'],
                        'size': cancelled_order['original_size'],
                        'token_id': token_id
                    }
                    
                    # Update gamma_market with current best bid/ask
                    gamma_market['bestBid'] = best_bid
                    gamma_market['bestAsk'] = best_ask

                    # Reorder the cancelled order
                    logger.info(f"Reordering cancelled order: {cancelled_order_id}")
                    result = reorder(client, order_data, token_id, gamma_market, gamma_market)
                    logger.info(f"Reorder result for cancelled order {cancelled_order_id}: {result}")
                else:
                    logger.warning(f"Cancelled order {cancelled_order_id} not found in open orders")
        
        except Exception as e:
            logger.error(f"Error processing token_id {token_id}: {str(e)}")

        # Add a small delay between processing each token to avoid rate limiting
        time.sleep(1)

    logger.info("Finished processing all token IDs.")

def manage_orders(client, open_orders, token_id, best_bid, best_ask, order_book):
    orders_to_cancel = []
    
    tick_size = 0.01  # Example value, adjust as needed
    max_incentive_spread = 0.03  # Example value, adjust as needed

    market_info = {
        'best_bid': best_bid,
        'best_ask': best_ask,
        'tick_size': tick_size,
        'max_incentive_spread': max_incentive_spread
    }

    midpoint = (best_bid + best_ask) / 2
    reward_range = 3 * tick_size

    # Get all order IDs for the current token
    order_ids = [order['id'] for order in open_orders if order['asset_id'] == token_id]

    # Check scoring for all orders at once
    logger.info(f"Checking scoring for order IDs: {order_ids}")
    scoring_results = run_order_scoring(client, order_ids)

    for order in open_orders:
        if order['asset_id'] == token_id:
            order_price = float(order['price'])
            order_id = order['id']
            order_size = float(order['original_size'])
            
            logger.info(f"\nProcessing order: ID: {order_id}, Price: {order_price}, Size: {order_size}")
            logger.info(f"Market info: Best Bid: {market_info['best_bid']}, Best Ask: {market_info['best_ask']}")

            # Check if order is scoring
            is_scoring = scoring_results.get(order_id, False)
            logger.info(f"Order {order_id} scoring status: {is_scoring}")

            # Even if the order is scoring, we'll check all conditions
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
            too_far_from_best_bid = (market_info['best_bid'] - order_price) > max_incentive_spread
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

            # Final decision
            if should_cancel:
                logger.info(f"Marking order {order_id} for cancellation: {', '.join(cancel_reasons)}")
                if is_scoring:
                    logger.info(f"Note: Order {order_id} was scoring, but is being cancelled due to meeting cancellation criteria")
                orders_to_cancel.append(order_id)
            else:
                logger.info(f"Order {order_id} does not meet any cancellation criteria")

    # Cancel all orders that meet the conditions
    if orders_to_cancel:
        try:
            client.cancel_orders(orders_to_cancel)
            logger.info(f"Cancelled orders: {orders_to_cancel}")
        except Exception as e:
            logger.error(f"Failed to cancel orders: {str(e)}")
            orders_to_cancel = []

    return orders_to_cancel

if __name__ == "__main__":
    main()
