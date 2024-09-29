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
    def __init__(self, ws_url: str, asset_ids: list, message_handler: Callable[[Dict[str, Any]], Any]):
        self.ws_url = ws_url  # WebSocket URL
        self.asset_ids = asset_ids  # List of asset IDs to subscribe to
        self.connection = None
        self.logger = logging.getLogger(__name__)
        self.stop_event = asyncio.Event()
        self.message_handler = message_handler  # Callback for handling messages

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
            self.logger.error(f"Unexpected error during connection: {e}", exc_info=True)
            raise

    async def subscribe_channels(self):
        """
        Subscribe to the market channel with the provided asset_ids.
        """
        # Corrected subscription payload with snake_case
        market_channel_sub = {
            "asset_ids": self.asset_ids,  # Use 'asset_ids' with snake_case
            "type": "Market"
        }

        try:
            self.logger.info("Subscribing to market channel with payload:")
            self.logger.debug(json.dumps(market_channel_sub, indent=2))
            await self.connection.send(json.dumps(market_channel_sub))

            # Attempt to receive any server response
            try:
                market_response = await self.connection.recv()
                self.logger.info(f"Market channel subscription response: {market_response}")
            except websockets.ConnectionClosedError as e:
                self.logger.error(f"Connection closed unexpectedly during subscription: {e.code} - {e.reason}")
                # Attempt to read any final message
                try:
                    message = await self.connection.recv()
                    self.logger.error(f"Received message before close: {message}")
                except Exception:
                    pass
                raise
        except Exception as e:
            self.logger.error(f"Error during channel subscription: {e}", exc_info=True)
            await self.disconnect()
            raise

    async def listen(self):
        self.logger.info("Started listening to WebSocket messages.")
        try:
            async for message in self.connection:
                data = json.loads(message)
                # Handle incoming messages using the provided callback
                await self.message_handler(data)
        except websockets.ConnectionClosed as e:
            self.logger.warning(f"WebSocket connection closed: {e.code} - {e.reason}")
        except Exception as e:
            self.logger.error(f"Error while listening to WebSocket: {e}", exc_info=True)
        finally:
            await self.disconnect()
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