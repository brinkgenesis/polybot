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
from utils.logger_config import main_logger
from utils.utils import shorten_id

# Configure the logger
class CustomFormatter(logging.Formatter):
    def format(self, record):
        return record.getMessage()

logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)

# Remove any existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# Create console handler and set level to INFO
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create formatter
formatter = CustomFormatter()

# Add formatter to ch
ch.setFormatter(formatter)

# Add ch to logger
logger.addHandler(ch)

def print_section(title, content):
    logger.info("\n" + "=" * 50)
    logger.info(title)
    logger.info("=" * 50)
    logger.info(content)
    logger.info("")

def get_order_details():
    print_section("Order Input", f"Please enter the following details:")
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
    print_section("Building Order", f"Building order with args: {order_args}")
    signed_order = client.create_order(order_args)
    logger.debug(f"Signed Order Type: {type(signed_order)}")
    logger.debug(f"Signed Order Content: {signed_order}")
    return signed_order

def execute_order(client, signed_order):
    try:
        print_section("Order Execution", "Starting order execution process")
        logger.info(f"Attempting to execute order: {signed_order}")

        logger.info("\nAttempting to post order")
        resp = client.post_order(signed_order, OrderType.GTC)
        
        # Log the type and content of resp
        logger.debug(f"Response Type: {type(resp)}")
        logger.debug(f"Response Content: {resp}")

        logger.info("Order posted, processing response")

        if resp['success']:
            print_section("Execution Result", f"✅ Order executed successfully: {resp['orderID']}")
            return True, resp['orderID']
        else:
            print_section("Execution Result", f"⚠️ Order may not have been placed correctly: {resp['errorMsg']}")
            return False, resp['errorMsg']

    except Exception as e:
        print_section("Execution Error", f"❌ Failed to execute order: {str(e)}")
        logger.error(f"Exception Type: {type(e)}")
        logger.error(f"Exception Message: {e}", exc_info=True)
        return False, str(e)

def main():
    try:
        # Initialize the ClobClient with all necessary credentials
         clob_client = ClobClient(
            host=HOST,
            chain_id=CHAIN_ID,
            key=PRIVATE_KEY,
            signature_type=2,  # POLY_GNOSIS_SAFE
            funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
        )
         clob_client.set_api_creds(clob_client.create_or_derive_api_creds())  # Ensure this is async
         print_section("ClobClient Initialization", "ClobClient initialized with the following details:")
         pprint(vars(clob_client))
         logger.info("ClobClient initialized successfully")

         # Get order details from user input
         token_id, size, price, side = get_order_details()
         print_section("Order Details", f"token_id={token_id}, size={size}, price={price}, side={side}")

            # Check tick size
         try:
                tick_size = clob_client.get_tick_size(token_id)  # Ensure this is async
                print_section("Tick Size", f"Tick size for token {token_id}: {tick_size}")
         except PolyApiException as e:
                print_section("Tick Size Error", f"Failed to get tick size: {e}")
                if e.status_code == 404:
                    logger.error(f"Market not found for token ID: {token_id}")
                return

            # Build the order
         try:
                signed_order = build_order(clob_client, token_id, size, price, side)
                logger.info("Order built successfully")
         except Exception as e:
                print_section("Order Building Error", f"Failed to build order: {e}")
                return

            # Execute the order
         success, result = execute_order(clob_client, signed_order)

         if not success:
                print_section("Execution Error", f"Order execution failed. Reason: {result}")

    except PolyApiException as e:
        print_section("PolyApiException", f"PolyApiException occurred: {e}")
        if e.status_code == 404:
            logger.error("This could indicate an invalid API endpoint or authentication issue.")
    except Exception as e:
        print_section("Unexpected Error", f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
