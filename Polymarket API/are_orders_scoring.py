import os
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrdersScoringParams
from dotenv import load_dotenv
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

def order_scoring(order_id):
    host = os.getenv("POLYMARKET_HOST")
    key = os.getenv("PRIVATE_KEY")
    creds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_SECRET"),
        api_passphrase=os.getenv("POLY_PASS_PHRASE"),
    )
    chain_id = os.getenv("CHAIN_ID")
    client = ClobClient(host, key=key, chain_id=chain_id, creds=creds)

    scoring = client.are_orders_scoring(
        OrdersScoringParams(
            orderIds=[order_id]
        )
    )
    logger.info(f"Scoring result: {scoring}")
    logger.info("Done!")
    return scoring

# This function will be called from main.py
def run_order_scoring(order_id):
    logger.info(f"Running order scoring for order ID: {order_id}")
    return order_scoring(order_id)
