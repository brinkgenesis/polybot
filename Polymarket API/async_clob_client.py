import asyncio
from decimal import Decimal
from typing import List, Dict, Any
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OpenOrderParams, BookParams
from logger_config import main_logger

logger = main_logger

class AsyncClobClient:
    def __init__(
        self,
        host: str,
        chain_id: int,
        key: str,
        signature_type: int,
        funder: str
    ):
        self.sync_client = ClobClient(
            host=host,
            chain_id=chain_id,
            key=key,
            signature_type=signature_type,
            funder=funder
        )

    async def set_api_creds(self, creds: ApiCreds):
        """
        Asynchronously sets the API credentials.
        """
        try:
            await asyncio.to_thread(self.sync_client.set_api_creds, creds)
            logger.info("API credentials set successfully.")
        except Exception as e:
            logger.error(f"Error setting API credentials: {e}", exc_info=True)
            raise

    async def get_orders(self, params: OpenOrderParams) -> List[Dict[str, Any]]:
        """
        Asynchronously fetches active orders based on the provided parameters.
        """
        try:
            orders = await asyncio.to_thread(self.sync_client.get_orders, params)
            return orders
        except Exception as e:
            logger.error(f"Error fetching orders: {e}", exc_info=True)
            return []

    async def build_order(
        self, 
        token_id: str, 
        size: Decimal, 
        price: Decimal, 
        side: str
    ) -> Dict[str, Any]:
        """
        Asynchronously builds a signed order.
        """
        try:
            signed_order = await asyncio.to_thread(
                self.sync_client.build_order, 
                token_id, 
                size, 
                price, 
                side
            )
            return signed_order
        except Exception as e:
            logger.error(f"Error building order: {e}", exc_info=True)
            raise

    async def execute_order(self, signed_order: Dict[str, Any]) -> str:
        """
        Asynchronously executes a signed order and returns the order ID.
        """
        try:
            order_id = await asyncio.to_thread(
                self.sync_client.execute_order, 
                signed_order
            )
            return order_id
        except Exception as e:
            logger.error(f"Error executing order: {e}", exc_info=True)
            raise

    async def cancel_orders(self, order_ids: List[str], token_id: str) -> List[str]:
        """
        Asynchronously cancels multiple orders.
        """
        try:
            cancelled_order_ids = await asyncio.to_thread(
                self.sync_client.cancel_orders, 
                order_ids
            )
            logger.info(f"Cancelled orders: {cancelled_order_ids}")
            return cancelled_order_ids
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}", exc_info=True)
            return []

    async def get_order_book(self, token_id: str) -> Dict[str, Any]:
        """
        Asynchronously fetches the order book for a given token ID.
        """
        try:
            order_book = await asyncio.to_thread(
                self.sync_client.get_order_book, 
                token_id
            )
            return order_book
        except Exception as e:
            logger.error(f"Error fetching order book for {token_id}: {e}", exc_info=True)
            return {}
    
    # Add other methods following the same pattern...