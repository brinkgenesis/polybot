import os
import time
from dotenv import load_dotenv
import logging
from py_clob_client.signing.eip712 import sign_clob_auth_message, get_clob_auth_domain
from py_clob_client.signing.model import ClobAuth
from py_clob_client.signer import Signer

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CHAIN_ID = int(os.getenv("CHAIN_ID", 137))
POLY_ADDRESS = os.getenv("POLY_ADDRESS")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

def create_l1_auth_headers():
    if not POLY_ADDRESS or not PRIVATE_KEY:
        raise ValueError("POLY_ADDRESS and PRIVATE_KEY must be set in the .env file")

    signer = Signer(PRIVATE_KEY, CHAIN_ID)
    timestamp = int(time.time())
    nonce = 0  # Default nonce, you might want to implement a nonce management system

    signature = sign_clob_auth_message(signer, timestamp, nonce)

    headers = {
        "POLY_ADDRESS": POLY_ADDRESS,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": str(timestamp),
        "POLY_NONCE": str(nonce)
    }

    logger.info("L1 Authentication headers created successfully")
    logger.info(f"POLY_ADDRESS: {headers['POLY_ADDRESS']}")
    logger.info(f"POLY_SIGNATURE: {headers['POLY_SIGNATURE'][:10]}...{headers['POLY_SIGNATURE'][-10:]}")
    logger.info(f"POLY_TIMESTAMP: {headers['POLY_TIMESTAMP']}")
    logger.info(f"POLY_NONCE: {headers['POLY_NONCE']}")

    return headers

if __name__ == "__main__":
    try:
        headers = create_l1_auth_headers()
        print("\nGenerated Headers:")
        for key, value in headers.items():
            if key == "POLY_SIGNATURE":
                print(f"{key}: {value[:10]}...{value[-10:]}")
            else:
                print(f"{key}: {value}")
    except Exception as e:
        logger.error(f"Error creating L1 authentication headers: {str(e)}")