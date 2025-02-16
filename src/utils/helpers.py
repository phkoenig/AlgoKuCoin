import time
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

def calculate_rsi(prices: list, period: int = 14) -> float:
    """Calculate Relative Strength Index (RSI)."""
    if len(prices) < period + 1:
        return 50.0  # Return neutral RSI if not enough data
        
    # Calculate price changes
    deltas = np.diff(prices)
    
    # Separate gains and losses
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    # Calculate average gains and losses
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return 100.0
    
    # Calculate RS and RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def calculate_moving_average(prices: list, period: int) -> float:
    """Calculate Simple Moving Average (SMA)."""
    if len(prices) < period:
        return prices[-1] if prices else 0
    return sum(prices[-period:]) / period

def calculate_exponential_moving_average(prices: list, period: int) -> float:
    """Calculate Exponential Moving Average (EMA)."""
    if len(prices) < period:
        return prices[-1] if prices else 0
    
    multiplier = 2 / (period + 1)
    ema = prices[0]
    
    for price in prices[1:]:
        ema = (price - ema) * multiplier + ema
    
    return ema

def format_number(number: float, decimals: int = 8) -> str:
    """Format number with specified decimal places."""
    return f"{number:.{decimals}f}"

def timestamp_to_datetime(timestamp: int) -> datetime:
    """Convert Unix timestamp to datetime object."""
    return datetime.fromtimestamp(timestamp / 1000)  # KuCoin uses milliseconds

def get_current_timestamp() -> int:
    """Get current timestamp in milliseconds."""
    return int(time.time() * 1000)

def calculate_percentage_change(old_value: float, new_value: float) -> float:
    """Calculate percentage change between two values."""
    if old_value == 0:
        return 0
    return ((new_value - old_value) / old_value) * 100

def parse_klines_to_dataframe(klines: list) -> pd.DataFrame:
    """Convert KuCoin klines data to pandas DataFrame."""
    df = pd.DataFrame(klines, columns=['timestamp', 'open', 'close', 'high', 'low', 'volume', 'turnover'])
    
    # Convert types
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'close', 'high', 'low', 'volume', 'turnover']:
        df[col] = pd.to_numeric(df[col])
    
    return df.sort_values('timestamp') 