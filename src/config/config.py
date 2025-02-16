import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API Credentials
API_KEY = os.getenv('KUCOIN_API_KEY')
API_SECRET = os.getenv('KUCOIN_API_SECRET')
API_PASSPHRASE = os.getenv('KUCOIN_API_PASSPHRASE')

# API URLs
API_URL = 'https://api.kucoin.com'
SANDBOX_API_URL = 'https://openapi-sandbox.kucoin.com'

# Trading Parameters
TRADING_PAIR = os.getenv('TRADING_PAIR', 'SOLUSDT')
LEVERAGE = int(os.getenv('LEVERAGE', '5'))
POSITION_SIZE = float(os.getenv('POSITION_SIZE', '1')) 