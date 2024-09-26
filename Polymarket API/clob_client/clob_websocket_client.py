import websockets
import asyncio
import json
import threading
from py_clob_client.client import ClobClient
import logging
from utils.utils import run_sync_in_thread

 

# class ClobWebsocketClient:
#     def __init__(self, clob_client: ClobClient, uri: str = "wss://clob.polymarket.com/ws"):
#         """
#            Initializes the WebSocket client for the CLOB.
#
#            :param clob_client: Instance of ClobClient.
#            :param uri: WebSocket URI for the CLOB.
#            """
#         self.clob_client = clob_client
#         self.uri = uri
#         self.logger = logging.getLogger(self.__class__.__name__)
#         self.websocket = None
#
#     async def connect(self):
#         """
#         Establishes the WebSocket connection.
#            """
#         try:
#             self.websocket = await websockets.connect(self.uri)
#             self.logger.info("Connected to WebSocket.")
#         except Exception as e:
#             self.logger.error(f"Failed to connect to WebSocket: {e}", exc_info=True)
#
#     async def subscribe_to_market_channel(self, market_id: str):
#            """
#            Subscribes to the market channel for a specific market ID.
#
#            :param market_id: The market ID to subscribe to.
#            """
#            subscription_message = json.dumps({
#                "type": "subscribe",
#                "channel": "market",
#                "market": market_id
#            })
#            try:
#                await self.websocket.send(subscription_message)
#                self.logger.info(f"Subscribed to market channel: {market_id}")
#            except Exception as e:
#                self.logger.error(f"Failed to subscribe to market channel {market_id}: {e}", exc_info=True)
#
#     async def market_websocket(self):
#            """
#            Asynchronously listens to the WebSocket for market events.
#
#            Yields:
#                Messages received from the WebSocket.
#            """
#            await self.connect()
#            # Subscribe to all relevant market channels
#            markets = await run_sync_in_thread(self.clob_client.get_sampling_markets)
#            for market in markets:
#                await self.subscribe_to_market_channel(market['token_id'])
#            
#            try:
#                async for message in self.websocket:
#                    yield message
#            except websockets.ConnectionClosed:
#                self.logger.warning("WebSocket connection closed.")
#            except Exception as e:
#                self.logger.error(f"Error in WebSocket connection: {e}", exc_info=True)
