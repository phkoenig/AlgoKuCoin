import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Configuration
API_KEY = os.getenv('KUCOIN_API_KEY')
API_SECRET = os.getenv('KUCOIN_API_SECRET')
API_PASSPHRASE = os.getenv('KUCOIN_API_PASSPHRASE')

# Trading Configuration
TRADING_PAIR = os.getenv('TRADING_PAIR', 'BTC-USDT')
ORDER_SIZE = float(os.getenv('ORDER_SIZE', '0.001'))
STOP_LOSS_PERCENTAGE = float(os.getenv('STOP_LOSS_PERCENTAGE', '2.0'))
TAKE_PROFIT_PERCENTAGE = float(os.getenv('TAKE_PROFIT_PERCENTAGE', '3.0'))

# API URLs
API_URL = 'https://api.kucoin.com'  # Main net
SANDBOX_API_URL = 'https://openapi-sandbox.kucoin.com'  # Sandbox for testing

# Trading Parameters
CANDLE_INTERVAL = '15min'  # Available intervals: 1min, 3min, 5min, 15min, 30min, 1hour, 2hour, 4hour, 6hour, 8hour, 12hour, 1day, 1week
MAX_ORDERS = 5  # Maximum number of open orders
MIN_VOLUME = 100  # Minimum 24h volume in USDT to consider trading a pair 