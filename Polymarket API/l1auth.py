from eth_account import Account
from eth_account.messages import encode_defunct
import time
import os
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

POLY_ADDRESS = "POLY_ADDRESS"
POLY_SIGNATURE = "POLY_SIGNATURE"
POLY_TIMESTAMP = "POLY_TIMESTAMP"
POLY_NONCE = "POLY_NONCE"
CHAIN_ID = int(os.getenv("CHAIN_ID", 137))  # Default to Polygon Mainnet if not specified

class Signer:
    def __init__(self, private_key: str):
        self.account = Account.from_key(private_key)

    def address(self):
        return self.account.address

    def sign_message(self, message: str):
        message_hash = encode_defunct(text=message)
        return self.account.sign_message(message_hash)

def create_level_1_headers(signer: Signer, chain_id: int, nonce: int = 0):
    timestamp = str(int(time.time()))

    message = "This message attests that I control the given wallet"
    signature = signer.sign_message(message).signature.hex()

    headers = {
        POLY_ADDRESS: signer.address().lower(),
        POLY_SIGNATURE: signature,
        POLY_TIMESTAMP: timestamp,
        POLY_NONCE: str(nonce),
        "Content-Type": "application/json"
    }

    # Log the generated headers with masked sensitive information
    masked_headers = headers.copy()
    masked_headers[POLY_SIGNATURE] = f"{signature[:10]}...{signature[-10:]}"
    logger.info(f"Generated L1 Auth Headers: {masked_headers}")

    return headers

if __name__ == "__main__":
    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not found in environment variables")
    else:
        signer = Signer(private_key)
        headers = create_level_1_headers(signer, CHAIN_ID)
        logger.info("L1 Auth Headers generated successfully")