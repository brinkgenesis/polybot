import os
import json
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from auth.l1auth import create_l1_auth_headers  # Using updated L1 authentication
import logging
from py_clob_client.exceptions import PolyApiException  # Ensure you import the exception class

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler and set level to info
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to ch
ch.setFormatter(formatter)

# Add ch to logger
logger.addHandler(ch)

# Load environment variables
load_dotenv()

# Set up the ClobClient
API_KEY = os.getenv("POLY_API_KEY")
API_SECRET = os.getenv("POLY_API_SECRET")
API_PASSPHRASE = os.getenv("POLY_PASSPHRASE")
POLYMARKET_HOST = os.getenv("POLYMARKET_HOST")
CHAIN_ID = int(os.getenv("CHAIN_ID", 137))  # Default to 137 if not set
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
POLYMARKET_PROXY_ADDRESS = os.getenv("POLYMARKET_PROXY_ADDRESS")

def create_api_key(nonce: int = None):
    """
    Creates a new API key using L1 Authentication.

    Parameters:
    - nonce (int, optional): Nonce value. Defaults to None.

    Returns:
        ApiCreds or None: The response containing 'apiKey', 'secret', 'passphrase' if successful; otherwise, None.
    """
    client = ClobClient(
        host=POLYMARKET_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=POLYMARKET_PROXY_ADDRESS
    )

    try:
        # Generate L1 authentication headers for the POST /auth/api-key endpoint
        headers = create_l1_auth_headers(nonce=nonce)

        # Call the create_api_key method with the nonce
        response = client.create_api_key(nonce=nonce)

        # Assuming response contains 'apiKey', 'secret', 'passphrase'
        api_key = response.api_key
        secret = response.api_secret
        passphrase = response.api_passphrase

        if api_key and secret and passphrase:
            logger.info("API Key successfully created:")
            logger.info(f"API Key: {api_key}")
            logger.info(f"Secret: {secret}")
            logger.info(f"Passphrase: {passphrase}")
            return response
        else:
            logger.error("Failed to create API key. Response:", response)
            return None

    except PolyApiException as e:
        # Dump the full JSON error response
        error_response = {
            "status_code": e.status_code,
            "error_message": e.error_msg
        }
        logger.error("Error creating API key:")
        logger.error(json.dumps(error_response, indent=2))
        return None
    except Exception as e:
        logger.error(f"Unexpected error creating API key: {str(e)}")
        return None

if __name__ == "__main__":
    # Optionally, specify a nonce or leave it as None
    response = create_api_key()