import logging
import threading
from typing import Any, Callable, Dict, List
from datetime import datetime, timezone
import time
import os
import json
from utils.utils import shorten_id
import websocket
import ssl
import certifi

class WS_Sub:
    def __init__(self, memory_lock: threading.Lock, event_callback: Callable[[Dict[str, Any]], None], on_connected: Callable[[], None]):
        """
        Initialize WS_Sub with callbacks to handle incoming events and connection establishment.
        
        :param memory_lock: Lock for thread-safe operations.
        :param event_callback: Function to call with event data.
        :param on_connected: Function to call when WebSocket is connected.
        """
        self.memory_lock = memory_lock
        self.message_handler = event_callback  # Corrected assignment
        self.on_connected = on_connected
        self.ws_url = os.getenv("WS_URL")  # WebSocket URL
        self.ws_app = None
        self.is_running = True
        self.assets_ids = set()
        self.ws_initialized = threading.Event()
        self.subscribed_assets_ids = set()

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    def on_open(self, ws):
        self.logger.info("WebSocket connection opened.")
        if self.on_connected:
            self.on_connected()
        self.ws_initialized.set()  # Ensure this is called immediately

    def on_message(self, ws, message):
        self.logger.debug(f"Received message: {message}")
        try:
            data = json.loads(message)
            self.message_handler(data)
        except json.JSONDecodeError:
            self.logger.warning("Received non-JSON message.")

    def on_error(self, ws, error):
        """
        Callback for WebSocket errors.
        """
        self.logger.error(f"WebSocket error: {error}", exc_info=True)

    def on_close(self, ws, close_status_code, close_msg):
        self.logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")
        self.ws_initialized.clear()  # Reset the event upon closure
        
        if self.is_running:
            self.logger.info("Attempting to reconnect...")

    def subscribe(self, assets_ids: List[str]):
        """
        Subscribe to the provided list of asset IDs.
        
        :param assets_ids: List of asset IDs to subscribe to.
        """
        # Wait until WebSocket client is initialized
        if not self.ws_initialized.wait(timeout=15):  # Increased timeout to 15 seconds
            self.logger.error("WebSocket client initialization timed out. Cannot subscribe to assets.")
            return


        subscription_payload = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": assets_ids  # Pass the entire list
        }

        try:
            if self.ws_app and self.ws_app.sock and self.ws_app.sock.connected:
                self.logger.info(f"Subscribing to {len(assets_ids)} assets.")
                message = json.dumps(subscription_payload)
                self.ws_app.send(message)
                self.logger.info(f"Subscribed to assets: {list(assets_ids)}")
                self.subscribed_assets_ids.update(assets_ids)
            else:
                self.logger.error("WebSocket client is not connected. Cannot subscribe to assets.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to assets: {e}", exc_info=True)

    def unsubscribe_all(self, assets_ids: List[str]):
        if not self.ws_app or not self.ws_app.sock or not self.ws_app.sock.connected:
            self.logger.warning("WebSocket is not connected. Cannot unsubscribe.")
            return
        unsubscribe_message = {
            "type": "unsubscribe",
            "assets_ids": list(assets_ids)  # Assuming an empty list unsubscribes all
        }
        self.ws_app.send(json.dumps(unsubscribe_message))
        self.logger.info("Sent unsubscription message for all assets.")


    def run(self):
        """
        Run the WebSocket connection with reconnection logic.
        """
        reconnect_delay = 1  # Start with 1 second
        max_reconnect_delay = 60  # Maximum delay of 60 seconds

        while self.is_running:
            try:
                self.logger.info(f"Connecting to WebSocket URL: {self.ws_url}")
                self.ws_app = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                self.ws_app.run_forever(
                    sslopt={"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": certifi.where()}
                )
            except Exception as e:
                self.logger.error(f"WebSocket encountered an exception: {e}", exc_info=True)

            if not self.is_running:
                break  # Exit loop if shutting down

            self.logger.info(f"Attempting to reconnect in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

    def reconnect(self):
           """
           Handle reconnection with exponential backoff.
           """
           self.logger.info(f"Attempting to reconnect in {self.reconnect_delay} seconds...")
           time.sleep(self.reconnect_delay)
           self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
           if self.is_running:
               self.run()

    def shutdown(self):
        """
        Gracefully shutdown the WebSocket connection.
        """
        self.logger.info("Shutting down WS_Sub...")
        self.is_running = False
        if self.ws_app:
            self.ws_app.close()
            self.logger.info("WebSocket client disconnected.")
        self.logger.info("WS_Sub shutdown complete.")

def main():
    # This main function is not directly used by WSorder_manager.py
    # It can be used for standalone testing of WS_Sub
    pass

if __name__ == "__main__":
    main()