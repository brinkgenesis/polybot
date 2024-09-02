import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams
from dotenv import load_dotenv
from typing import List, Dict
from bid_manager import build_and_print_order, execute_orders  # Import necessary functions from bid_manager

# Load environment variables
load_dotenv()

# Initialize the client
host = os.getenv("POLYMARKET_HOST")
key = os.getenv("PRIVATE_KEY")
chain_id = int(os.getenv("CHAIN_ID"))
client = ClobClient(host, key=key, chain_id=chain_id)

def get_open_orders():
    """
    Fetch open orders using the proxy address from the .env file.
    """
    proxy_address = os.getenv("POLYMARKET_PROXY_ADDRESS")
    open_orders = client.get_orders(owner=proxy_address)
    return open_orders

def cancel_order(order_id):
    """
    Cancel an order by its ID.
    """
    resp = client.cancel(order_id=order_id)
    return resp

def get_market_details(question_id: str) -> Dict:
    """
    Fetch market details using the question_id.
    """
    url = f"{host}/markets/{question_id}"
    response = client.session.get(url)
    if response.status_code != 200:
        raise Exception(f"Error fetching market details. Status code: {response.status_code}, Response: {response.text}")
    return response.json()

def manage_orders(token_id, question_id, best_bid, best_ask, spread, midpoint):
    """
    Manage open orders based on the provided parameters.
    """
    open_orders = get_open_orders()
    market_details = get_market_details(question_id)
    max_incentive_spread = float(market_details['max_incentive_spread'])
    
    orders_to_cancel = []
    for order in open_orders:
        if order['asset_id'] == token_id:
            order_price = float(order['price'])
            order_id = order['id']
            
            # Condition to cancel order based on midpoint
            if midpoint - order_price > max_incentive_spread:
                print(f"Cancelling order {order_id} as midpoint - order_price > max_incentive_spread")
                orders_to_cancel.append(order_id)
            
            # Condition to cancel orders if best bid matches order price
            if best_bid == order_price:
                print(f"Cancelling order {order_id} as best_bid == order_price")
                orders_to_cancel.append(order_id)
    
    # Cancel all orders that meet the conditions
    for order_id in orders_to_cancel:
        cancel_order(order_id)
    
    # Create new orders using bid_manager
    market = {"tokens": [{"token_id": token_id}], "minimum_tick_size": "0.01"}  # Example market data
    gamma_market = {"bestBid": best_bid, "bestAsk": best_ask, "spread": spread, "midpoint": midpoint}  # Example gamma market data
    
    new_orders = build_and_print_order(market, gamma_market)
    if new_orders:
        execute_orders(client, new_orders)

if __name__ == "__main__":
    # Example usage
    token_id = "example_token_id"
    question_id = "example_question_id"
    best_bid = 0.5
    best_ask = 0.6
    spread = 0.1
    midpoint = 0.55
    
    manage_orders(token_id, question_id, best_bid, best_ask, spread, midpoint)
