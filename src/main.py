import os
import time
import signal
from dotenv import load_dotenv
from api.kucoin_client_new import KuCoinFuturesClient
from strategies.rsi_macd_strategy import RsiMacdStrategy
import logging
import pandas as pd
import numpy as np
from datetime import datetime
from logging.handlers import RotatingFileHandler
import colorama
from colorama import Fore, Style

# Initialize colorama
colorama.init()

# Create logs directory if it doesn't exist
if not os.path.exists('logs'):
    os.makedirs('logs')

# Configure logging
def setup_logging():
    # Main logger
    main_logger = logging.getLogger()
    main_logger.setLevel(logging.DEBUG)

    # Console handler (INFO and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(message)s')
    console_handler.setFormatter(console_formatter)

    # WebSocket file handler (DEBUG and above)
    ws_handler = RotatingFileHandler('logs/websocket.log', maxBytes=1024*1024, backupCount=5)
    ws_handler.setLevel(logging.DEBUG)
    ws_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    ws_handler.setFormatter(ws_formatter)

    # Trading file handler (INFO and above)
    trading_handler = RotatingFileHandler('logs/trading.log', maxBytes=1024*1024, backupCount=5)
    trading_handler.setLevel(logging.INFO)
    trading_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    trading_handler.setFormatter(trading_formatter)

    # Add handlers to the main logger
    main_logger.addHandler(console_handler)
    main_logger.addHandler(ws_handler)
    main_logger.addHandler(trading_handler)

    # Configure WebSocket logger
    ws_logger = logging.getLogger('websocket')
    ws_logger.setLevel(logging.DEBUG)
    ws_logger.addHandler(ws_handler)
    ws_logger.propagate = False  # Prevent messages from propagating to the root logger

    return main_logger

# Set up logging
logger = setup_logging()

