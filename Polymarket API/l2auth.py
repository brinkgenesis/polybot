from py_clob_client.headers.headers import create_level_2_headers
from py_clob_client.signer import Signer
from py_clob_client.clob_types import ApiCreds, RequestArgs
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
POLY_ADDRESS = os.getenv("POLY_ADDRESS")
POLY_API_KEY = os.getenv("POLY_API_KEY")
POLY_API_SECRET = os.getenv("POLY_API_SECRET")
POLY_PASSPHRASE = os.getenv("POLY_PASSPHRASE")

def create_l2_auth_headers(method: str, request_path: str, body=None):
    if not all([PRIVATE_KEY, POLY_API_KEY, POLY_API_SECRET, POLY_PASSPHRASE]):
        raise ValueError("All L2 authentication environment variables must be set in the .env file")

    signer = Signer(PRIVATE_KEY, CHAIN_ID)
    creds = ApiCreds(POLY_API_KEY, POLY_API_SECRET, POLY_PASSPHRASE)
    request_args = RequestArgs(method, request_path, body)

    headers = create_level_2_headers(signer, creds, request_args)

    logger.info("L2 Authentication headers created successfully")
    for key, value in headers.items():
        if key in ["POLY_SIGNATURE", "POLY_PASSPHRASE"]:
            logger.info(f"{key}: {value[:10]}...{value[-10:]}")
        else:
            logger.info(f"{key}: {value}")

    return headers

if __name__ == "__main__":
    try:
        # Example usage
        method = "GET"
        request_path = "/api/v1/markets"
        headers = create_l2_auth_headers(method, request_path)
        print("\nGenerated L2 Headers:")
        for key, value in headers.items():
            if key in ["POLY_SIGNATURE", "POLY_PASSPHRASE"]:
                print(f"{key}: {value[:10]}...{value[-10:]}")
            else:
                print(f"{key}: {value}")
    except Exception as e:
        logger.error(f"Error creating L2 authentication headers: {str(e)}")
