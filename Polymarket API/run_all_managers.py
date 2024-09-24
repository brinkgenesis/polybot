import asyncio
from py_clob_client.client import ClobClient
from async_clob_client import AsyncClobClient
from subgraph_client import SubgraphClient
from riskManager import RiskManager
from order_manager import manage_orders, get_order_book, get_market_info
from logger_config import main_logger
import config
from py_clob_client.clob_types import ApiCreds, OpenOrderParams
from utils import shorten_id


logger = main_logger

async def run_risk_manager(clob_client: AsyncClobClient, subgraph_client: SubgraphClient):
    risk_manager = RiskManager(clob_client, subgraph_client)
    await risk_manager.run()

async def run_order_manager(clob_client: AsyncClobClient):
    while True:
        try:
            open_orders = await clob_client.get_orders(OpenOrderParams())  # Ensure OpenOrderParams is correctly defined
            if not open_orders:
                logger.info("OrderManager: No open orders found.")
                await asyncio.sleep(config.RISK_MONITOR_INTERVAL)
                continue

            unique_token_ids = set(order['asset_id'] for order in open_orders)
            logger.info(f"OrderManager: Processing {len(unique_token_ids)} unique token IDs.")

            for token_id in unique_token_ids:
                logger.info(f"OrderManager: Processing token_id: {shorten_id(token_id)}")
                order_book = await get_order_book(clob_client, token_id)
                if order_book is None:
                    continue

                market_info = await get_market_info(clob_client, token_id)  # Ensure this is async and properly wrapped
                cancelled_orders = await manage_orders(clob_client, open_orders, token_id, market_info, order_book)
                
                for order_id in cancelled_orders:
                    # Implement any additional logic if needed
                    pass

            await asyncio.sleep(config.RISK_MONITOR_INTERVAL)
        except Exception as e:
            logger.error(f"OrderManager: Error in monitoring active orders: {e}", exc_info=True)
            await asyncio.sleep(config.RISK_FETCH_RETRY_DELAY)

async def main():
    # Initialize the synchronous ClobClient
    clob_client_sync = ClobClient(
        host=config.HOST,
        chain_id=config.CHAIN_ID,
        key=config.PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=config.POLYMARKET_PROXY_ADDRESS
    )
    
    # Wrap it with AsyncClobClient
    async_clob_client = AsyncClobClient(clob_client_sync)

    # Set API credentials asynchronously
    await async_clob_client.set_api_creds(ApiCreds(
        api_key=config.POLY_API_KEY,
        api_secret=config.POLY_API_SECRET,
        api_passphrase=config.POLY_PASSPHRASE
    ))

    # Initialize SubgraphClient with HTTP URL
    subgraph_client = SubgraphClient(config.SUBGRAPH_HTTP_URL)

    try:
        # Run both managers concurrently
        await asyncio.gather(
            run_risk_manager(async_clob_client, subgraph_client),
            run_order_manager(async_clob_client)
        )
    finally:
        # Ensure proper closure if necessary
        # Since WebSocket is disabled, no need to close it
        # Close SubgraphClient's session if required based on its implementation
        pass  # Or implement any necessary cleanup

if __name__ == "__main__":
    asyncio.run(main())