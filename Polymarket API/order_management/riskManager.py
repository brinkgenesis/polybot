import json
import time
import config
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import Callable, Dict
from gql import gql
import sys
from order_management.order_manager import (
    manage_orders,
    get_order_book_sync as get_order_book,
    get_market_info_sync as get_market_info,
    reorder,
)
from subgraph_client.subgraph_client import SubgraphClient
from utils.utils import shorten_id
from utils.logger_config import main_logger
from py_clob_client.client import ClobClient
from typing import List
from time import sleep



# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = main_logger

class RiskManager:
    def __init__(self, clob_client: ClobClient, subgraph_client: SubgraphClient):
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

    def cancel_orders(self, order_ids: List[str]):
        try:
            cancelled_orders = self.clob_client.cancel_orders(order_ids)
            return cancelled_orders
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}", exc_info=True)
            return []

    def cancel_and_cooldown_order(self, order_id: str, market_id: str):
        """
        Cancels the specified order and marks the market for cooldown.
        """
        try:
            self.clob_client.cancel_orders([order_id])
            self.volatility_cooldown[market_id] = time.time() + self.cooldown_duration
            self.logger.info(f"Cancelled order: {shorten_id(order_id)} for market {shorten_id(market_id)}")
            self.logger.info(f"Set volatility cooldown for market {shorten_id(market_id)} until {self.volatility_cooldown[market_id]}")
        except Exception as e:
            self.logger.error(f"Error cancelling order {shorten_id(order_id)}: {e}", exc_info=True)

    def monitor_subgraph(self):
        """
        Monitors the subgraph for large orders and triggers cancellation logic.
        """
        while True:
            try:
                large_orders = self.subgraph_client.get_large_orders(config.RISK_VOLUME_THRESHOLD)
                
                if large_orders:
                    self.logger.info(f"Fetched {len(large_orders)} large orders from Subgraph.")
                    for trade in large_orders:
                        try:
                            # Extract necessary fields with defaults
                            order_id = trade.get("id")
                            market_data = trade.get("market")
                            if isinstance(market_data, dict):
                                market_id = market_data.get("id")
                            else:
                                market_id = trade.get("market")
                            side = trade.get("side", "").upper()
                            outcome = trade.get("outcome", "").upper()
                            size = float(trade.get("tradeAmount", 0))  # Assuming 'tradeAmount' is the size
                            price = float(trade.get("price", 0))
                            total_order = size * price

                            # Validate extracted data
                            if not all([order_id, market_id, side, outcome, size, price]):
                                self.logger.warning(f"Incomplete trade data: {trade}")
                                continue

                            # Apply risk logic
                            if (total_order > self.VOLUME_THRESHOLD and 
                                ((side == "SELL" and outcome == "YES") or 
                                 (side == "BUY" and outcome == "NO"))):
                                
                                if market_id not in self.volatility_cooldown:
                                    self.logger.warning(
                                        f"Subgraph detected large order: {shorten_id(order_id)} in market {shorten_id(market_id)}"
                                    )
                                    self.cancel_and_cooldown_order(order_id, market_id)
                        except Exception as trade_e:
                            self.logger.error(f"Error processing trade data: {trade_e}", exc_info=True)
                else:
                    self.logger.info("No large orders detected in Subgraph query.")

                sleep(300)  # Poll every 5 minutes
            except Exception as e:
                self.logger.error(f"Error in monitor_subgraph: {e}", exc_info=True)
                sleep(config.RISK_FETCH_RETRY_DELAY)

    def run(self):
        """
        Runs the RiskManager's monitoring tasks.
        """
        self.monitor_subgraph()





