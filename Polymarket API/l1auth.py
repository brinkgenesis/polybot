from py_clob_client.headers.headers import create_level_1_headers
from py_clob_client.signer import Signer
import os
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CHAIN_ID = int(os.getenv("CHAIN_ID", 137))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

def create_l1_auth_headers(nonce=None):
    if not PRIVATE_KEY:
        raise ValueError("PRIVATE_KEY must be set in the .env file")

    signer = Signer(PRIVATE_KEY, CHAIN_ID)
    headers = create_level_1_headers(signer, nonce)

    logger.info("L1 Authentication headers created successfully")
    for key, value in headers.items():
        if key == "POLY_SIGNATURE":
            logger.info(f"{key}: {value[:10]}...{value[-10:]}")
        else:
            logger.info(f"{key}: {value}")

    return headers

if __name__ == "__main__":
    try:
        headers = create_l1_auth_headers()
        print("\nGenerated L1 Headers:")
        for key, value in headers.items():
            if key == "POLY_SIGNATURE":
                print(f"{key}: {value[:10]}...{value[-10:]}")
            else:
                print(f"{key}: {value}")
    except Exception as e:
        logger.error(f"Error creating L1 authentication headers: {str(e)}")