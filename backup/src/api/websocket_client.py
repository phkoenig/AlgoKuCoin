import websocket
import json
import time
import threading
from datetime import datetime
import logging
import requests
import base64
import hmac
import hashlib

class WebSocketClient:
    def __init__(self, api_key, api_secret, api_passphrase, use_sandbox=False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.use_sandbox = use_sandbox
        self.ws = None
        self.ping_thread = None
        self.running = False
        self.callback = None
        
        # Candlestick aggregation
        self.current_candle = None
        self.candles = []
        self.last_candle_time = None
        
    def sign_request(self, timestamp, method, endpoint, body=''):
        """Sign request for API v2 authentication."""
        str_to_sign = str(timestamp) + method + endpoint + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                str_to_sign.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        passphrase = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                self.api_passphrase.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        
        return signature, passphrase
        
    def get_ws_token(self):
        """Get WebSocket token from KuCoin."""
        base_url = "https://api-futures.kucoin.com"
        if self.use_sandbox:
            base_url = "https://api-sandbox-futures.kucoin.com"
            
        endpoint = "/api/v1/bullet-public"
        
        response = requests.post(f"{base_url}{endpoint}")
        
        if response.status_code == 200:
            data = response.json()
            if data["code"] == "200000":
                token = data["data"]["token"]
                server = data["data"]["instanceServers"][0]
                return token, server["endpoint"]
            else:
                raise Exception(f"API Error: {data.get('msg', 'Unknown error')}")
        raise Exception(f"Failed to get WebSocket token: {response.text}")

    def start_ping_thread(self):
        """Start a thread to send ping messages periodically."""
        def ping_loop():
            while self.running:
                try:
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        self.ws.send(json.dumps({"type": "ping"}))
                    time.sleep(20)
                except Exception as e:
                    logging.error(f"Error in ping thread: {str(e)}")
                    break
        
        self.ping_thread = threading.Thread(target=ping_loop)
        self.ping_thread.daemon = True
        self.ping_thread.start()

    def create_new_candle(self, timestamp_ms):
        """Create a new candlestick."""
        return {
            'timestamp': timestamp_ms,
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': 0.0
        }

    def update_candle(self, price, size):
        """Update current candlestick with new trade data."""
        current_time = int(time.time() * 1000)  # Current time in milliseconds
        
        # Initialize new candle if needed
        if not self.current_candle or current_time - self.current_candle['timestamp'] >= 1000:
            # Store and display previous candle if it exists and is complete
            if self.current_candle and self.current_candle['open'] is not None:
                self.candles.append(self.current_candle)
                # Keep only last 100 candles
                if len(self.candles) > 100:
                    self.candles.pop(0)
                # Log the completed candlestick
                candle_time = datetime.fromtimestamp(self.current_candle['timestamp']/1000).strftime('%H:%M:%S')
                logging.info(f"1s Candle | Time: {candle_time} | O: {self.current_candle['open']:.3f} | H: {self.current_candle['high']:.3f} | L: {self.current_candle['low']:.3f} | C: {self.current_candle['close']:.3f} | V: {self.current_candle['volume']:.4f}")
            
            # Create new candle
            self.current_candle = self.create_new_candle(current_time - (current_time % 1000))
        
        # Update candle data
        if self.current_candle['open'] is None:
            self.current_candle['open'] = price
        self.current_candle['high'] = max(self.current_candle['high'] or price, price)
        self.current_candle['low'] = min(self.current_candle['low'] or price, price)
        self.current_candle['close'] = price
        self.current_candle['volume'] += float(size)
        
        # Trigger callback with updated candles if it exists
        if self.callback and len(self.candles) > 0:
            self.callback(self.candles + [self.current_candle])

    def on_open(self, ws):
        """Handle WebSocket connection opened."""
        logging.warning("WebSocket connection established")

    def on_message(self, ws, message):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(message)
            logging.warning(f"Raw message: {message}")  # Debug log
            
            if self.callback:
                self.callback(data)
            
        except Exception as e:
            logging.error(f"Error processing message: {str(e)}")

    def on_error(self, ws, error):
        """Handle WebSocket errors."""
        logging.error(f"WebSocket error: {str(error)}")

    def on_close(self, ws, close_status_code, close_msg):
        """Handle WebSocket connection close."""
        self.running = False
        logging.info("WebSocket connection closed")

    def connect(self, symbol, callback=None):
        """Connect to KuCoin WebSocket and subscribe to market data."""
        self.callback = callback
        self.running = True
        
        # Get WebSocket token and endpoint
        token, endpoint = self.get_ws_token()
        
        # Construct WebSocket URL
        ws_url = f"{endpoint}?token={token}&connectId={int(time.time() * 1000)}"
        
        # Configure and start WebSocket
        self.ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )
        
        # Start ping thread
        self.start_ping_thread()
        
        def run_websocket():
            while self.running:
                try:
                    self.ws.run_forever()
                    if self.running:
                        logging.warning("WebSocket disconnected. Reconnecting...")
                        time.sleep(5)
                except Exception as e:
                    logging.error(f"WebSocket error: {str(e)}")
                    if self.running:
                        time.sleep(5)
        
        # Start WebSocket thread
        ws_thread = threading.Thread(target=run_websocket)
        ws_thread.daemon = True
        ws_thread.start()
        
        # Wait for connection to establish
        time.sleep(1)
        
        # Subscribe to market data topics
        topics = [
            f"/contractMarket/execution:{symbol}",
            f"/contractMarket/tickerV2:{symbol}",
            f"/contract/instrument:{symbol}"
        ]
        
        # Send subscription messages
        for topic in topics:
            subscribe_message = {
                "id": int(time.time() * 1000),
                "type": "subscribe",
                "topic": topic,
                "privateChannel": False,
                "response": True
            }
            self.ws.send(json.dumps(subscribe_message))
            logging.warning(f"Subscribed to: {topic}")
        
        return ws_thread

    def close(self):
        """Close WebSocket connection."""
        self.running = False
        if self.ws:
            self.ws.close() 