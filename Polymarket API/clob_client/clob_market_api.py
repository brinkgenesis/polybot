from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
from config import HOST, PRIVATE_KEY, CHAIN_ID
from int import clob_client

def place_order(token_id, price, size, side):
    order_args = OrderArgs(price=price, size=size, side=side, token_id=token_id)
    return clob_client.post_order(clob_client.create_order(order_args), OrderType.GTC)

def get_active_orders(token_id):
    return clob_client.get_active_orders(token_id)

def cancel_order(order_id):
    return clob_client.cancel_order(order_id)

def get_fills(token_id):
    return clob_client.get_fills(token_id)

def get_market_price(token_id):
    # Implement logic to get current market price
    # This is a placeholder and needs to be implemented
    return 0.5
