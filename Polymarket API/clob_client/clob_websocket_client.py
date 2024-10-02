import asyncio
import json
import logging
import ssl
import certifi  # Import certifi for certificate verification
from typing import Any, Callable, Dict, List
import websocket  # Using the `websocket-client` library for synchronous WebSocket
import threading
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed logs

class ClobWebSocketClient:
    def __init__(self, ws_url: str, message_handler: Callable[[Dict[str, Any]], Any], on_open_callback: Callable = None):
        self.ws_url = ws_url  # WebSocket URL
        self.message_handler = message_handler  # Callback for handling messages
        self.on_open_callback = on_open_callback  # Callback when connection opens
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws = None
        self.stop_keep_alive = threading.Event()

    def on_open(self, ws):
        self.logger.info("WebSocket connection opened.")
        if self.on_open_callback:
            self.on_open_callback()
        # Removed keep-alive ping thread

    def on_message(self, ws, message):
        self.logger.debug(f"Received message: {message}")
        try:
            message = message.strip()
            if not message:
                self.logger.debug("Received an empty message. Ignoring.")
                return
            data = json.loads(message)
            self.message_handler(data)
        except json.JSONDecodeError:
            self.logger.error(f"Received non-JSON message: {message}")
        except Exception as e:
            self.logger.error(f"Unexpected error in on_message: {e}", exc_info=True)

    def on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}", exc_info=True)

    def on_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket connection closed with code {close_status_code}, message: {close_msg}")
        # No keep-alive to stop

    def run_sync(self):
        reconnect_delay = 1  # Start with 1 second
        max_reconnect_delay = 60  # Maximum delay of 60 seconds

        while True:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )
                self.ws.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": certifi.where()}
                )
            except Exception as e:
                self.logger.error(f"WebSocket encountered an exception: {e}", exc_info=True)

            self.logger.info(f"Attempting to reconnect in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

    def disconnect(self):
        if self.ws:
            self.ws.close()
            self.logger.info("WebSocket client disconnected.")