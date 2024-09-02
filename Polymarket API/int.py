from py_clob_client.client import ClobClient
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

host = "https://clob.polymarket.com"
private_key = os.getenv("PRIVATE_KEY")
chain_id = 137

print(f"Host: {host}")
print(f"Chain ID: {chain_id}")
print(f"Private key (first 5 chars): {private_key[:5]}..." if private_key else "Private key not set")

def initialize_clob_client():
    if not private_key:
        raise ValueError("Private key must be set in the .env file")
    
    return ClobClient(host, key=private_key, chain_id=chain_id)

try:
    # Initialize ClobClient for read-only operations
    clob_client = initialize_clob_client()
    print("\nClobClient initialized successfully for read-only operations.")
except Exception as e:
    print(f"An unexpected error occurred: {e}")

# Export the clob_client
__all__ = ['clob_client']