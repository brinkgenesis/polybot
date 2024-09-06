from gamma_clob_query import main as gamma_clob_main
from bid_manager import build_and_print_order, execute_orders
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
        orders = build_and_print_order(market, gamma_market, client)

        # Ask user if they want to execute the orders
        execute = input("Do you want to execute these orders? (yes/no): ").lower().strip()
        if execute == 'yes':
            execute_orders(client, orders, market)  # Pass the original market data
        else:
            logger.info("Orders not executed.")

if __name__ == "__main__":
    main()