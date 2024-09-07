import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams, ApiCreds
from dotenv import load_dotenv
from typing import List, Dict
from bid_manager import build_and_print_order, execute_orders  # Import necessary functions from bid_manager
import logging

# Load environment variables
load_dotenv()

# Initialize constants
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
ORDER_BOOK_ENDPOINT = "/orderbook"

# Set up logging to remove timestamp and INFO
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Remove timestamps and INFO from all loggers
for handler in logging.root.handlers:
    handler.setFormatter(logging.Formatter('%(message)s'))

# Initialize the client
host = os.getenv("POLYMARKET_HOST")
key = os.getenv("PRIVATE_KEY")
chain_id = int(os.getenv("CHAIN_ID"))
api_key = os.getenv("POLY_API_KEY")
api_secret = os.getenv("POLY_API_SECRET")
api_passphrase = os.getenv("POLY_PASSPHRASE")

api_creds = ApiCreds(api_key, api_secret, api_passphrase)
client = ClobClient(host, key=key, chain_id=chain_id, creds=api_creds)

def get_open_orders(params: OpenOrderParams = None):
    """
    Get open orders using the ClobClient.
    """
    try:
        return client.get_orders(params)
    except Exception as e:
        logger.error(f"Error fetching open orders: {str(e)}")
        return []

def format_order_book(order_book):
    """
    Format the OrderBookSummary for better readability with asks on top (lowest at bottom)
    and bids below (highest at top).
    """
    formatted = f"Market: {order_book.market}\n"
    formatted += f"Asset ID: {order_book.asset_id}\n\n"  # Added an extra newline
    
    # Sort asks from highest to lowest
    sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price), reverse=True)
    formatted += "Asks:\n"
    for ask in sorted_asks:
        formatted += f"  Price: {ask.price}, Size: {ask.size}\n"
    
    # Sort bids from highest to lowest
    sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
    formatted += "Bids:\n"
    for bid in sorted_bids:
        formatted += f"  Price: {bid.price}, Size: {bid.size}\n"
    
    formatted += f"\nHash: {order_book.hash}"  # Added a newline before Hash
    return formatted

def get_order_book(token_id: str):
    """
    Fetch and print the order book for the given token_id using the ClobClient.
    """
    try:
        raw_order_book = client.get_order_book(token_id)
        logger.info(f"Order book for token_id {token_id}:")
        logger.info(format_order_book(raw_order_book))
        return raw_order_book
    except Exception as e:
        logger.error(f"Error fetching order book for token_id {token_id}: {str(e)}")
        return None

def cancel_order(order_id):
    """
    Cancel an order by its ID.
    """
    try:
        resp = client.cancel(order_id=order_id)
        logger.info(f"Order {order_id} cancelled successfully")
        return resp
    except Exception as e:
        logger.error(f"Error cancelling order {order_id}: {str(e)}")
        return None

# Mock functions for bid_manager
def mock_build_and_print_order(market: Dict, gamma_market: Dict, client: ClobClient):
    logger.info("Mocking build_and_print_order function")
    logger.info(f"Market: {market}")
    logger.info(f"Gamma Market: {gamma_market}")
    return [{"token_id": market['token_ids'][0], "price": gamma_market['midpoint'], "size": 100, "side": "BUY"}]

def mock_execute_orders(client: ClobClient, orders: List[Dict], market: Dict):
    logger.info("Mocking execute_orders function")
    logger.info(f"Orders to execute: {orders}")
    logger.info(f"Market: {market}")

def get_order_book_size_at_price(order_book, price):
    """
    Look up the total size of orders at a given price in the order book.
    """
    for bid in order_book.bids:
        if float(bid.price) == price:
            return float(bid.size)
    for ask in order_book.asks:
        if float(ask.price) == price:
            return float(ask.size)
    return 0  # Return 0 if no orders at this price

def manage_orders(token_id, best_bid, best_ask, spread, midpoint):
    """
    Manage open orders based on the provided parameters.
    """
    open_orders = get_open_orders()
    order_book = get_order_book(token_id)
    
    orders_to_cancel = []
    for order in open_orders:
        if order['asset_id'] == token_id:
            order_price = float(order['price'])
            order_id = order['id']
            order_size = float(order['size'])
            
            # Condition to cancel orders if best bid matches order price
            if best_bid == order_price:
                logger.info(f"Marking order {order_id} for cancellation as best_bid == order_price")
                orders_to_cancel.append(order_id)
            
            # New condition: cancel if order size is >= 50% of order book size at that price
            order_book_size = get_order_book_size_at_price(order_book, order_price)
            if order_book_size > 0:
                order_size_percentage = (order_size / order_book_size) * 100
                logger.info(f"Order {order_id} size ({order_size}) is {order_size_percentage:.2f}% of order book size ({order_book_size}) at price {order_price}")
                
                if order_size_percentage >= 50:
                    logger.info(f"Marking order {order_id} for cancellation as order size is >= 50% of order book size")
                    orders_to_cancel.append(order_id)
            else:
                logger.info(f"No orders in the book at price {order_price} for order {order_id}")
            
            # New condition: cancel if best bid size in order book is less than $500 in value
            best_bid_size = get_order_book_size_at_price(order_book, best_bid)
            best_bid_value = best_bid * best_bid_size
            if best_bid_value < 500:
                logger.info(f"Marking order {order_id} for cancellation as best bid size ({best_bid_size}) at price {best_bid} is less than $500 in value (${best_bid_value:.2f})")
                orders_to_cancel.append(order_id)
    
    # Cancel all orders that meet the conditions
    for order_id in orders_to_cancel:
        cancel_order(order_id)
    
    # Fetch and print order book for this token_id
    get_order_book(token_id)
    
    # Create new orders using mocked bid_manager functions
    market = {
        "question": "Example Question",
        "questionID": "example_id",
        "token_ids": [token_id],
        "minimum_tick_size": "0.01"
    }
    gamma_market = {
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "spread": spread,
        "midpoint": midpoint
    }
    
    new_orders = mock_build_and_print_order(market, gamma_market, client)
    if new_orders:
        mock_execute_orders(client, new_orders, market)

if __name__ == "__main__":
    # Example usage
    token_id = "11015470973684177829729219287262166995141465048508201953575582100565462316088"
    best_bid = 0.5
    best_ask = 0.6
    spread = 0.1
    midpoint = 0.55
    
    manage_orders(token_id, best_bid, best_ask, spread, midpoint)
