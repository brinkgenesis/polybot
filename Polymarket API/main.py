from gamma_clob_query import main as gamma_clob_main
import logging
from py_clob_client.client import ClobClient
import os
import dotenv

dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

from py_clob_client.client import ClobClient

client = ClobClient(
    host=os.getenv("POLY_HOST"),
    key=os.getenv("POLY_PRIVATE_KEY"),
    chain_id=os.getenv("POLY_CHAIN_ID"),
    api_key=os.getenv("POLY_API_KEY"),
    api_secret=os.getenv("POLY_API_SECRET"),
    api_passphrase=os.getenv("POLY_PASSPHRASE")
)

def main():
    # Run the existing gamma_clob_query process
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

    # The order execution is now handled within gamma_clob_main()
    # You can add any additional processing or analysis here if needed

if __name__ == "__main__":
    main()