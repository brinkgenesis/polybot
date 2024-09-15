import websocket
import json
import threading
from py_clob_client.client import ClobClient

class ClobWebsocketClient:
    def __init__(self, clob_client: ClobClient, message_handler: callable = None):
        self.ws_url = "wss://ws-subscriptions-clob.polymarket.com/ws/"
        self.clob_client = clob_client
        self.ws = None
        self.message_handler = message_handler  # Callback for handling messages

    def connect(self):
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        wst = threading.Thread(target=self.ws.run_forever, daemon=True)
        wst.start()

    def on_message(self, ws, message):
        if self.message_handler:
            self.message_handler(message)  # Pass message to the handler
        else:
            print(f"Received message: {message}")

    def on_error(self, ws, error):
        print(f"Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket connection closed")

    def on_open(self, ws):
        print("WebSocket connection opened")
        self.subscribe_to_user_channel()

    def subscribe_to_user_channel(self):
        subscription = {
            "type": "subscribe",
            "channel": "user",
            "apiKey": self.clob_client.api_key,
            "signature": self.clob_client.get_signature(),
            "timestamp": self.clob_client.get_timestamp()
        }
        self.ws.send(json.dumps(subscription))

    def subscribe_to_market_channel(self, condition_id: str):
        subscription = {
            "type": "subscribe",
            "channel": "market",
            "marketId": condition_id
        }
        self.ws.send(json.dumps(subscription))
