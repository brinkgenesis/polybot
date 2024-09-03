import os
import time
import hmac
import hashlib
from dotenv import load_dotenv

load_dotenv()

POLY_ADDRESS = "POLY_ADDRESS"
POLY_SIGNATURE = "POLY_SIGNATURE"
POLY_TIMESTAMP = "POLY_TIMESTAMP"
POLY_API_KEY = "POLY_API_KEY"
POLY_PASSPHRASE = "POLY_PASSPHRASE"

def create_level_2_headers(request_path: str, method: str, body: str = ""):
    timestamp = str(int(time.time()))
    
    api_key = os.getenv("POLY_API_KEY")
    api_secret = os.getenv("POLY_API_SECRET")
    passphrase = os.getenv("POLY_PASSPHRASE")
    address = os.getenv("POLY_ADDRESS")

    if not all([api_key, api_secret, passphrase, address]):
        raise ValueError("Missing required environment variables for L2 authentication")

    message = f"{timestamp}{method}{request_path}{body}"
    signature = hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    headers = {
        POLY_ADDRESS: address,
        POLY_SIGNATURE: signature,
        POLY_TIMESTAMP: timestamp,
        POLY_API_KEY: api_key,
        POLY_PASSPHRASE: passphrase,
        "Content-Type": "application/json"
    }

    return headers

# If you want to test the function directly in this file:
if __name__ == "__main__":
    # Example usage
    request_path = "/api/v1/orders"
    method = "GET"
    headers = create_level_2_headers(request_path, method)
    print("Generated L2 Auth Headers:")
    for key, value in headers.items():
        print(f"{key}: {value}")
