import os
import logging
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, BalanceAllowanceParams, AssetType
from dotenv import load_dotenv


load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_clob_client():
    host = os.getenv("POLYMARKET_HOST")
    private_key = os.getenv("PRIVATE_KEY")
    chain_id = int(os.getenv("CHAIN_ID"))
    
    logger.info(f"Initializing ClobClient with host: {host}, chain_id: {chain_id}")
    
    creds = ApiCreds(
        api_key=os.getenv("POLY_API_KEY"),
        api_secret=os.getenv("POLY_API_SECRET"),
        api_passphrase=os.getenv("POLY_PASSPHRASE"),
    )
    client = ClobClient(host, key=private_key, chain_id=chain_id, creds=creds)
    
    logger.info("ClobClient initialized successfully")
    
    return client

def get_balance_allowances(client, market):
    logger.info("Getting balance allowances")

    # USDC (Collateral)
    collateral = client.get_balance_allowance(
        params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
    )
    logger.info(f"USDC (Collateral) balance allowance: {collateral}")

    # YES token
    yes = client.get_balance_allowance(
        params=BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL,
            token_id=market['token_ids'][0],
        )
    )
    logger.info(f"YES token balance allowance: {yes}")

    # NO token
    no = client.get_balance_allowance(
        params=BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL,
            token_id=market['token_ids'][1],
        )
    )
    logger.info(f"NO token balance allowance: {no}")

    return collateral, yes, no

def update_balance_allowance(client, market):
    logger.info("Starting balance allowance update for market")

    # Get initial balance allowances
    logger.info("Initial balance allowances:")
    get_balance_allowances(client, market)

    def log_response(asset_type, response):
        if response is None:
            logger.warning(f"{asset_type} balance allowance update returned None")
        elif isinstance(response, dict):
            logger.info(f"{asset_type} balance allowance update response: {response}")
        else:
            logger.info(f"{asset_type} balance allowance update response (type: {type(response)}): {response}")

    # USDC
    logger.info("Updating balance allowance for USDC (Collateral)")
    try:
        response = client.update_balance_allowance(
            params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        )
        log_response("USDC", response)
    except Exception as e:
        logger.error(f"Error updating USDC balance allowance: {str(e)}", exc_info=True)

    # YES
    logger.info(f"Updating balance allowance for YES token (ID: {market['token_ids'][0]})")
    try:
        response = client.update_balance_allowance(
            params=BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=market['token_ids'][0],
            )
        )
        log_response("YES token", response)
    except Exception as e:
        logger.error(f"Error updating YES token balance allowance: {str(e)}", exc_info=True)

    # NO
    logger.info(f"Updating balance allowance for NO token (ID: {market['token_ids'][1]})")
    try:
        response = client.update_balance_allowance(
            params=BalanceAllowanceParams(
                asset_type=AssetType.CONDITIONAL,
                token_id=market['token_ids'][1],
            )
        )
        log_response("NO token", response)
    except Exception as e:
        logger.error(f"Error updating NO token balance allowance: {str(e)}", exc_info=True)

    logger.info("Balance allowance update completed for market")

    # Get updated balance allowances
    logger.info("Updated balance allowances:")
    get_balance_allowances(client, market)

def main():
    client = initialize_clob_client()
    
    sample_market = {
        'token_ids': [
            101387043804718005915829260116288145378006156939179335980718677111421935985515,
            101387043804718005915829260116288145378006156939179335980718677111421935985516
        ]
    }
    
    logger.info("Starting balance allowance update with sample market data")
    update_balance_allowance(client, sample_market)
    logger.info("Balance allowance update completed for sample market")

if __name__ == "__main__":
    logger.info("update_balance_allowance.py executed directly. Running with sample data.")
    main()

