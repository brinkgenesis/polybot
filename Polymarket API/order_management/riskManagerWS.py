import logging
import asyncio
import threading
from typing import Any, Dict
from datetime import datetime, timedelta, timezone
import time
import config
import ssl
import certifi
import os

from clob_client.clob_websocket_client import ClobWebSocketClient
from py_clob_client.client import ClobClient, OpenOrderParams
from utils.utils import shorten_id


# Load environment variables (if using a .env file, consider using python-dotenv)
API_KEY = os.getenv("CLOB_API_KEY")
API_SECRET = os.getenv("CLOB_API_SECRET")
API_PASSPHRASE = os.getenv("CLOB_API_PASSPHRASE")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# Configure logging format
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

class RiskManagerWS:
    def __init__(self, client: ClobClient):
        self.client = client
        self.token_ids = set()
        self.cooldown_tokens: Dict[str, datetime] = {}
        self.cooldown_duration = timedelta(minutes=10)
        self.ws_client = ClobWebSocketClient(
            ws_url="wss://ws-subscriptions-clob.polymarket.com/ws/market"  # Corrected URL
        )

    def fetch_open_orders(self):
        try:
            open_orders = self.client.get_orders(OpenOrderParams())
            for order in open_orders:
                token_id = order['asset_id']
                self.token_ids.add(token_id)
            logger.info(f"Token IDs from open orders: {[shorten_id(tid) for tid in self.token_ids]}")
        except Exception as e:
            logger.error(f"Failed to fetch open orders: {e}", exc_info=True)

    def on_trade(self, trade_data: Dict[str, Any]):
        token_id = trade_data.get('tokenId')
        trade_size = float(trade_data.get('size', 0))
        trade_price = float(trade_data.get('price', 0))
        trade_value = trade_size * trade_price

        if token_id in self.token_ids:
            logger.info(f"Received trade for token {shorten_id(token_id)}: Size={trade_size}, Price={trade_price}")

            if trade_value >= 500:
                logger.info(f"Trade value ${trade_value} exceeds threshold for token {shorten_id(token_id)}")
                # Cancel orders for this token_id
                self.cancel_orders_for_token(token_id)
                # Place token_id on cooldown
                self.cooldown_tokens[token_id] = datetime.now(timezone.utc) + self.cooldown_duration
                # Remove token_id from active monitoring
                self.token_ids.remove(token_id)

    def cancel_orders_for_token(self, token_id: str):
        try:
            open_orders = self.client.get_orders(OpenOrderParams())
            orders_to_cancel = [order for order in open_orders if order['asset_id'] == token_id]
            if orders_to_cancel:
                order_ids = [order['id'] for order in orders_to_cancel]
                self.client.cancel_orders(order_ids)
                logger.info(f"Cancelled orders for token {shorten_id(token_id)}: {order_ids}")
            else:
                logger.warning(f"No open orders found for token {shorten_id(token_id)} to cancel.")
        except Exception as e:
            logger.error(f"Failed to cancel orders for token {shorten_id(token_id)}: {e}", exc_info=True)

    def check_cooldown_tokens(self):
        now = datetime.now(timezone.utc)
        for token_id, cooldown_time in list(self.cooldown_tokens.items()):
            if cooldown_time <= now:
                # Check market depth
                best_bid = self.client.get_best_bid(token_id)
                if best_bid:
                    trade_value = best_bid['price'] * best_bid['size']
                    if trade_value >= 500:
                        # Reorder logic here
                        self.place_order(token_id)
                        # Remove from cooldown
                        del self.cooldown_tokens[token_id]
                        logger.info(f"Reordered token {shorten_id(token_id)} after cooldown.")
                    else:
                        # Extend cooldown
                        self.cooldown_tokens[token_id] = now + self.cooldown_duration
                        logger.info(f"Extended cooldown for token {shorten_id(token_id)} due to insufficient trade value ${trade_value}.")
                else:
                    # If no best bid found, extend cooldown
                    self.cooldown_tokens[token_id] = now + self.cooldown_duration
                    logger.info(f"Extended cooldown for token {shorten_id(token_id)} due to missing best bid.")

    def place_order(self, token_id: str):
        # Implement your order placement logic here
        logger.info(f"Placing order for token {shorten_id(token_id)}")
        # Example placeholder:
        # size = calculate_order_size(token_id)
        # price = determine_order_price(token_id)
        # side = determine_order_side(token_id)
        # signed_order = build_order(self.client, token_id, size, price, side)
        # success, result = execute_order(self.client, signed_order)
        pass

    async def monitor_trades(self):
        try:
            await self.ws_client.connect()
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}", exc_info=True)
            return

        # Subscribe to trade events for the token_ids
        for token_id in self.token_ids:
            try:
                # Assuming the WebSocket sends trade events that are captured in the on_trade callback
                # Modify as per actual implementation
                logger.info(f"Subscribed to trade events for token {shorten_id(token_id)}.")
            except Exception as e:
                logger.error(f"Failed to subscribe to trades for token {shorten_id(token_id)}: {e}", exc_info=True)

        # Keep the websocket connection alive
        try:
            await self.ws_client.listen()
        except Exception as e:
            logger.error(f"Error while listening to WebSocket: {e}", exc_info=True)

    def run(self):
        # Fetch open orders and get token IDs
        self.fetch_open_orders()

        if not self.token_ids:
            logger.warning("No token IDs found in open orders. Exiting RiskManagerWS.")
            return

        # Start the websocket event loop in a separate thread
        loop = asyncio.new_event_loop()
        thread = threading.Thread(target=loop.run_until_complete, args=(self.monitor_trades(),), daemon=True)
        thread.start()

        # Periodically check cooldown tokens
        try:
            while True:
                self.check_cooldown_tokens()
                # Sleep for a minute before checking again
                time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutting down RiskManagerWS...")
            # Close websocket connection
            loop.call_soon_threadsafe(loop.stop)
            self.ws_client.connection.close()
            thread.join()
            logger.info("RiskManagerWS shutdown complete.")

def main():
    logging.basicConfig(level=logging.INFO)

    client = ClobClient(
        host=config.POLYMARKET_HOST,
        chain_id=config.CHAIN_ID,
        key=config.PRIVATE_KEY,
        signature_type=2,  # POLY_GNOSIS_SAFE
        funder=config.POLYMARKET_PROXY_ADDRESS
    )
    client.set_api_creds(client.create_or_derive_api_creds())
    risk_manager = RiskManagerWS(client)
    risk_manager.run()

if __name__ == "__main__":
    main()