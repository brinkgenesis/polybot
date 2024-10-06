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
    def __init__(self, event_callback: Callable[[Dict[str, Any]], None]):
        """
        Initialize WS_Sub with a callback to handle incoming events.
        
        :param event_callback: Function to call with event data.
        """
        self.ws_url = os.getenv("WS_URL")  # WebSocket URL
        self.ws_app = None
        self.message_handler = self.message_handler
        self.on_open_callback = self.on_ws_open
        self.event_callback = event_callback  # Callback function for events

        self.is_running = True
        self.assets_ids = set()
        self.ws_initialized = threading.Event()

        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)

    def connect_websocket(self):
        """
        Initialize and run the WebSocket client in a separate thread.
        """
        ws_thread = threading.Thread(target=self.run_websocket, daemon=True)
        ws_thread.start()
        self.logger.info("WebSocket client thread started.")

    def run_websocket(self):
        """
        Run the WebSocket connection with reconnection logic.
        """
        reconnect_delay = 1  # Start with 1 second
        max_reconnect_delay = 60  # Maximum delay of 60 seconds

        while self.is_running:
            try:
                self.ws_app = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close,
                )
                self.ws_app.run_forever(
                )
            except Exception as e:
                self.logger.error(f"WebSocket encountered an exception: {e}", exc_info=True)

            if not self.is_running:
                break  # Exit loop if shutting down

            self.logger.info(f"Attempting to reconnect in {reconnect_delay} seconds...")
            time.sleep(reconnect_delay)
            reconnect_delay = min(reconnect_delay * 2, max_reconnect_delay)  # Exponential backoff

    def on_open(self, ws):
        """
        Callback when WebSocket connection is opened.
        """
        self.logger.info("WebSocket connection opened.")
        if self.on_open_callback:
            self.on_open_callback()

    def on_ws_open(self):
        """
        Callback specific for WS_Sub when WebSocket is opened.
        """
        self.logger.info("WebSocket connection established. Ready to subscribe.")
        self.ws_initialized.set()

    def on_message(self, ws, message):
        """
        Callback for received messages from WebSocket.
        """
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
        """
        Callback when WebSocket connection is closed.
        """
        self.logger.info(f"WebSocket connection closed: {close_status_code} - {close_msg}")

    def message_handler(self, data: Dict[str, Any]):
        """
        Handle incoming WebSocket messages and forward them via callback.
        """
        try:
            asset_id = data.get("asset_id")
            event_type = data.get("event_type")
            if event_type in ["book", "price_change", "last_trade_price"]:
                self.event_callback(data)  # Forward event to callback
            else:
                self.logger.warning(f"Unhandled event_type: {event_type}")
        except Exception as e:
            self.logger.error(f"Error in message_handler: {e}", exc_info=True)

    def subscribe_all_assets(self):
        """
        Subscribe to all assets after ensuring the WebSocket is initialized.
        """
        # Wait until WebSocket client is initialized
        if not self.ws_initialized.wait(timeout=15):  # Wait up to 15 seconds
            self.logger.error("WebSocket client initialization timed out. Cannot subscribe to assets.")
            return

        assets_ids = list(self.assets_ids)  # Convert set to list
        if not assets_ids:
            self.logger.warning("No assets to subscribe to.")
            return

        subscription_payload = {
            "type": "subscribe",
            "channel": "market",
            "assets_ids": assets_ids  # Pass the entire list
        }

        try:
            if self.ws_app and self.ws_app.sock and self.ws_app.sock.connected:
                # Log minimal subscription payload
                self.logger.info(f"Subscribing to {len(assets_ids)} assets.")
                
                # Convert payload to JSON string
                message = json.dumps(subscription_payload)
                self.ws_app.send(message)  # Send the subscription message
                self.logger.info("Subscribed to all assets.")
            else:
                self.logger.error("WebSocket client is not connected. Cannot subscribe to assets.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to all assets: {e}", exc_info=True)

    def subscribe(self, assets_ids: List[str]):
        """
        Subscribe to the provided list of asset IDs.
        
        :param assets_ids: List of asset IDs to subscribe to.
        """
        if not assets_ids:
            self.logger.warning("No assets provided for subscription.")
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
                self.logger.info(f"Subscribed to assets: {assets_ids}")
            else:
                self.logger.error("WebSocket client is not connected. Cannot subscribe to assets.")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to assets: {e}", exc_info=True)

    def run(self):
        """
        Run the WS_Sub by connecting WebSocket and handling subscriptions.
        """
        self.connect_websocket()
        # Start subscription in a separate thread to prevent blocking
        subscription_thread = threading.Thread(
            target=self.subscribe_all_assets,
            daemon=True
        )
        subscription_thread.start()
        self.logger.info("Subscription thread started.")
        try:
            while self.is_running:
                time.sleep(1)  # Keep the main thread alive
        except KeyboardInterrupt:
            self.shutdown()

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

    def _convert_timestamp(self, timestamp):
        """
        Convert timestamp to a readable format.
        """
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return timestamp

def main():
    # This main function is not directly used by WSorder_manager.py
    # It can be used for standalone testing of WS_Sub
    pass

if __name__ == "__main__":
    main()