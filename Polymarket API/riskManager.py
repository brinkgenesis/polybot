import asyncio
import json
import time
import config
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Callable, Dict
from gql import gql

from utils import shorten_id
from order_manager import cancel_orders, reorder, get_order_book, manage_orders
from subgraph_client import SubgraphClient
from logger_config import main_logger
from async_clob_client import AsyncClobClient
from typing import List


# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = main_logger

class RiskManager:
    def __init__(self, clob_client: AsyncClobClient, subgraph_client: SubgraphClient):
        self.clob_client = clob_client
        self.subgraph_client = subgraph_client
        self.volatility_cooldown = {}
        self.logger = logger

        # RiskManager parameters
        self.VOLUME_THRESHOLD = config.RISK_VOLUME_THRESHOLD
        self.VOLATILITY_COOLDOWN_PERIOD = config.RISK_VOLATILITY_COOLDOWN_PERIOD
        self.INACTIVITY_THRESHOLD = config.RISK_INACTIVITY_THRESHOLD
        self.OPEN_INTEREST_THRESHOLD = config.RISK_OPEN_INTEREST_THRESHOLD
        self.HIGH_ACTIVITY_THRESHOLD_PERCENT = config.RISK_HIGH_ACTIVITY_THRESHOLD_PERCENT

        # Cooldown tracking
        self.cooldown_duration = config.RISK_VOLATILITY_COOLDOWN_PERIOD  # 10 minutes

    async def cancel_and_cooldown_order(self, order_id: str, market_id: str):
        """
        Cancels the specified order and marks the market for cooldown.
        """
        try:
            await self.clob_client.cancel_orders([order_id])
            self.volatility_cooldown[market_id] = asyncio.get_event_loop().time() + self.cooldown_duration
            self.logger.info(f"Cancelled order: {shorten_id(order_id)} for market {shorten_id(market_id)}")
            self.logger.info(f"Set volatility cooldown for market {shorten_id(market_id)} until {self.volatility_cooldown[market_id]}")
        except Exception as e:
            self.logger.error(f"Error cancelling order {shorten_id(order_id)}: {e}", exc_info=True)

    async def monitor_subgraph(self):
        """
        Monitors the subgraph for large orders and triggers cancellation logic.
        """
        while True:
            try:
                large_orders = await self.subgraph_client.get_large_orders(config.RISK_VOLUME_THRESHOLD)
                if large_orders:
                    for trade in large_orders:
                        order_id = trade["id"]
                        market_id = trade["market"]

                        side = trade.get("side", "").upper()
                        outcome = trade.get("outcome", "")

                        size = float(trade.get("size", 0))
                        price = float(trade.get("price", 0))
                        total_order = size * price

                        if total_order > config.RISK_VOLUME_THRESHOLD and ((side == "SELL" and outcome == "YES") or (side == "BUY" and outcome == "NO")):
                            if market_id not in self.volatility_cooldown:
                                self.logger.warning(f"Subgraph detected large order: {order_id} in market {shorten_id(market_id)}")
                                await self.cancel_and_cooldown_order(order_id, market_id)
                else:
                    self.logger.info("No large orders detected in Subgraph query.")

                await asyncio.sleep(300)  # Poll every 5 minutes
            except Exception as e:
                self.logger.error(f"Error in monitor_subgraph: {e}", exc_info=True)
                await asyncio.sleep(config.RISK_FETCH_RETRY_DELAY)

async def handle_order_cancellation(self, cancelled_order: dict):
    """
    Handles the logic after an order has been cancelled.

    :param cancelled_order: The order that was cancelled.
    """
    token_id = cancelled_order['asset_id']
    # Assume get_order_book is an asynchronous method
    order_book = await self.clob_client.get_order_book(token_id)
    market_info = self.get_market_info(order_book)  # Fetch the latest market info

    new_order_ids: List[str] = await reorder(
        client=self.clob_client, 
        cancelled_order=cancelled_order, 
        token_id=token_id, 
        market_info=market_info
    )

    if new_order_ids:
        logger.info(f"Reordered with new orders: {new_order_ids}")
    else:
        logger.warning("Reorder failed or no new orders were created.")

    async def run(self):
        """
        Runs the RiskManager's monitoring tasks.
        """
        await self.monitor_subgraph()





