import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams
from config import (
    POLYMARKET_HOST,
    POLY_API_KEY,
    POLY_API_SECRET,
    POLY_PASSPHRASE,
    PRIVATE_KEY,
    POLYMARKET_PROXY_ADDRESS,
    CHAIN_ID,
)
from order_management.limitOrder import build_order, execute_order
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def auto_sell_filled_orders():
    # Initialize ApiCreds
    creds = ApiCreds(
        api_key=POLY_API_KEY,
        api_secret=POLY_API_SECRET,
        api_passphrase=POLY_PASSPHRASE,
    )

    # Instantiate ClobClient
    clob_client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
        signature_type=2,  # Adjust based on your setup
        funder=POLYMARKET_PROXY_ADDRESS,
    )

    # Set API credentials
    clob_client.set_api_creds(clob_client.create_or_derive_api_creds())

    # Get open orders
    try:
        open_orders = clob_client.get_orders(OpenOrderParams())
    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")
        return

    for order in open_orders:
        size_matched = float(order['size_matched'])
        original_size = float(order['original_size'])
        if size_matched > 0:
            # Build and execute a sell order equal to the size that has been filled
            token_id = order['asset_id']
            side = 'SELL'
            size = size_matched  # Amount to sell is equal to size_matched

            # Get the order book for the token
            try:
                order_book = clob_client.get_order_book(token_id)
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
                    signed_order = build_order(clob_client, token_id, size, best_bid_price, side)
                    logger.info(f"Order built successfully for token {token_id}")
                except Exception as e:
                    logger.error(f"Failed to build order for token {token_id}: {e}")
                    continue

                # Execute the order
                success, result = execute_order(clob_client, signed_order)

                if success:
                    logger.info(f"Placed sell order for {size} of token {token_id} at price {best_bid_price}")
                else:
                    logger.error(f"Order execution failed for token {token_id}. Reason: {result}")
            else:
                logger.info(f"No bids available for token {token_id}")
        else:
            logger.info(f"No filled orders to process for order ID: {order['id']}")

if __name__ == "__main__":
    auto_sell_filled_orders()
