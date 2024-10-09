import os
import logging
from py_clob_client.client import ClobClient, OpenOrderParams, ApiCreds

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def fetch_open_orders():
    """
    Fetch open orders from the Polymarket CLOB API and print the response details.
    """
    # Load environment variables
    creds = {
        'api_key': os.getenv("POLY_API_KEY"),
        'api_secret': os.getenv("POLY_API_SECRET"),
        'api_passphrase': os.getenv("POLY_API_PASSPHRASE")
    }
    POLYMARKET_HOST = os.getenv("POLYMARKET_HOST", "https://clob.polymarket.com")
    CHAIN_ID = os.getenv("CHAIN_ID")
    PRIVATE_KEY = os.getenv("PRIVATE_KEY")
    POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")
    
    # Initialize ClobClient
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=POLYMARKET_PROXY_ADDRESS
    )
    try:
        creds = ApiCreds(
        api_key = str(os.getenv("POLY_API_KEY")),
        api_secret= str(os.getenv("POLY_API_SECRET")),
        api_passphrase= str(os.getenv("POLY_PASSPHRASE"))
    ) 
        client.set_api_creds(creds)
        logger.info("ClobClient initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to set API credentials: {e}", exc_info=True)
        return
    
    try:
        open_orders = client.get_orders(OpenOrderParams())
        logger.info(f"Retrieved {len(open_orders)} open orders.")
        logger.debug(f"Open Orders: {open_orders}")
    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")

if __name__ == "__main__":
    fetch_open_orders()