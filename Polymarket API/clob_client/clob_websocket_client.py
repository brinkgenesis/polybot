import asyncio
import websockets
import json
import logging
import ssl
import certifi  # Import certifi for certificate verification
from typing import Any, Callable, Dict, List
import websocket  # Using the `websocket-client` library for synchronous WebSocket
import threading
import time

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class ClobWebSocketClient:
    def __init__(self, ws_url: str, asset_ids: List[str], message_handler: Callable[[Dict[str, Any]], Any], on_open_callback: Callable = None):
        self.ws_url = ws_url  # WebSocket URL
        self.asset_ids = asset_ids  # List of asset IDs to subscribe to
        self.message_handler = message_handler  # Callback for handling messages
        self.on_open_callback = on_open_callback
        self.logger = logging.getLogger(self.__class__.__name__)
        self.ws = None
        self.keep_alive_thread = None
        self.stop_keep_alive = threading.Event()

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            self.message_handler(data)
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON decode error: {e}", exc_info=True)
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    def on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}", exc_info=True)

    def on_close(self, ws, close_status_code, close_msg):
        self.logger.info("WebSocket connection closed.")

    def on_open(self, ws):
        self.logger.info("WebSocket connection opened.")
        # Invoke the callback to signal that the WebSocket is initialized
        if self.on_open_callback:
            self.on_open_callback()
        # Start the keep-alive thread
        self.keep_alive_thread = threading.Thread(target=self.keep_alive, daemon=True)
        self.keep_alive_thread.start()

    def keep_alive(self):
        while not self.stop_keep_alive.is_set():
            try:
                if self.ws:
                    ping_payload = {"type": "ping"}
                    self.ws.send(json.dumps(ping_payload))
                    self.logger.debug("Sent keep-alive ping.")
                time.sleep(30)  # Ping every 30 seconds
            except Exception as e:
                self.logger.error(f"Error sending keep-alive ping: {e}", exc_info=True)
                break  # Exit the loop if unable to send pings

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
                self.ws.run_forever()
            except Exception as e:
                self.logger.error(f"WebSocket encountered an exception: {e}", exc_info=True)

            self.logger.info(f"Attempting to reconnect in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

    def disconnect(self):
        if self.ws:
            self.stop_keep_alive.set()
            self.ws.close()
            self.logger.info("WebSocket client disconnected.")