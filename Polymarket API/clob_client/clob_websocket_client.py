import asyncio
import websockets
import json
import logging
import ssl
import certifi  # Import certifi for certificate verification
from typing import Any, Callable, Dict

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ClobWebSocketClient:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url  # Use the passed ws_url
        self.connection = None
        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()

    async def connect(self):
        self.logger.info(f"Connecting to WebSocket at {self.ws_url}")
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        try:
            self.connection = await websockets.connect(self.ws_url, ssl=ssl_context)
            self.logger.info("WebSocket connection established.")
            await self.subscribe_channels()
        except websockets.InvalidStatusCode as e:
            self.logger.error(f"Failed to connect: {e}. Status code: {e.status_code}")
            raise
        except asyncio.TimeoutError:
            self.logger.error("Connection attempt timed out.")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error during WebSocket connection: {e}", exc_info=True)
            raise

    async def subscribe_channels(self):
        """
        Subscribe to required channels on the WebSocket.
        Modify this method if subscription isn't needed or requires different parameters.
        """
        # Example subscription payload for the 'market' channel
        market_channel_sub = {
            "type": "subscribe",
            "channel": "market",
            # Add additional fields if necessary
        }

        try:
            self.logger.info("Subscribing to market channel.")
            await self.connection.send(json.dumps(market_channel_sub))
            market_response = await self.connection.recv()
            self.logger.info(f"Market channel subscription response: {market_response}")
        except Exception as e:
            self.logger.error(f"Error during channel subscription: {e}", exc_info=True)
            await self.connection.close()
            raise

    async def listen(self):
        """
        Listen to incoming messages from the WebSocket.
        """
        self.logger.info("Started listening to WebSocket messages.")
        try:
            async for message in self.connection:
                self.logger.debug(f"Received message: {message}")
                # Handle incoming messages here
                # You can parse the message and perform actions or callbacks as needed
        except websockets.ConnectionClosed as e:
            self.logger.warning(f"WebSocket connection closed: {e.code} - {e.reason}")
        except Exception as e:
            self.logger.error(f"Error while listening to WebSocket: {e}", exc_info=True)
        finally:
            await self.connection.close()
            self.logger.info("WebSocket connection closed.")

    async def disconnect(self):
        """
        Gracefully close the WebSocket connection.
        """
        if self.connection and not self.connection.closed:
            await self.connection.close()
            self.logger.info("WebSocket connection has been closed.")

    async def run_async(self):
        """
        Asynchronously run the WebSocket client.
        """
        try:
            await self.connect()
            await self.listen()
        except Exception as e:
            self.logger.error(f"Failed to run WebSocket client: {e}", exc_info=True)
        finally:
            await self.disconnect()

    def run(self):
        """
        Run the WebSocket client in an asyncio event loop.
        """
        try:
            asyncio.run(self.run_async())
        except Exception as e:
            self.logger.error(f"Unhandled exception in WebSocket client: {e}", exc_info=True)
        finally:
            self.logger.info("WebSocket client has been stopped.")