from kucoin_futures.client import Market, Trade, User
from .websocket_client import WebSocketClient
import logging

class KuCoinFuturesClient:
    def __init__(self, api_key, api_secret, api_passphrase, use_sandbox=False):
        """Initialize KuCoin Futures client with API credentials."""
        self.api_key = api_key
        self.api_secret = api_secret
        self.api_passphrase = api_passphrase
        self.use_sandbox = use_sandbox
        
        # Initialize API clients
        self.market_client = Market(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        self.trade_client = Trade(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        self.user_client = User(
            key=api_key,
            secret=api_secret,
            passphrase=api_passphrase,
            is_sandbox=use_sandbox
        )
        
        # Initialize WebSocket client
        self.ws_client = None
        
    def connect_websocket(self, symbol, callback):
        """Connect to WebSocket and subscribe to market data."""
        if self.ws_client:
            self.ws_client.close()
            
        self.ws_client = WebSocketClient(
            api_key=self.api_key,
            api_secret=self.api_secret,
            api_passphrase=self.api_passphrase,
            use_sandbox=self.use_sandbox
        )
        
        return self.ws_client.connect(symbol, callback)
        
    def get_position(self, symbol):
        """Get current position for a symbol."""
        positions = self.user_client.get_all_position()
        for position in positions:
            if position['symbol'] == symbol:
                return position
        return None
        
    def set_leverage(self, symbol, leverage):
        """Set leverage for a symbol."""
        return self.trade_client.update_margin_mode(symbol, leverage)
        
    def close_position(self, symbol):
        """Close position for a symbol."""
        position = self.get_position(symbol)
        if position and float(position['currentQty']) != 0:
            side = 'sell' if float(position['currentQty']) > 0 else 'buy'
            size = abs(float(position['currentQty']))
            return self.place_futures_order(symbol, side, size, close_position=True)
        return None
        
    def place_futures_order(self, symbol, side, size, leverage=None, close_position=False):
        """Place a futures order."""
        if leverage:
            self.set_leverage(symbol, leverage)
            
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'market',
            'size': size
        }
        
        if close_position:
            params['closeOrder'] = True
            
        return self.trade_client.create_market_order(**params)

    def get_funding_rate(self, symbol):
        """Get current funding rate."""
        return self.market_client.get_current_funding_rate(symbol) 