class TradingBot:
    def __init__(self):
        # Load environment variables
        load_dotenv()
        
        # Initialize trading parameters
        self.symbol = "SOLUSDTM"  # Use futures symbol directly
        self.leverage = 5
        self.size = 1  # Trading volume in SOL
        
        # Display settings
        self.display_candles = 15  # Number of candles to display (increased from 5)
        self.max_stored_candles = 100  # Maximum number of candles to store
        
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
        
        # Initialize DataFrame for 1-second candlesticks
        self.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'trades']
        self.candlestick_df = pd.DataFrame(columns=self.columns)
        
        # Current candle data
        self.current_candle = {
            'timestamp': None,
            'open': None,
            'high': -np.inf,
            'low': np.inf,
            'close': None,
            'volume': 0,
            'trades': 0
        }
        
        # Market data tracking
        self.mark_price = None
        self.index_price = None
        self.funding_rate = None
        self.last_display_time = 0
        
        # Price tracking
        self.last_price = None
        self.last_update_time = None

    def aggregate_tick_data(self, message):
        """Aggregate WebSocket data into 1-second candlesticks using pandas."""
        try:
            if not isinstance(message, dict):
                return
                
            topic = message.get('topic', '')
            subject = message.get('subject', '')
            data = message.get('data', {})
            
            if not data or 'ts' not in data:
                return
                
            # Convert nanosecond timestamp to second timestamp
            current_time = int(float(data.get('ts', 0)) / 1e9)
            
            # Extract price and size based on message type
            price = None
            size = 0
            
            if 'tickerV2' in topic and subject == 'tickerV2':
                bid_price = float(data.get('bestBidPrice', 0))
                ask_price = float(data.get('bestAskPrice', 0))
                price = (bid_price + ask_price) / 2
                size = (float(data.get('bestBidSize', 0)) + float(data.get('bestAskSize', 0))) / 2
                
            elif 'execution' in topic and subject == 'match':
                price = float(data.get('price', 0))
                size = float(data.get('size', 0))
                
            elif 'instrument' in topic and subject == 'instrument':
                self.mark_price = float(data.get('markPrice', 0))
                self.index_price = float(data.get('indexPrice', 0))
                self.funding_rate = float(data.get('fundingRate', 0))
                price = self.mark_price
                
            if price is None or price == 0:
                return
                
            # Initialize or update current candle
            if self.current_candle['timestamp'] is None:
                self.current_candle['timestamp'] = current_time
                self.current_candle['open'] = price
                self.current_candle['high'] = price
                self.current_candle['low'] = price
                self.current_candle['close'] = price
                self.current_candle['volume'] = size
                self.current_candle['trades'] = 1
                
            elif current_time > self.current_candle['timestamp']:
                # Store the completed candle in DataFrame
                new_row = pd.DataFrame([self.current_candle])
                self.candlestick_df = pd.concat([self.candlestick_df, new_row], ignore_index=True)
                
                # Keep only last 100 candles
                if len(self.candlestick_df) > 100:
                    self.candlestick_df = self.candlestick_df.iloc[-100:]
                
                # Start new candle
                self.current_candle = {
                    'timestamp': current_time,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': size,
                    'trades': 1
                }
            else:
                # Update current candle
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price
                self.current_candle['volume'] += size
                self.current_candle['trades'] += 1
            
            self.last_price = price
            self.last_update_time = current_time
            
        except Exception as e:
            logger.error(f"Error aggregating market data: {str(e)}")

    def format_candlesticks_for_display(self, num_candles=None):
        """Format recent candlesticks for display."""
        if self.candlestick_df.empty:
            return None
            
        # Use class setting if num_candles not specified
        if num_candles is None:
            num_candles = self.display_candles
            
        # Get last n candles
        recent_candles = self.candlestick_df.iloc[-num_candles:].copy()
        
        # Convert timestamp to readable format
        recent_candles['time'] = pd.to_datetime(recent_candles['timestamp'], unit='s').dt.strftime('%H:%M:%S')
        
        # Round numeric columns
        recent_candles[['open', 'high', 'low', 'close']] = recent_candles[['open', 'high', 'low', 'close']].round(3)
        recent_candles['volume'] = recent_candles['volume'].round(4)
        
        # Select and reorder columns
        display_df = recent_candles[['time', 'open', 'high', 'low', 'close', 'volume', 'trades']]
        
        return display_df

    def on_candlestick_update(self, message):
        """Handle new market data and display updates."""
        try:
            if isinstance(message, dict):
                # Log WebSocket message to separate file
                ws_logger = logging.getLogger('websocket')
                ws_logger.debug(f"WebSocket message: {message}")
                
                # Aggregate the data
                self.aggregate_tick_data(message)
                
                # Display updates every second
                current_second = int(time.time())
                if current_second > self.last_display_time:
                    self.last_display_time = current_second
                    
                    # Display market data
                    if self.last_price and self.last_update_time:
                        current_time = datetime.fromtimestamp(self.last_update_time).strftime('%H:%M:%S')
                        
                        # Clear screen and move cursor to top
                        os.system('cls' if os.name == 'nt' else 'clear')
                        
                        # Display header
                        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}")  # Widened separator
                        print(f"{Fore.GREEN}KuCoin Futures Bot - {self.symbol}{Style.RESET_ALL}")
                        print(f"Time: {current_time}")
                        print(f"Storing last {self.max_stored_candles} candles, displaying last {self.display_candles}")
                        print(f"{Fore.CYAN}{'='*80}{Style.RESET_ALL}\n")  # Widened separator
                        
                        # Display current market state in organized sections
                        print(f"{Fore.BLUE}Current Market State:{Style.RESET_ALL}")
                        print(f"{'-'*30}")
                        print(f"Current Price: {Fore.YELLOW}{self.last_price:.3f}{Style.RESET_ALL} USDT")
                        if self.mark_price:
                            print(f"Mark Price:    {Fore.YELLOW}{self.mark_price:.3f}{Style.RESET_ALL} USDT")
                        if self.index_price:
                            print(f"Index Price:   {Fore.YELLOW}{self.index_price:.3f}{Style.RESET_ALL} USDT")
                        if self.funding_rate:
                            print(f"Funding Rate:  {Fore.YELLOW}{self.funding_rate*100:.4f}%{Style.RESET_ALL}")
                        
                        # Display recent candlesticks with more historical data
                        recent_candles = self.format_candlesticks_for_display()
                        if recent_candles is not None:
                            print(f"\n{Fore.BLUE}Recent Candlesticks (Last {self.display_candles} seconds):{Style.RESET_ALL}")
                            print(f"{'-'*80}")  # Widened separator
                            print(f"{'Time':^8} | {'Open':^8} | {'High':^8} | {'Low':^8} | {'Close':^8} | {'Volume':^10} | {'Trades':^6}")
                            print(f"{'-'*80}")  # Widened separator
                            
                            for _, row in recent_candles.iterrows():
                                print(f"{row['time']:^8} | {row['open']:8.3f} | {row['high']:8.3f} | "
                                      f"{row['low']:8.3f} | {row['close']:8.3f} | {row['volume']:10.4f} | {row['trades']:^6d}")
                            
                            print(f"{'-'*80}\n")  # Widened separator
                    
        except Exception as e:
            logger.error(f"Error in market data update: {str(e)}")

    def execute_trade(self, signal):
        """Execute trading signal."""
        try:
            # Get current position
            position = self.client.get_position(self.symbol)
            current_size = float(position.get('currentQty', 0))
            logger.info(f"Current position size: {current_size}")
            
            # Set leverage
            self.client.set_leverage(self.symbol, self.leverage)
            logger.info(f"Leverage set to {self.leverage}x")
            
            if signal == 'buy' and current_size <= 0:
                # Close any existing short position
                if current_size < 0:
                    logger.info(f"Closing existing short position: {current_size}")
                    self.client.close_position(self.symbol)
                
                # Open long position
                order = self.client.place_futures_order(
                    symbol=self.symbol,
                    side='buy',
                    leverage=self.leverage,
                    size=self.size
                )
                logger.info(f"Opened long position: {order}")
                
            elif signal == 'sell' and current_size >= 0:
                # Close any existing long position
                if current_size > 0:
                    logger.info(f"Closing existing long position: {current_size}")
                    self.client.close_position(self.symbol)
                
                # Open short position
                order = self.client.place_futures_order(
                    symbol=self.symbol,
                    side='sell',
                    leverage=self.leverage,
                    size=self.size
                )
                logger.info(f"Opened short position: {order}")
                
        except Exception as e:
            logger.error(f"Error executing trade: {str(e)}")

    def handle_exit(self, signum, frame):
        """Handle graceful shutdown."""
        logger.info("Received exit signal. Closing positions and shutting down...")
        self.running = False
        try:
            # Close any open positions
            self.client.close_position(self.symbol)
            logger.info("Positions closed")
        except Exception as e:
            logger.error(f"Error closing positions: {str(e)}")
        
        # Close WebSocket connection
        if self.client.ws_client:
            self.client.ws_client.close()
            logger.info("WebSocket connection closed")

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
            logger.error(f"Error running bot: {str(e)}")
            raise
        finally:
            if self.client.ws_client:
                self.client.ws_client.close()

if __name__ == "__main__":
    bot = TradingBot()
    bot.run() 