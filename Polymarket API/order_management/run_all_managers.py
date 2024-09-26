import asyncio
from py_clob_client.client import ClobClient
from clob_client.async_clob_client import AsyncClobClient
from subgraph_client.subgraph_client import SubgraphClient
from order_management.riskManager import RiskManager
from order_management.order_manager import (
    manage_orders,
    get_order_book_sync as get_order_book,
    get_market_info_sync as get_market_info,
)
from order_management.limitOrder import main as limit_order_main
from utils.logger_config import main_logger
import config
from py_clob_client.clob_types import ApiCreds, OpenOrderParams
from utils.utils import shorten_id
import limitOrder

logger = main_logger

async def run_risk_manager(async_clob_client: AsyncClobClient, subgraph_client: SubgraphClient, token_id_queue: asyncio.Queue):
    risk_manager = RiskManager(async_clob_client, subgraph_client, token_id_queue)
    await risk_manager.run()

async def run_order_manager(clob_client: AsyncClobClient, token_id_queue: asyncio.Queue):
    while True:
        try:
            logger.info("OrderManager: Fetching open orders.")
            open_orders = await clob_client.get_orders(OpenOrderParams(asset_id=None))
            if not open_orders:
                logger.info("OrderManager: No open orders found.")
            else:
                logger.info(f"OrderManager: Processing {len(open_orders)} open orders.")
                unique_token_ids = set(order['asset_id'] for order in open_orders)
                logger.info(f"OrderManager: Processing {len(unique_token_ids)} unique token IDs.")

                # Send unique_token_ids to the queue
                await token_id_queue.put(unique_token_ids)
                
                # Additional processing can go here

            logger.info(f"OrderManager: Sleeping for {config.RISK_MONITOR_INTERVAL} seconds.")
            await asyncio.sleep(config.RISK_MONITOR_INTERVAL)

        except Exception as e:
            logger.error(f"OrderManager: Error in monitoring active orders: {e}", exc_info=True)
            logger.info(f"OrderManager: Sleeping for {config.RISK_FETCH_RETRY_DELAY} seconds before retrying.")
            await asyncio.sleep(config.RISK_FETCH_RETRY_DELAY)

async def run_limit_order():
    """Continuously runs the limitOrder.py main function with a 10-second interval."""
    while True:
        try:
            logger.info("LimitOrder: Starting a new run.")
            # Run the synchronous limit_order_main in a separate thread to avoid blocking
            await asyncio.to_thread(limitOrder.limit_order_main)
            logger.info("LimitOrder: Completed a run.")
        except Exception as e:
            logger.error(f"LimitOrder: Error during execution: {e}", exc_info=True)
        finally:
            logger.info(f"LimitOrder: Sleeping for {config.LIMIT_ORDER_INTERVAL} seconds before next run.")
            await asyncio.sleep(config.LIMIT_ORDER_INTERVAL)  # 10-second sleep

async def main():
    """Main coroutine to initialize clients and run all managers concurrently."""
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

    # Initialize the shared token_id queue
    token_id_queue = asyncio.Queue()

    try:
        # Run all managers concurrently
        await asyncio.gather(
            run_risk_manager(async_clob_client, subgraph_client, token_id_queue),
            run_order_manager(async_clob_client, token_id_queue),
            run_limit_order()
        )
    finally:
        # Perform any necessary cleanup here
        logger.info("All managers have been stopped.")
        # If SubgraphClient or other clients have cleanup methods, call them here

if __name__ == "__main__":
    asyncio.run(main())