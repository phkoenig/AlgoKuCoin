import os
import time
import signal
from dotenv import load_dotenv
from api.kucoin_client_new import KuCoinFuturesClient
from strategies.rsi_macd_strategy import RsiMacdStrategy
import logging
import pandas as pd
from datetime import datetime

# Disable noisy websocket and urllib3 logging
logging.getLogger('websocket').setLevel(logging.ERROR)
logging.getLogger('urllib3').setLevel(logging.ERROR)

# Set logging level for our bot
logging.basicConfig(
    level=logging.WARNING,  # Changed from INFO to WARNING
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class TradingBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Initialize trading parameters
        self.symbol = "SOLUSDTM"  # Use futures symbol directly
        self.leverage = 5
        self.size = 1  # Trading volume in SOL
        
        # Initialize WebSocket topics
        self.topics = [
            f"/contractMarket/execution:{self.symbol}",
            f"/contractMarket/tickerV2:{self.symbol}",
            f"/contract/instrument:{self.symbol}"
        ]
        
        # Initialize clients and strategy
        self.client = KuCoinFuturesClient(
            api_key=os.getenv('KUCOIN_API_KEY'),
            api_secret=os.getenv('KUCOIN_API_SECRET'),
            api_passphrase=os.getenv('KUCOIN_API_PASSPHRASE'),
            use_sandbox=False
        )
        
        self.strategy = RsiMacdStrategy(
            rsi_lower=40,
            rsi_upper=60,
            signal_buffer_seconds=3
        )
        
        # Trading state
        self.is_trading = False
        self.current_position = None
        self.running = True
        
        # Last candlestick display time
        self.last_display_time = 0
        
        # Add new attributes for data aggregation
        self.current_candle = {
            'timestamp': None,
            'open': None,
            'high': None,
            'low': None,
            'close': None,
            'volume': 0
        }
        self.candlestick_data = []
        self.last_trade_price = None
        self.last_trade_size = None
        
        # Initialize market data tracking
        self.mark_price = None
        self.index_price = None
        self.funding_rate = None
        
        # Add list to store recent market data
        self.recent_data = {
            'ticker': None,
            'execution': None,
            'instrument': None
        }

    def format_candlesticks_as_dataframe(self, candlesticks):
        """Convert candlesticks to pandas DataFrame and format for display."""
        if not candlesticks:
            return None
            
        # Convert to DataFrame
        df = pd.DataFrame(candlesticks)
        
        # Convert timestamp to datetime
        df['time'] = pd.to_datetime(df['timestamp'], unit='s')  # Changed from 'ms' to 's'
        
        # Format prices to 3 decimal places and volume to 4
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].round(3)
        df['volume'] = df['volume'].round(4)
        
        # Select and reorder columns
        df = df[['time', 'open', 'high', 'low', 'close', 'volume']]
        
        # Format time to show only hours:minutes:seconds
        df['time'] = df['time'].dt.strftime('%H:%M:%S')
        
        return df

    def aggregate_tick_data(self, message):
        """Aggregate WebSocket data into 1-second candlesticks."""
        try:
            if not isinstance(message, dict):
                return
                
            topic = message.get('topic', '')
            subject = message.get('subject', '')
            data = message.get('data', {})
            
            if not data or 'ts' not in data:
                return
                
            current_time = int(float(data.get('ts', 0)) / 1e9)  # Convert nanoseconds to seconds
            
            # Handle different types of messages based on topic and subject
            if 'tickerV2' in topic and subject == 'tickerV2':
                # Update from ticker
                bid_price = float(data.get('bestBidPrice', 0))
                ask_price = float(data.get('bestAskPrice', 0))
                price = (bid_price + ask_price) / 2
                size = (float(data.get('bestBidSize', 0)) + float(data.get('bestAskSize', 0))) / 2
                
            elif 'execution' in topic and subject == 'match':
                # Update from trade execution
                price = float(data.get('price', 0))
                size = float(data.get('size', 0))
                
            elif 'instrument' in topic and subject == 'instrument':
                # Update from market data
                self.mark_price = float(data.get('markPrice', 0))
                self.index_price = float(data.get('indexPrice', 0))
                price = self.mark_price
                size = float(data.get('volume', 0)) if 'volume' in data else 0
            else:
                return
                
            # Initialize new candle if needed
            if self.current_candle['timestamp'] is None:
                self.current_candle['timestamp'] = current_time
                self.current_candle['open'] = price
                self.current_candle['high'] = price
                self.current_candle['low'] = price
                self.current_candle['close'] = price
                self.current_candle['volume'] = size
            
            # Check if we need to create a new candle (1 second has passed)
            elif current_time > self.current_candle['timestamp']:
                # Store the completed candle
                self.candlestick_data.append(dict(self.current_candle))
                
                # Keep only the last 100 candles
                if len(self.candlestick_data) > 100:
                    self.candlestick_data.pop(0)
                
                # Start new candle
                self.current_candle = {
                    'timestamp': current_time,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': size
                }
            
            # Update current candle
            else:
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price
                self.current_candle['volume'] += size

        except Exception as e:
            logging.error(f"Error aggregating market data: {str(e)}")

    def on_candlestick_update(self, message):
        """Handle new market data."""
        try:
            if isinstance(message, dict):
                topic = message.get('topic', '')
                subject = message.get('subject', '')
                data = message.get('data', {})
                
                if data:
                    # Store data based on topic
                    if 'tickerV2' in topic:
                        self.recent_data['ticker'] = data
                    elif 'execution' in topic:
                        self.recent_data['execution'] = data
                    elif 'instrument' in topic:
                        self.recent_data['instrument'] = data
                    
                    # Get timestamp in nanoseconds and convert
                    ts_ns = int(float(data.get('ts', 0)))
                    ts_s = ts_ns // 1_000_000_000
                    current_time = datetime.fromtimestamp(ts_s).strftime('%H:%M:%S.%f')[:-3]
                    
                    # Format the message based on topic
                    if 'tickerV2' in topic:
                        print(f"[{current_time}] TICKER | "
                              f"Bid: {data.get('bestBidPrice')} ({data.get('bestBidSize')}) | "
                              f"Ask: {data.get('bestAskPrice')} ({data.get('bestAskSize')}) | "
                              f"Spread: {float(data.get('bestAskPrice', 0)) - float(data.get('bestBidPrice', 0)):.3f}")
                    
                    elif 'execution' in topic:
                        print(f"[{current_time}] TRADE  | "
                              f"Price: {data.get('price')} | "
                              f"Size: {data.get('size')} | "
                              f"Side: {data.get('side')}")
                    
                    elif 'instrument' in topic:
                        print(f"[{current_time}] MARKET | "
                              f"Mark: {data.get('markPrice')} | "
                              f"Index: {data.get('indexPrice')} | "
                              f"Funding: {float(data.get('fundingRate', 0)) * 100:.4f}%")
                    
                    # Also aggregate this data into candlesticks
                    self.aggregate_tick_data(message)
                    
                    # Every second, show the current candlestick
                    current_second = int(time.time())
                    if current_second > self.last_display_time:
                        self.last_display_time = current_second
                        if self.candlestick_data:
                            df = self.format_candlesticks_as_dataframe(self.candlestick_data[-5:])  # Show last 5 candles
                            if df is not None:
                                print("\nLast 5 Candlesticks:")
                                print(df.to_string(index=False))
                                print()
            
        except Exception as e:
            logging.error(f"Error in market data update: {str(e)}")

    def execute_trade(self, signal):
        """Execute trading signal."""
        try:
            # Get current position
            position = self.client.get_position(self.symbol)
            current_size = float(position.get('currentQty', 0))
            logging.info(f"Current position size: {current_size}")
            
            # Set leverage
            self.client.set_leverage(self.symbol, self.leverage)
            logging.info(f"Leverage set to {self.leverage}x")
            
            if signal == 'buy' and current_size <= 0:
                # Close any existing short position
                if current_size < 0:
                    logging.info(f"Closing existing short position: {current_size}")
                    self.client.close_position(self.symbol)
                
                # Open long position
                order = self.client.place_futures_order(
                    symbol=self.symbol,
                    side='buy',
                    leverage=self.leverage,
                    size=self.size
                )
                logging.info(f"Opened long position: {order}")
                
            elif signal == 'sell' and current_size >= 0:
                # Close any existing long position
                if current_size > 0:
                    logging.info(f"Closing existing long position: {current_size}")
                    self.client.close_position(self.symbol)
                
                # Open short position
                order = self.client.place_futures_order(
                    symbol=self.symbol,
                    side='sell',
                    leverage=self.leverage,
                    size=self.size
                )
                logging.info(f"Opened short position: {order}")
                
        except Exception as e:
            logging.error(f"Error executing trade: {str(e)}")

    def handle_exit(self, signum, frame):
        """Handle graceful shutdown."""
        logging.info("Received exit signal. Closing positions and shutting down...")
        self.running = False
        try:
            # Close any open positions
            self.client.close_position(self.symbol)
            logging.info("Positions closed")
        except Exception as e:
            logging.error(f"Error closing positions: {str(e)}")
        
        # Close WebSocket connection
        if self.client.ws_client:
            self.client.ws_client.close()
            logging.info("WebSocket connection closed")

    def run(self):
        """Run the trading bot."""
        try:
            # Set up signal handlers for graceful shutdown
            signal.signal(signal.SIGINT, self.handle_exit)
            signal.signal(signal.SIGTERM, self.handle_exit)
            
            print("\nStarting trading bot in LIVE mode...")
            print("WARNING: Using real trading environment - trades will use real funds!")
            print(f"Trading {self.symbol} with {self.leverage}x leverage")
            print(f"Position size: {self.size} SOL")
            
            def handle_candlestick_update(message):
                if self.running:
                    self.on_candlestick_update(message)
            
            # Connect to WebSocket
            ws_thread = self.client.connect_websocket(
                symbol=self.symbol,
                callback=handle_candlestick_update
            )
            
            print("\nWaiting for market data...")
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
            ws_thread.join(timeout=5)
            
        except Exception as e:
            logging.error(f"Error running bot: {str(e)}")
            raise
        finally:
            if self.client.ws_client:
                self.client.ws_client.close()

if __name__ == "__main__":
    bot = TradingBot()
    bot.run() 