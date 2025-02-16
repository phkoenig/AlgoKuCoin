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

    # Strategy file handler (INFO and above)
    strategy_handler = RotatingFileHandler('logs/strategy.log', maxBytes=1024*1024, backupCount=5)
    strategy_handler.setLevel(logging.INFO)
    strategy_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    strategy_handler.setFormatter(strategy_formatter)

    # Add handlers to the main logger
    main_logger.addHandler(console_handler)
    main_logger.addHandler(ws_handler)
    main_logger.addHandler(trading_handler)

    # Configure WebSocket logger
    ws_logger = logging.getLogger('websocket')
    ws_logger.setLevel(logging.DEBUG)
    ws_logger.addHandler(ws_handler)
    ws_logger.propagate = False  # Prevent messages from propagating to the root logger

    # Configure Strategy logger
    strategy_logger = logging.getLogger('strategy')
    strategy_logger.setLevel(logging.INFO)
    strategy_logger.addHandler(strategy_handler)
    strategy_logger.addHandler(console_handler)  # Also show strategy messages in console
    strategy_logger.propagate = False  # Prevent messages from propagating to the root logger

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
        
        # Set up strategy logger
        self.strategy_logger = logging.getLogger('strategy')
        
        # Trading state
        self.is_trading = False
        self.current_position = None
        self.running = True
        self.last_signal = None
        self.last_signal_time = None
        
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
        """Aggregate WebSocket data into 1-second candlesticks."""
        try:
            if not isinstance(message, dict):
                return
                
            data = message.get('data', {})
            if not data:
                return
                
            # Extract price from different message types
            price = None
            if 'bestBidPrice' in data and 'bestAskPrice' in data:
                bid_price = float(data['bestBidPrice'])
                ask_price = float(data['bestAskPrice'])
                price = (bid_price + ask_price) / 2
            elif 'price' in data:
                price = float(data['price'])
            elif 'markPrice' in data:
                price = float(data['markPrice'])
                
            if price is None:
                return
                
            # Update last price
            self.last_price = price
            self.last_update_time = int(time.time())
            
            # Create new candlestick every second
            current_time = self.last_update_time
            
            if self.current_candle['timestamp'] is None:
                # Initialize first candle
                self.current_candle = {
                    'timestamp': current_time,
                    'open': price,
                    'high': price,
                    'low': price,
                    'close': price,
                    'volume': 0,
                    'trades': 1
                }
            elif current_time > self.current_candle['timestamp']:
                # Log the completed candle
                logger.debug(f"Completed candle - Time: {datetime.fromtimestamp(self.current_candle['timestamp']).strftime('%H:%M:%S')} | "
                           f"O: {self.current_candle['open']:.3f} | H: {self.current_candle['high']:.3f} | "
                           f"L: {self.current_candle['low']:.3f} | C: {self.current_candle['close']:.3f}")
                
                # Store the completed candle
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
                    'volume': 0,
                    'trades': 1
                }
            else:
                # Update current candle
                self.current_candle['high'] = max(self.current_candle['high'], price)
                self.current_candle['low'] = min(self.current_candle['low'], price)
                self.current_candle['close'] = price
                self.current_candle['trades'] += 1
                
        except Exception as e:
            logger.error(f"Error aggregating market data: {str(e)}")
            logger.exception("Full traceback:")

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

    def process_trading_signals(self):
        """Process trading signals from strategy."""
        if len(self.candlestick_df) < 100:  # Need enough data for indicators
            return
            
        # Convert DataFrame to list of dictionaries for strategy
        candles = self.candlestick_df.to_dict('records')
        
        # Get trading signal
        signal = self.strategy.analyze_candles(candles)
        
        if signal:
            current_time = int(time.time())
            # Only process new signals or signals older than 3 seconds
            if (self.last_signal != signal or 
                self.last_signal_time is None or 
                current_time - self.last_signal_time > 3):
                
                self.last_signal = signal
                self.last_signal_time = current_time
                
                # Execute trade
                self.execute_trade(signal)

    def on_candlestick_update(self, message):
        """Handle new market data and display updates."""
        try:
            if isinstance(message, dict):
                # Aggregate the data
                self.aggregate_tick_data(message)
                
                # Display updates every second
                current_second = int(time.time())
                if current_second > self.last_display_time:
                    self.last_display_time = current_second
                    
                    # Only update display if we have price data
                    if self.last_price and self.last_update_time:
                        # Clear screen
                        os.system('cls' if os.name == 'nt' else 'clear')
                        
                        # Display header
                        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}KuCoin Futures Bot - {self.symbol}{Style.RESET_ALL}")
                        print(f"Time: {datetime.fromtimestamp(self.last_update_time).strftime('%H:%M:%S')}")
                        print(f"{Fore.CYAN}{'='*50}{Style.RESET_ALL}\n")
                        
                        # Display basic market data
                        print(f"{Fore.BLUE}Market Data:{Style.RESET_ALL}")
                        print(f"{'-'*30}")
                        print(f"Current Price: {Fore.YELLOW}{self.last_price:.3f}{Style.RESET_ALL} USDT")
                        print(f"Candlesticks:  {len(self.candlestick_df)}/100")
                        print()
                        
                        # Display indicators if we have enough data
                        if len(self.candlestick_df) >= 100:
                            try:
                                # Calculate indicators
                                rsi = self.strategy.calculate_rsi(self.candlestick_df['close'].values)
                                macd, signal, hist = self.strategy.calculate_macd(self.candlestick_df['close'].values)
                                
                                print(f"{Fore.BLUE}Indicators:{Style.RESET_ALL}")
                                print(f"{'-'*30}")
                                
                                # Display RSI with color
                                rsi_color = (Fore.GREEN if rsi <= 40 else 
                                           Fore.RED if rsi >= 60 else 
                                           Fore.YELLOW)
                                print(f"RSI (40/60):    {rsi_color}{rsi:.2f}{Style.RESET_ALL}")
                                
                                # Display MACD with color
                                macd_color = Fore.GREEN if macd > signal else Fore.RED
                                print(f"MACD Line:      {macd_color}{macd:.4f}{Style.RESET_ALL}")
                                print(f"Signal Line:    {macd_color}{signal:.4f}{Style.RESET_ALL}")
                                print(f"Histogram:      {Fore.GREEN if hist > 0 else Fore.RED}{hist:.4f}{Style.RESET_ALL}")
                                print()
                                
                            except Exception as e:
                                print(f"{Fore.RED}Error calculating indicators: {str(e)}{Style.RESET_ALL}")
                        else:
                            print(f"{Fore.YELLOW}Waiting for more data to calculate indicators...{Style.RESET_ALL}")
                            print(f"Need {100 - len(self.candlestick_df)} more candlesticks")
                            print()
                        
                        # Display last few candlesticks
                        if not self.candlestick_df.empty:
                            print(f"{Fore.BLUE}Recent Candlesticks:{Style.RESET_ALL}")
                            print(f"{'-'*30}")
                            recent = self.candlestick_df.iloc[-15:] if len(self.candlestick_df) > 15 else self.candlestick_df
                            for _, candle in recent.iterrows():
                                time_str = datetime.fromtimestamp(candle['timestamp']).strftime('%H:%M:%S')
                                color = Fore.GREEN if candle['close'] >= candle['open'] else Fore.RED
                                print(f"{color}{time_str} | O: {candle['open']:.3f} | H: {candle['high']:.3f} | "
                                      f"L: {candle['low']:.3f} | C: {candle['close']:.3f}{Style.RESET_ALL}")
    
        except Exception as e:
            logger.error(f"Error updating display: {str(e)}")
            logger.exception("Full traceback:")

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
            # Try to close any open positions without checking first
            try:
                self.client.close_position(self.symbol)
                logger.info("Position closed successfully")
            except Exception as e:
                if "Position does not exist" in str(e):
                    logger.info("No open position to close")
                else:
                    raise
                
        except Exception as e:
            logger.error(f"Error closing positions: {str(e)}")
            logger.exception("Full traceback:")
        
        # Close WebSocket connection
        if hasattr(self.client, 'ws_client') and self.client.ws_client:
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
            print("\nConnecting to KuCoin WebSocket...")
            ws_thread = self.client.connect_websocket(
                symbol=self.symbol,
                callback=handle_candlestick_update
            )
            
            print("Connected! Waiting for market data...")
            print("Press Ctrl+C to exit safely\n")
            
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
                
                # Check WebSocket connection
                if not ws_thread.is_alive():
                    print("WebSocket disconnected. Reconnecting...")
                    ws_thread = self.client.connect_websocket(
                        symbol=self.symbol,
                        callback=handle_candlestick_update
                    )
            
            ws_thread.join(timeout=5)
            
        except Exception as e:
            logger.error(f"Error running bot: {str(e)}")
            logger.exception("Full traceback:")
            raise
        finally:
            if self.client.ws_client:
                self.client.ws_client.close()

    def display_market_state(self):
        """Display current market state including indicators and recent candlesticks"""
        os.system('cls' if os.name == 'nt' else 'clear')
        
        # Current Market State
        print("\n=== Current Market State ===")
        print(f"Symbol: {self.symbol}")
        print(f"Current Price: {self.last_price:.2f}")
        print(f"24h Volume: {self.volume_24h:.2f}")
        print(f"24h High: {self.high_24h:.2f}")
        print(f"24h Low: {self.low_24h:.2f}")
        
        # Strategy Indicators
        if len(self.candlestick_df) >= 100:  # Only show if we have enough data
            print("\n=== Strategy Indicators ===")
            
            # Get indicator values
            rsi = self.strategy.calculate_rsi(self.candlestick_df['close'].values)
            macd, signal, hist = self.strategy.calculate_macd(self.candlestick_df['close'].values)
            
            # Color code RSI
            rsi_color = '\033[32m' if rsi <= 40 else '\033[31m' if rsi >= 60 else '\033[37m'
            print(f"RSI (40/60): {rsi_color}{rsi:.2f}\033[0m")
            
            # Color code MACD
            macd_color = '\033[32m' if macd > signal else '\033[31m'
            hist_color = '\033[32m' if hist > 0 else '\033[31m'
            print(f"MACD: {macd_color}{macd:.4f}\033[0m")
            print(f"Signal: {macd_color}{signal:.4f}\033[0m")
            print(f"Histogram: {hist_color}{hist:.4f}\033[0m")
            
            # Log indicator values
            self.strategy_logger.info(f"Indicators - RSI: {rsi:.2f}, MACD: {macd:.4f}, Signal: {signal:.4f}, Hist: {hist:.4f}")
        
        # Recent Candlesticks
        print("\n=== Recent Candlesticks ===")
        if self.candlestick_df.empty:
            print("No data available for recent candlesticks")
        else:
            recent_candles = self.candlestick_df.iloc[-self.display_candles:].copy()
            for _, row in recent_candles.iterrows():
                color = '\033[32m' if row['close'] >= row['open'] else '\033[31m'
                print(f"{color}Time: {datetime.fromtimestamp(row['timestamp']).strftime('%H:%M:%S')} | "
                      f"O: {row['open']:.2f} | H: {row['high']:.2f} | L: {row['low']:.2f} | C: {row['close']:.2f}\033[0m")
        
        # Trading Status
        print("\n=== Trading Status ===")
        print(f"Last Signal: {self.strategy.last_signal if hasattr(self.strategy, 'last_signal') else 'None'}")
        if hasattr(self.strategy, 'last_signal_time') and self.strategy.last_signal_time:
            print(f"Last Signal Time: {datetime.fromtimestamp(self.strategy.last_signal_time).strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == "__main__":
    bot = TradingBot()
    bot.run() 