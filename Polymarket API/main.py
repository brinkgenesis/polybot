from gamma_client.gamma_clob_query import main as gamma_clob_main
from order_management.limitOrder import build_order, execute_orders
from shared.are_orders_scoring import run_order_scoring
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
import os
import logging
from dotenv import load_dotenv
from pprint import pprint

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def main():
    # Initialize API credentials
    apicreds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_API_SECRET"),
        api_passphrase=os.getenv("POLY_PASSPHRASE")
    )

    # Initialize ClobClient with API credentials
    client = ClobClient(
        host=os.getenv("POLYMARKET_HOST"),
        key=os.getenv("PRIVATE_KEY"),
        chain_id=int(os.getenv("CHAIN_ID")),
        creds=apicreds
    )
    pprint(vars(client))

    logger.info("ClobClient initialized successfully.")

    # Run gamma_clob_query to find markets
    matched_markets = gamma_clob_main()

    if not matched_markets:
        logger.error("No matched markets found. Exiting.")
        return

    logger.info(f"Found {len(matched_markets)} matched markets:")
    for market in matched_markets:
        logger.info(f"Question: {market['question']}")
        logger.info(f"Question ID: {market['questionID']}")
        logger.info(f"Token IDs: {market['token_ids']}")
        logger.info("-" * 50)

        # Build and print order for each matched market
        gamma_market = market['gamma_market']
        print("Building orders")
        pprint(vars(client))    
        orders = build_order(market, gamma_market, client)

        # Ask user if they want to execute the orders
        execute = input("Do you want to execute these orders? (yes/no): ").lower().strip()
        if execute == 'yes':
            execution_results = execute_orders(client, orders, market)
            
            # Check if we have a successful order execution
            successful_orders = [result for result in execution_results if result[0]]
            if successful_orders:
                order_id = successful_orders[0][1]  # Get the order ID of the first successful order
                logger.info(f"Running order scoring for order ID: {order_id}")
                scoring_result = run_order_scoring(order_id)
                logger.info(f"Order scoring result: {scoring_result}")
            else:
                logger.info("No successful orders to score.")
        else:
            logger.info("Orders not executed.")

if __name__ == "__main__":
    main()