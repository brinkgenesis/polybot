import asyncio
from py_clob_client.client import ClobClient, OpenOrderParams
from async_clob_client import AsyncClobClient
from subgraph_client import SubgraphClient
from riskManager import RiskManager
from order_manager import manage_orders, get_order_book, get_market_info
from logger_config import main_logger
import config
from py_clob_client.clob_types import ApiCreds

logger = main_logger


async def run_risk_manager(clob_client: AsyncClobClient, subgraph_client: SubgraphClient):
    risk_manager = RiskManager(clob_client, subgraph_client)
    await risk_manager.run()


async def run_order_manager(clob_client: AsyncClobClient):
    while True:
        try:
            open_orders = await clob_client.get_orders(OpenOrderParams())  # Ensure OpenOrderParams is correctly defined
            if not open_orders:
                logger.info("No open orders found.")
                await asyncio.sleep(5)
                continue

            # Assuming token_id, market_info, and order_book are obtained from other sources
            token_id = "0xMarketId1"  # Example placeholder
            market_info = await clob_client.get_market_info(token_id)  # Ensure get_market_info is wrapped
            order_book = await clob_client.get_order_book(token_id)  # Ensure get_order_book is wrapped

            await manage_orders(clob_client, open_orders, token_id, market_info, order_book)

        except Exception as e:
            logger.error(f"Error in managing orders: {e}", exc_info=True)
            await asyncio.sleep(5)  # Wait before retrying


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
        await subgraph_client.client.close()  # Ensure the gql Client is closed properly
        # Note: Unable to close clob_client's session as the library does not expose it


if __name__ == "__main__":
    asyncio.run(main())