from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
from py_clob_client.order_builder.helpers import to_token_decimals, round_down
from py_order_utils.utils import generate_seed
import time
import logging

logger = logging.getLogger(__name__)

def set_allowances(client, token_id, total_order_size):
    # Use client as passed in parameter
    usdc_address = client.collateral_token_address
    ctf_address = token_id
    exchange_address = client.exchange_address

    print(f"CTF Address: {ctf_address}")
    print(f"Exchange Address: {exchange_address}")

    # Check allowances
    usdc_allowance_ctf = client.get_collateral_allowance(ctf_address)
    print(f"USDC allowance for CTF: {usdc_allowance_ctf}")

    usdc_allowance_exchange = client.get_collateral_allowance(exchange_address)
    conditional_tokens_allowance_exchange = client.get_conditional_tokens_approval(exchange_address)

    # Calculate required allowance (10 times the total order size)
    required_allowance = int(total_order_size * 10 * 1e6)  # Assuming USDC has 6 decimal places

    # Set allowances if needed
    if usdc_allowance_ctf < required_allowance:
        txn = client.approve_collateral(ctf_address, required_allowance)
        print(f"Setting USDC allowance for CTF: {txn.transactionHash.hex()}")

    if usdc_allowance_exchange < required_allowance:
        txn = client.approve_collateral(exchange_address, required_allowance)
        print(f"Setting USDC allowance for Exchange: {txn.transactionHash.hex()}")

    if not conditional_tokens_allowance_exchange:
        txn = client.approve_conditional_tokens(exchange_address)
        print(f"Setting Conditional Tokens allowance for Exchange: {txn.transactionHash.hex()}")

    print("Allowances set")

def main(client, token_id, total_order_size):
    set_allowances(client, token_id, total_order_size)

if __name__ == "__main__":
    # Example usage
    token_id = "0x1234567890123456789012345678901234567890"  # Replace with actual token ID
    total_order_size = 100.0  # Replace with actual total order size
    main(client, token_id, total_order_size)
