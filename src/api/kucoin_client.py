from kucoin.client import Market, Trade, User
from kucoin_futures.client import Market as FuturesMarket
from kucoin_futures.client import Trade as FuturesTrade
from kucoin_futures.client import User as FuturesUser
import websocket
import json
import time
import threading
from datetime import datetime
import numpy as np
import requests
import logging
from config.config import API_KEY, API_SECRET, API_PASSPHRASE, API_URL, SANDBOX_API_URL

class KuCoinFuturesClient:
    def __init__(self, api_key, api_secret, api_passphrase, use_sandbox=False):
        """Initialize KuCoin Futures client with API credentials."""
        self.use_sandbox = use_sandbox
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        
        # Initialize API clients for futures
        self.market_client = FuturesMarket(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        self.trade_client = FuturesTrade(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        self.user_client = FuturesUser(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        
        # For WebSocket connection
        self.ws = None
        self.ping_thread = None
        self.ping_interval = 20  # Ping every 20 seconds
        self.should_reconnect = True
        self.reconnect_delay = 5  # Start with 5 seconds delay
        self.max_reconnect_delay = 60  # Maximum delay between reconnects
        
        # For candlestick data
        self.candlestick_data = []
        self.current_candle = {
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': 0,
            'timestamp': None
        }

    def get_ws_token(self):
        """Get WebSocket token for futures API."""
        base_url = "https://api-sandbox-futures.kucoin.com" if self.use_sandbox else "https://api-futures.kucoin.com"
        url = f"{base_url}/api/v1/bullet-public"
        
        response = requests.post(url)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == '200000':
                return data['data']
        raise Exception(f"Failed to get WebSocket token. Response: {response.text}")

    def start_ping_thread(self):
        """Start a thread to send ping messages periodically."""
        def ping_loop():
            while self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    ping_msg = {"id": int(time.time() * 1000), "type": "ping"}
                    self.ws.send(json.dumps(ping_msg))
                    logging.info("Ping sent")
                    time.sleep(self.ping_interval)
                except Exception as e:
                    logging.error(f"Error in ping loop: {str(e)}")
                    break

        self.ping_thread = threading.Thread(target=ping_loop)
        self.ping_thread.daemon = True
        self.ping_thread.start()

    def connect_websocket(self, symbol, callback):
        """Connect to KuCoin WebSocket for real-time trade data."""
        def connect():
            while self.should_reconnect:
                try:
                    # Get WebSocket token and endpoints
                    ws_info = self.get_ws_token()
                    
                    if not ws_info or 'token' not in ws_info:
                        raise Exception("Failed to get WebSocket token")
                    
                    # Get the first WebSocket server URL
                    ws_endpoint = f"{ws_info['instanceServers'][0]['endpoint']}?token={ws_info['token']}"
                    logging.info(f"WebSocket URL: {ws_endpoint}")
                    
                    def on_message(ws, message):
                        try:
                            data = json.loads(message)
                            logging.info(f"Received: {message}")  # Log all messages for debugging
                            
                            if data['type'] == 'message':
                                # Extract trade data
                                trade_data = data['data']
                                
                                # Log based on subject
                                if data.get('subject') == 'tickerV2':
                                    logging.info(f"Ticker Update | "
                                              f"Price: {trade_data.get('price', 'unknown')} | "
                                              f"Volume: {trade_data.get('volume', 'unknown')} | "
                                              f"Time: {datetime.fromtimestamp(int(trade_data.get('ts', 0))/1000).strftime('%H:%M:%S.%f')[:-3]}")
                                elif data.get('subject') == 'match':
                                    logging.info(f"Trade Execution | "
                                              f"Side: {trade_data.get('side', 'unknown')} | "
                                              f"Price: {trade_data.get('price', 'unknown')} | "
                                              f"Size: {trade_data.get('size', 'unknown')} | "
                                              f"Time: {datetime.fromtimestamp(int(trade_data.get('ts', 0))/1000).strftime('%H:%M:%S.%f')[:-3]}")
                                
                                if 'price' in trade_data:
                                    price = float(trade_data['price'])
                                    size = float(trade_data.get('size', 0))
                                    timestamp = int(trade_data['ts'])
                                    
                                    # Update current candle
                                    if self.current_candle['open'] is None:
                                        self.current_candle = {
                                            'open': price,
                                            'high': price,
                                            'low': price,
                                            'close': price,
                                            'volume': size,
                                            'timestamp': timestamp
                                        }
                                    else:
                                        self.current_candle['high'] = max(self.current_candle['high'], price)
                                        self.current_candle['low'] = min(self.current_candle['low'], price)
                                        self.current_candle['close'] = price
                                        self.current_candle['volume'] += size
                                    
                                    # If second has changed, save candle and start new one
                                    current_second = int(timestamp / 1000)
                                    if self.current_candle['timestamp'] and int(self.current_candle['timestamp'] / 1000) < current_second:
                                        self.candlestick_data.append(self.current_candle.copy())
                                        if len(self.candlestick_data) > 1000:  # Keep last 1000 candles
                                            self.candlestick_data.pop(0)
                                        callback(self.candlestick_data)
                                        self.current_candle = {
                                            'open': price,
                                            'high': price,
                                            'low': price,
                                            'close': price,
                                            'volume': size,
                                            'timestamp': timestamp
                                        }
                        elif data['type'] == 'pong':
                            logging.debug("Pong received")
                        elif data['type'] == 'welcome':
                            logging.info("Welcome message received, subscribing to market data...")
                            # Subscribe to both execution and ticker feeds
                            subscribe_messages = [
                                {
                                    "id": int(time.time() * 1000),
                                    "type": "subscribe",
                                    "topic": f"/contractMarket/execution:{symbol}",
                                    "privateChannel": False,
                                    "response": True
                                },
                                {
                                    "id": int(time.time() * 1000) + 1,
                                    "type": "subscribe",
                                    "topic": f"/contractMarket/tickerV2:{symbol}",
                                    "privateChannel": False,
                                    "response": True
                                }
                            ]
                            for msg in subscribe_messages:
                                ws.send(json.dumps(msg))
                                logging.info(f"Subscribe message sent: {msg}")
                        elif data['type'] == 'ack':
                            logging.info(f"Subscription confirmed: {data}")
                            if not self.ping_thread:
                                self.start_ping_thread()
                    except Exception as e:
                        logging.error(f"Error processing message: {str(e)}")
                        logging.error(f"Message that caused error: {message}")

                    def on_error(ws, error):
                        logging.error(f"WebSocket Error: {error}")

                    def on_close(ws, close_status_code, close_msg):
                        logging.warning(f"WebSocket Connection Closed: {close_status_code} - {close_msg}")
                        if self.should_reconnect:
                            time.sleep(self.reconnect_delay)
                            self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

                    def on_open(ws):
                        logging.info("WebSocket connection opened, waiting for welcome message...")

                    websocket.enableTrace(False)  # Disable low-level WebSocket logs
                    self.ws = websocket.WebSocketApp(
                        ws_endpoint,
                        on_message=on_message,
                        on_error=on_error,
                        on_close=on_close,
                        on_open=on_open
                    )
                    
                    self.ws.run_forever(ping_interval=20, ping_timeout=10)
                    
                except Exception as e:
                    logging.error(f"Connection error: {str(e)}")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)

        # Start connection in a separate thread
        connect_thread = threading.Thread(target=connect)
        connect_thread.daemon = True
        connect_thread.start()
        return connect_thread

    def place_futures_order(self, symbol, side, leverage, size, price=None, stop_price=None):
        """Place a futures order."""
        params = {
            'symbol': symbol,
            'side': side,
            'leverage': str(leverage),
            'size': str(size),
            'type': 'market' if price is None else 'limit'
        }
        
        if price is not None:
            params['price'] = str(price)
        if stop_price is not None:
            params['stop'] = 'down' if side == 'buy' else 'up'
            params['stopPrice'] = str(stop_price)
            
        return self.trade_client.create_order(**params)

    def get_position(self, symbol):
        """Get current position for a symbol."""
        return self.trade_client.get_position(symbol)

    def set_leverage(self, symbol, leverage):
        """Set leverage for a symbol."""
        return self.trade_client.set_leverage(symbol, leverage)

    def get_funding_rate(self, symbol):
        """Get current funding rate."""
        return self.market_client.get_current_funding_rate(symbol)

    def close_position(self, symbol):
        """Close position for a symbol."""
        position = self.get_position(symbol)
        if position and float(position['currentQty']) != 0:
            side = 'sell' if float(position['currentQty']) > 0 else 'buy'
            return self.place_futures_order(
                symbol=symbol,
                side=side,
                leverage=position['realLeverage'],
                size=abs(float(position['currentQty']))
            )

class KuCoinClient:
    def __init__(self, use_sandbox=False):
        """Initialize KuCoin client with API credentials."""
        self.api_url = SANDBOX_API_URL if use_sandbox else API_URL
        
        # Initialize API clients
        self.market_client = Market(url=self.api_url)
        self.trade_client = Trade(
            key=API_KEY,
            secret=API_SECRET,
            passphrase=API_PASSPHRASE,
            url=self.api_url
        )
        self.user_client = User(
            key=API_KEY,
            secret=API_SECRET,
            passphrase=API_PASSPHRASE,
            url=self.api_url
        )

    def get_ticker(self, symbol):
        """Get current ticker for a symbol."""
        return self.market_client.get_ticker(symbol)

    def get_balance(self, currency):
        """Get account balance for a currency."""
        accounts = self.user_client.get_account_list(currency=currency)
        return accounts[0] if accounts else None

    def place_market_buy(self, symbol, size):
        """Place a market buy order."""
        return self.trade_client.create_market_order(
            symbol=symbol,
            side='buy',
            size=str(size)
        )

    def place_market_sell(self, symbol, size):
        """Place a market sell order."""
        return self.trade_client.create_market_order(
            symbol=symbol,
            side='sell',
            size=str(size)
        )

    def get_klines(self, symbol, kline_type, start_time=None, end_time=None):
        """Get historical klines/candlestick data."""
        return self.market_client.get_kline(
            symbol=symbol,
            kline_type=kline_type,
            start=start_time,
            end=end_time
        )

    def get_order_details(self, order_id):
        """Get details of a specific order."""
        return self.trade_client.get_order_details(order_id)

    def cancel_order(self, order_id):
        """Cancel a specific order."""
        return self.trade_client.cancel_order(order_id) 