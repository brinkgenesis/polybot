import asyncio
from py_clob_client.client import ClobClient
from typing import Any, Dict, List
from utils import run_sync_in_thread

class AsyncClobClient:
    def __init__(self, clob_client: ClobClient):
        self.clob_client = clob_client

    async def get_sampling_markets(self) -> List[Dict]:
        return await run_sync_in_thread(self.clob_client.get_sampling_markets)

    async def get_orders(self, params: Any) -> List[Dict]:
        """
        Asynchronously fetches orders based on the provided parameters.
        """
        return await run_sync_in_thread(lambda: self.clob_client.get_orders(params))

    async def get_market_info(self, token_id: str) -> Dict:
        """
        Asynchronously fetches market information for a given token ID.
        """
        return await run_sync_in_thread(lambda: self.clob_client.get_market_info(token_id))

    async def get_order_book(self, token_id: str) -> Dict:
        """
        Asynchronously fetches the order book for a given token ID.
        """
        return await run_sync_in_thread(lambda: self.clob_client.get_order_book(token_id))

    async def manage_orders(self, open_orders: List[Dict], token_id: str, market_info: Dict, order_book: Dict) -> List[str]:
        """
        Asynchronously manages orders based on provided parameters.
        """
        return await run_sync_in_thread(lambda: self.clob_client.manage_orders(open_orders, token_id, market_info, order_book))

    async def cancel_orders(self, order_ids: List[str]) -> Any:
        """
        Asynchronously cancels orders with the given order IDs.
        """
        return await run_sync_in_thread(lambda: self.clob_client.cancel_orders(order_ids))

    async def create_order(self, order_args: Any) -> Any:
        """
        Asynchronously creates a new order with the provided arguments.
        """
        return await run_sync_in_thread(lambda: self.clob_client.create_order(order_args))

    async def post_order(self, signed_order: Dict, order_type: Any) -> Dict:
        """
        Asynchronously posts a signed order.
        """
        return await run_sync_in_thread(lambda: self.clob_client.post_order(signed_order, order_type))