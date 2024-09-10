import os
import sys
import logging
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams
from gamma_market_api import get_gamma_market_data
from are_orders_scoring import run_order_scoring

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
        # Replace this with the correct method to fetch open orders
        # For example, it might be something like:
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

def get_and_format_order_book(client, token_id: str, best_bid: float, best_ask: float):
    order_book = get_order_book(client, token_id)
    if order_book is None:
        return f"Error fetching order book for token_id {token_id}"
    
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
        print(f"Filled Size: {order['size_matched']}")
        print(f"Status: {order['status']}")
        print("-" * 30)

def manage_orders(client, open_orders):
    orders_to_cancel = []
    for order in open_orders:
        token_id = order['asset_id']
        order_price = float(order['price'])
        order_id = order['id']
        order_size = float(order['original_size'])

        # Fetch market data for this token
        gamma_market = get_gamma_market_data(token_id)
        if gamma_market is None:
            logger.error(f"Failed to fetch market data for token_id {token_id}.")
            continue

        best_bid = float(gamma_market.get('bestBid', '0'))
        best_ask = float(gamma_market.get('bestAsk', '0'))
        
        if best_bid == 0 or best_ask == 0 or best_bid >= best_ask:
            logger.error(f"Invalid best bid or best ask for token_id {token_id}. Skipping this order.")
            continue

        # Fetch order book for this token
        order_book = get_order_book(client, token_id)
        if order_book is None:
            logger.error(f"Failed to fetch order book for token_id {token_id}.")
            continue

        # Set tick_size and max_incentive_spread (you might want to fetch these from the API as well)
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

        # 1. Cancel if order is outside the reward range
        if abs(order_price - midpoint) > reward_range:
            logger.info(f"Marking order {order_id} for cancellation as it's outside the reward range")
            orders_to_cancel.append(order_id)
        
        # 2. Cancel if order is too far from the best bid/ask
        if order['side'] == 'bid' and (market_info['best_bid'] - order_price) > max_incentive_spread:
            logger.info(f"Marking bid {order_id} for cancellation as it's too far from best bid")
            orders_to_cancel.append(order_id)
        elif order['side'] == 'ask' and (order_price - market_info['best_ask']) > max_incentive_spread:
            logger.info(f"Marking ask {order_id} for cancellation as it's too far from best ask")
            orders_to_cancel.append(order_id)
        
        # 3. Cancel if order size is >= 50% of order book size at that price
        order_book_size = get_order_book_size_at_price(order_book, order_price)
        if order_book_size > 0:
            order_size_percentage = (order_size / order_book_size) * 100
            if order_size_percentage >= 50:
                logger.info(f"Marking order {order_id} for cancellation as order size is >= 50% of order book size")
                orders_to_cancel.append(order_id)
        
        # 4a. Cancel if bid is at the best bid
        if order['side'] == 'bid' and order_price == market_info['best_bid']:
            logger.info(f"Marking bid {order_id} for cancellation as it's at the best bid")
            orders_to_cancel.append(order_id)
        
        # 4b. Cancel if best bid has less than $500 in order value
        best_bid_size = get_order_book_size_at_price(order_book, market_info['best_bid'])
        best_bid_value = market_info['best_bid'] * best_bid_size
        if best_bid_value < 500:
            logger.info(f"Marking order {order_id} for cancellation as best bid value is less than $500")
            orders_to_cancel.append(order_id)

    # Cancel all orders that meet the conditions
    cancelled_orders = []
    for order_id in orders_to_cancel:
        try:
            client.cancel_orders(order_id)
            cancelled_orders.append(order_id)
            logger.info(f"Cancelled order {order_id}")
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {str(e)}")

    return cancelled_orders

def main():
    # Initialize the ClobClient with all necessary credentials
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=os.getenv("CHAIN_ID"),
        key=os.getenv("PRIVATE_KEY"),
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    logger.info("ClobClient initialized successfully")

    # Fetch and print open orders for the authenticated wallet
    open_orders = get_open_orders(client)
    print_open_orders(open_orders)

    if open_orders:
        print("Starting to process order books", file=sys.stderr)
        unique_token_ids = set(order['asset_id'] for order in open_orders)
        for token_id in unique_token_ids:
            print(f"Processing token_id {token_id}", file=sys.stderr)
            
            # Fetch gamma market data
            gamma_market = get_gamma_market_data(token_id)
            if gamma_market is None:
                print(f"Failed to fetch market data for token_id {token_id}.")
                continue

            best_bid = float(gamma_market.get('bestBid', '0'))
            best_ask = float(gamma_market.get('bestAsk', '0'))
            
            if best_bid == 0 or best_ask == 0 or best_bid >= best_ask:
                print(f"Invalid best bid or best ask for token_id {token_id}. Skipping this order.")
                continue

            formatted_order_book = get_and_format_order_book(client, token_id, best_bid, best_ask)
            print(formatted_order_book)
            print("Finished processing order book", file=sys.stderr)

        print("Finished processing all order books", file=sys.stderr)

        # Manage orders
        cancelled_orders = manage_orders(client, open_orders)
        print(f"Cancelled orders: {cancelled_orders}")
    else:
        print("No open orders to process.")

if __name__ == "__main__":
    main()
