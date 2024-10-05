from int import clob_client
import logging
import json
import time
from py_clob_client.exceptions import PolyApiException
from py_clob_client.headers.headers import create_level_1_headers
from py_clob_client.signer import Signer
import os
from dotenv import load_dotenv

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create console handler and set level to info
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to ch
ch.setFormatter(formatter)

# Add handler to logger
logger.addHandler(ch)

# Load environment variables
load_dotenv()

# Retrieve necessary environment variables
CHAIN_ID = int(os.getenv("CHAIN_ID", 137))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

def create_l1_auth_headers(nonce: int = None) -> dict:
    """
    Creates L1 Authentication headers required for API requests that need L1 Authentication.

    Parameters:
    - nonce (int, optional): Nonce value. Defaults to None.

    Returns:
    - dict: A dictionary containing the necessary L1 authentication headers.
    """
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

def create_api_key():
    """
    Creates a new API key using L1 Authentication.

    Returns:
        dict or None: A dictionary containing 'apiKey', 'secret', 'passphrase' if successful; otherwise, None.
    """
    try:
        # Generate a unique nonce based on current time in milliseconds
        nonce = int(time.time() * 1000)
        logger.info(f"Using nonce: {nonce}")

        # Create L1 Authentication headers
        headers = create_l1_auth_headers(nonce=nonce)

        # Attempt to create the API key
        response = clob_client.create_api_key(nonce=nonce)

        # Extract credentials from response
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
            logger.error("Failed to create API key. Response:")
            logger.error(json.dumps(response.__dict__, indent=2))
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
    # Create the API key
    creds = create_api_key()

    if creds:
        print("\nCreated API Credentials:")
        print(json.dumps({
            "api_key": creds.api_key,
            "secret": creds.api_secret,
            "passphrase": creds.api_passphrase
        }, indent=2))
    else:
        print("API key creation failed.")