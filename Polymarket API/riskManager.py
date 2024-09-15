import asyncio
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
from py_clob_client.clob_types import OpenOrderParams, OrderType, OrderArgs
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from logger_config import main_logger


# Load environment variables from .env file
load_dotenv()

# Configure logging
logger = main_logger

class RiskManager:
    def __init__(self, clob_client: 'ClobClient', subgraph_client: SubgraphClient):
        self.clob_client = clob_client
        self.subgraph_client = subgraph_client
        self.volatility_cooldown: Dict[str, float] = {}
        self.logger = logger

        # RiskManager parameters
        self.VOLUME_THRESHOLD = config.RISK_VOLUME_THRESHOLD
        self.VOLATILITY_COOLDOWN_PERIOD = config.RISK_VOLATILITY_COOLDOWN_PERIOD
        self.INACTIVITY_THRESHOLD = config.RISK_INACTIVITY_THRESHOLD
        self.OPEN_INTEREST_THRESHOLD = config.RISK_OPEN_INTEREST_THRESHOLD
        self.HIGH_ACTIVITY_THRESHOLD_PERCENT = config.RISK_HIGH_ACTIVITY_THRESHOLD_PERCENT

    async def subscribe_to_large_trades(self, token_id: str, min_total_order: float):
        subscription_query = '''
        subscription onLargeTrade($market: String!, $minAmount: Float!) {
          trades(
            where: { 
              market: $market,
              tradeAmount_gt: $minAmount
            }
            orderBy: timestamp
            orderDirection: desc
          ) {
            id
            timestamp
            market
            type
            tradeAmount
            outcomeIndex
            outcomeTokensAmount
          }
        }
        '''

        variables = {
            "market": token_id,
            "minAmount": min_total_order
        }

        async for trade in self.subgraph_client.subscribe_to_events(subscription_query, variables):
            if float(trade.get('tradeAmount', 0)) > min_total_order:
                self.logger.warning(
                    f"Trade ID {trade.get('id')} exceeds thresholds. Initiating risk mitigation."
                )
                await self.handle_large_trade(trade)

    async def handle_large_trade(self, trade: Dict):
        """
        Processes largeTrade events that meet the specified conditions.

        :param trade: The trade event data dictionary from the subgraph.
        """
        try:
            market_id = trade['market']
            total_order = float(trade['amount']) * float(trade['price'])

            self.logger.info(
                f"Handling Large Trade: Market {shorten_id(market_id)}, "
                f"Total Order ${total_order:.2f}"
            )

            # Cancel all orders for this market
            open_orders = self.clob_client.get_orders(OpenOrderParams())
            orders_to_cancel = [order['id'] for order in open_orders if order['asset_id'] == market_id]
            
            if orders_to_cancel:
                self.clob_client.cancel_orders(orders_to_cancel)
                self.logger.info(f"Cancelled orders: {[shorten_id(order_id) for order_id in orders_to_cancel]}")

            # Set volatility cooldown
            self.volatility_cooldown[market_id] = time.time() + self.VOLATILITY_COOLDOWN_PERIOD
            self.logger.info(f"Set volatility cooldown for market {shorten_id(market_id)} until {self.volatility_cooldown[market_id]}")

        except Exception as e:
            self.logger.error(f"Error handling large trade for market {shorten_id(market_id)}: {e}", exc_info=True)

    async def monitor_active_orders(self):
        while True:
            try:
                open_orders = self.clob_client.get_orders(OpenOrderParams())
                if not open_orders:
                    self.logger.info("No open orders found.")
                    await asyncio.sleep(config.RISK_MONITOR_INTERVAL)
                    continue

                unique_token_ids = set(order['asset_id'] for order in open_orders)
                self.logger.info(f"Processing {len(unique_token_ids)} unique token IDs.")
                all_cancelled_orders = []

                for token_id in unique_token_ids:
                    self.logger.info(f"Processing token_id: {shorten_id(token_id)}")
                    
                    # Check if market is in volatility cooldown
                    if token_id in self.volatility_cooldown:
                        if time.time() < self.volatility_cooldown[token_id]:
                            self.logger.info(f"Market {shorten_id(token_id)} is in volatility cooldown. Skipping.")
                            continue
                        else:
                            self.logger.info(f"Volatility cooldown ended for market {shorten_id(token_id)}.")
                            del self.volatility_cooldown[token_id]

                    order_book = get_order_book(self.clob_client, token_id)
                    if order_book is None:
                        continue

                    market_info = self.get_market_info(order_book)
                    cancelled_orders = manage_orders(self.clob_client, open_orders, token_id, market_info, order_book)
                    all_cancelled_orders.extend([(order_id, token_id, market_info) for order_id in cancelled_orders])

                # Reorder cancelled orders
                for cancelled_order_id, token_id, market_info in all_cancelled_orders:
                    cancelled_order = next((order for order in open_orders if order['id'] == cancelled_order_id), None)
                    if cancelled_order:
                        order_data = {
                            'side': cancelled_order['side'],
                            'size': cancelled_order['original_size'],
                            'token_id': token_id
                        }
                        await reorder(self.clob_client, order_data, token_id, market_info)

                await asyncio.sleep(config.RISK_MONITOR_INTERVAL)

            except Exception as e:
                self.logger.error(f"Error in monitoring active orders: {e}", exc_info=True)
                await asyncio.sleep(config.RISK_FETCH_RETRY_DELAY)

    def get_market_info(self, order_book):
        sorted_bids = sorted(order_book.bids, key=lambda x: float(x.price), reverse=True)
        sorted_asks = sorted(order_book.asks, key=lambda x: float(x.price))
        best_bid = float(sorted_bids[0].price) if sorted_bids else 0
        best_ask = float(sorted_asks[0].price) if sorted_asks else 0
        return {
            'best_bid': best_bid,
            'best_ask': best_ask,
            'tick_size': getattr(config, 'TICK_SIZE', 0.01),  # Default to 0.01 if not defined
            'max_incentive_spread': getattr(config, 'MAX_INCENTIVE_SPREAD', 0.05)  # Default to 0.05 if not defined
        }

    async def main(self):
        try:
            # Fetch open orders
            open_orders = self.clob_client.get_orders(OpenOrderParams())
            token_ids = list({order['asset_id'] for order in open_orders})
            
            # Subscribe to large trades for markets with open orders
            for token_id in token_ids:
                asyncio.create_task(
                    self.subscribe_to_large_trades(
                        token_id=token_id,
                        min_total_order=self.VOLUME_THRESHOLD
                    )
                )

            # Start monitoring active orders
            asyncio.create_task(self.monitor_active_orders())

            # Keep the main coroutine running
            while True:
                await asyncio.sleep(3600)

        except Exception as e:
            self.logger.error(f"Error in main RiskManager loop: {e}", exc_info=True)

if __name__ == "__main__":
    
    async def run():
        clob_client = ClobClient(
            host=config.HOST,
            chain_id=config.CHAIN_ID,
            key=config.PRIVATE_KEY,
            signature_type=2,  # Example signature type
            funder=config.POLYMARKET_PROXY_ADDRESS
        )
        clob_client.set_api_creds(ApiCreds(
            api_key=config.POLY_API_KEY,
            api_secret=config.POLY_API_SECRET,
            api_passphrase=config.POLY_PASSPHRASE
        ))

        subgraph_client = SubgraphClient(config.SUBGRAPH_URL)
        
        risk_manager = RiskManager(clob_client, subgraph_client)
        await risk_manager.main()

    asyncio.run(run())





