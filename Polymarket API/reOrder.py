import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient, ApiCreds
from py_clob_client.clob_types import OrderArgs, OpenOrderParams
from limitOrder import execute_order
from order_manager import manage_orders, get_open_orders, get_order_book  # Add this import
import logging
from pprint import pprint   
from gamma_market_api import get_gamma_market_data
import time

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_client():
    return ClobClient(
        host=os.getenv("POLYMARKET_HOST"),
        chain_id=int(os.getenv("CHAIN_ID")),
        key=os.getenv("PRIVATE_KEY"),
        signature_type=2,
        funder=os.getenv("POLYMARKET_PROXY_ADDRESS")
    )

def reorder(client, cancelled_order, market_id, gamma_market, market):
    # Set total order size
    total_order_size = float(cancelled_order['original_size'])

    # Calculate maker amount
    best_bid = float(gamma_market.get('bestBid', '0'))
    order_price_min_tick_size = float(market.get('minimum_tick_size', '0.01'))
    max_incentive_spread = float(market.get('max_incentive_spread', '0.03'))

    # Calculate order sizes
    order_size_30 = total_order_size * 0.3
    order_size_70 = total_order_size * 0.7

    # Calculate maker amounts
    maker_amount_30 = round(best_bid - (1 * order_price_min_tick_size), 3)
    maker_amount_70 = round(best_bid - (2 * order_price_min_tick_size), 3)

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

    # Build orders using OrderArgs
    order_args_30 = OrderArgs(
        price=str(maker_amount_30),
        size=str(order_size_30),
        side=cancelled_order['side'],
        token_id=cancelled_order['token_id'],
        fee_rate_bps=0,
        nonce=0,
        expiration=0
    )

    order_args_70 = OrderArgs(
        price=str(maker_amount_70),
        size=str(order_size_70),
        side=cancelled_order['side'],
        token_id=cancelled_order['token_id'],
        fee_rate_bps=0,
        nonce=0,
        expiration=0
    )

    logger.info(f"30% Order Args: {order_args_30}")
    logger.info(f"70% Order Args: {order_args_70}")

    # Execute orders
    results = []
    try:
        # Execute 30% order
        result_30 = execute_order(client, order_args_30)
        results.append(result_30)
        logger.info(f"30% order executed: {result_30}")

        # Execute 70% order
        result_70 = execute_order(client, order_args_70)
        results.append(result_70)
        logger.info(f"70% order executed: {result_70}")

    except Exception as e:
        logger.error(f"Error executing orders: {str(e)}")

    return results

def main():
    client = initialize_client()
    
    client.set_api_creds(client.create_or_derive_api_creds())
    print("ClobClient Initialization", "ClobClient initialized with the following details:")
    pprint(vars(client))
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
            logger.info(f"Fetching gamma market data for token_id: {token_id}")
            gamma_market = get_gamma_market_data(token_id)
            if gamma_market is None:
                logger.error(f"Failed to fetch market data for token_id: {token_id}")
                continue
            
            best_bid = float(gamma_market.get('bestBid', '0'))
            best_ask = float(gamma_market.get('bestAsk', '0'))
            logger.info(f"Best bid: {best_bid}, Best ask: {best_ask}")
            
            if best_bid == 0 or best_ask == 0 or best_bid >= best_ask:
                logger.error(f"Invalid best bid or best ask for token_id {token_id}. Skipping this token.")
                continue

            # Fetch order book
            logger.info(f"Fetching order book for token_id: {token_id}")
            order_book = get_order_book(client, token_id)
            if order_book is None:
                logger.error(f"Failed to fetch order book for token_id {token_id}")
                continue

            # Manage orders and get cancelled orders
            logger.info(f"Managing orders for token_id: {token_id}")
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

if __name__ == "__main__":
    main()