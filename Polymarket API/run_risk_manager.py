import time
from py_clob_client.client import ClobClient, OpenOrderParams
from subgraph_client import SubgraphClient
from riskManager import RiskManager
from order_manager import manage_orders, get_order_book_sync as get_order_book, get_market_info_sync as get_market_info
from logger_config import main_logger
import config
from py_clob_client.clob_types import ApiCreds

logger = main_logger

def run_risk_manager(clob_client: ClobClient, subgraph_client: SubgraphClient):
    risk_manager = RiskManager(clob_client, subgraph_client)
    risk_manager.run()

def run_order_manager(clob_client: ClobClient):
    while True:
        try:
            open_orders = clob_client.get_orders(OpenOrderParams())
            if not open_orders:
                logger.info("No open orders found.")
                time.sleep(5)
                continue

            # Assuming token_id, market_info, and order_book are obtained from other sources
            token_id = "0xMarketId1"  # Example placeholder
            market_info = get_market_info(clob_client, token_id)
            order_book = get_order_book(clob_client, token_id)

            manage_orders(clob_client, open_orders, token_id, market_info, order_book)
        except Exception as e:
            logger.error(f"Error in run_order_manager: {e}", exc_info=True)
            time.sleep(5)

def main():
    # Initialize the synchronous ClobClient
    clob_client = ClobClient(
        host=config.HOST,
        chain_id=config.CHAIN_ID,
        key=config.PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=config.POLYMARKET_PROXY_ADDRESS
    )
    
    # Set API credentials
    clob_client.set_api_creds(ApiCreds(
        api_key=config.POLY_API_KEY,
        api_secret=config.POLY_API_SECRET,
        api_passphrase=config.POLY_PASSPHRASE
    ))

    # Initialize SubgraphClient with HTTP URL
    subgraph_client = SubgraphClient(config.SUBGRAPH_HTTP_URL)  # Ensure SUBGRAPH_HTTP_URL is correct

    try:
        # Run both managers
        run_risk_manager(clob_client, subgraph_client)
        run_order_manager(clob_client)
    finally:
        # No need to close the subgraph_client as it doesn't have a close method
        pass

if __name__ == "__main__":
    main()