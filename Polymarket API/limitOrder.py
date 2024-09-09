import os
from decimal import Decimal
from py_clob_client.client import ClobClient, RequestArgs, Optional, order_to_json
from py_clob_client.clob_types import OrderArgs, OrderType, ApiCreds, PartialCreateOrderOptions, CreateOrderOptions
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.http_helpers.helpers import post
from config import HOST, CHAIN_ID, PRIVATE_KEY
from pprint import pprint
import logging
from py_clob_client.exceptions import PolyApiException

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_order_details():
    token_id = input("Enter the token ID: ")
    size = Decimal(input("Enter the order size: "))
    price = Decimal(input("Enter the execution price: "))
    side = input("Enter the order side (BUY/SELL): ").upper()
    if side not in [BUY, SELL]:
        raise ValueError("Invalid side. Must be BUY or SELL.")
    return token_id, size, price, side

def build_order(client, token_id, size, price, side):
    order_args = OrderArgs(
        price=price,
        size=size,
        side=side,
        token_id=token_id
        ) 
    logger.info(f"Building order with args: {order_args}")
    return client.create_order(order_args)#,PartialCreateOrderOptions(
    #neg_risk=True))

def execute_order(client, signed_order):
    try:
        logger.info("Starting order execution process")
        logger.info(f"Attempting to execute order: {signed_order}")

        logger.info("Attempting to post order")
        resp = client.post_order(signed_order, OrderType.GTC)
        logger.info("Order posted, processing response")

        if resp['success']:
            logger.info(f"✅ Order executed successfully: {resp['orderID']}")
            return True, resp['orderID']
        else:
            logger.warning(f"⚠️ Order may not have been placed correctly: {resp['errorMsg']}")
            return False, resp['errorMsg']

    except Exception as e:
        logger.error(f"❌ Failed to execute order: {str(e)}")
        return False, str(e)

def main():
    try:
        # Initialize the ClobClient with all necessary credentials
        client = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=PRIVATE_KEY,
            #creds=ApiCreds(os.getenv("POLY_API_KEY"), os.getenv("POLY_API_SECRET"), os.getenv("POLY_PASSPHRASE")),
            signature_type=2,  # POLY_GNOSIS_SAFE
            funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
        )
        client.set_api_creds(client.create_or_derive_api_creds())
        pprint(vars(client))
        logger.info("ClobClient initialized successfully")

        # Get order details from user input
        token_id, size, price, side = get_order_details()
        logger.info(f"Order details: token_id={token_id}, size={size}, price={price}, side={side}")

        # Check tick size
        try:
            tick_size = client.get_tick_size(token_id)
            logger.info(f"Tick size for token {token_id}: {tick_size}")
        except PolyApiException as e:
            logger.error(f"Failed to get tick size: {e}")
            if e.status_code == 404:
                logger.error(f"Market not found for token ID: {token_id}")
            return

        # Build the order
        try:
            signed_order = build_order(client, token_id, size, price, side)
            logger.info("Order built successfully")
        except Exception as e:
            logger.error(f"Failed to build order: {e}")
            return

        # Execute the order
        success, result = execute_order(client, signed_order)

        if success:
            logger.info(f"Order executed successfully. Order ID: {result}")
        else:
            logger.error(f"Order execution failed. Reason: {result}")

    except PolyApiException as e:
        logger.error(f"PolyApiException occurred: {e}")
        if e.status_code == 404:
            logger.error("This could indicate an invalid API endpoint or authentication issue.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
