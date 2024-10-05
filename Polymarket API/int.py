from py_clob_client.client import ClobClient
import os
from dotenv import load_dotenv
import logging
import time

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration parameters
HOST = "https://clob.polymarket.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 137  # Typically 137 for Polygon Mainnet
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")

# Validate essential environment variables
if not PRIVATE_KEY:
    logger.error("PRIVATE_KEY is not set in the .env file.")
    raise ValueError("PRIVATE_KEY must be set in the .env file.")

if not POLYMARKET_PROXY_ADDRESS:
    logger.error("POLYMARKET_PROXY_ADDRESS is not set in the .env file.")
    raise ValueError("POLYMARKET_PROXY_ADDRESS must be set in the .env file.")

logger.info(f"Host: {HOST}")
logger.info(f"Chain ID: {CHAIN_ID}")
logger.info(f"Private key (first 5 chars): {PRIVATE_KEY[:5]}...")

def initialize_clob_client():
    """
    Initializes and returns a ClobClient instance with proper configuration.
    """
    client = ClobClient(
        host=HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=POLYMARKET_PROXY_ADDRESS
    )
    logger.info("ClobClient initialized successfully with L1 Authentication.")
    return client

try:
    # Initialize ClobClient with necessary configurations
    clob_client = initialize_clob_client()
except Exception as e:
    logger.error(f"An unexpected error occurred during ClobClient initialization: {e}")
    raise

# Export the clob_client for use in other modules
__all__ = ['clob_client']