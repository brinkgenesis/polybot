import os
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from l1auth import create_l1_auth_headers

# Load environment variables
load_dotenv()

# Set up the ClobClient
HOST = "https://clob.polymarket.com"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
CHAIN_ID = 137

def derive_api_key():
    # Initialize the ClobClient
    clob_client = ClobClient(HOST, key=PRIVATE_KEY, chain_id=CHAIN_ID)
    
    # Get L1 authentication headers
    l1_headers = create_l1_auth_headers()
    
    try:
        # Extract necessary information from L1 headers
        address = l1_headers["POLY_ADDRESS"]
        signature = l1_headers["POLY_SIGNATURE"]
        timestamp = int(l1_headers["POLY_TIMESTAMP"])
        nonce = int(l1_headers["POLY_NONCE"])

        # Derive API key
        creds = clob_client.derive_api_key(address=address, signature=signature, timestamp=timestamp, nonce=nonce)
        return creds
    except Exception as e:
        print(f"Error deriving API key: {str(e)}")
        return None

if __name__ == "__main__":
    creds = derive_api_key()
    if creds:
        print("API Credentials:")
        print(f"API Key: {creds['apiKey']}")
        print(f"Secret: {creds['secret'][:10]}...{creds['secret'][-10:]}")
        print(f"Passphrase: {creds['passphrase'][:10]}...{creds['passphrase'][-10:]}")
    else:
        print("Failed to derive API key.")