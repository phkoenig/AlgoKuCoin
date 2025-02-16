import numpy as np
import pandas as pd
from typing import List, Dict
from datetime import datetime

class RsiMacdStrategy:
    def __init__(self, rsi_period: int = 14, 
                 macd_fast: int = 12, 
                 macd_slow: int = 26, 
                 macd_signal: int = 9,
                 rsi_lower: float = 40,
                 rsi_upper: float = 60,
                 signal_buffer_seconds: int = 3):
        """
        Initialize the RSI + MACD strategy.
        
        Args:
            rsi_period: Period for RSI calculation
            macd_fast: Fast period for MACD
            macd_slow: Slow period for MACD
            macd_signal: Signal period for MACD
            rsi_lower: Lower RSI threshold (oversold)
            rsi_upper: Upper RSI threshold (overbought)
            signal_buffer_seconds: Time window to look for matching signals
        """
        self.rsi_period = rsi_period
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.signal_buffer_seconds = signal_buffer_seconds
        
        # Signal tracking
        self.last_rsi_signal = {'type': None, 'time': None}
        self.last_macd_signal = {'type': None, 'time': None}

    def calculate_rsi(self, closes: List[float]) -> float:
        """Calculate RSI value."""
        if len(closes) < self.rsi_period:
            return 50  # Default value when not enough data
            
        # Calculate price changes
        delta = np.diff(closes)
        
        # Separate gains and losses
        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)
        
        # Calculate average gains and losses
        avg_gain = np.mean(gains[:self.rsi_period])
        avg_loss = np.mean(losses[:self.rsi_period])
        
        if avg_loss == 0:
            return 100
        
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        
        return rsi

    def calculate_macd(self, closes: List[float]) -> tuple:
        """Calculate MACD values."""
        if len(closes) < self.macd_slow + self.macd_signal:
            return 0, 0, 0  # Default values when not enough data
            
        # Calculate EMAs
        exp1 = pd.Series(closes).ewm(span=self.macd_fast, adjust=False).mean()
        exp2 = pd.Series(closes).ewm(span=self.macd_slow, adjust=False).mean()
        
        # Calculate MACD line
        macd = exp1 - exp2
        
        # Calculate Signal line
        signal = macd.ewm(span=self.macd_signal, adjust=False).mean()
        
        # Calculate histogram
        hist = macd - signal
        
        return macd.iloc[-1], signal.iloc[-1], hist.iloc[-1]

    def check_signals_match(self, signal_type: str, current_time: int) -> bool:
        """
        Check if RSI and MACD signals match within the buffer window.
        Returns True if signals match within the buffer time window.
        """
        if self.last_rsi_signal['type'] != signal_type or self.last_macd_signal['type'] != signal_type:
            return False
            
        # Convert millisecond timestamps to seconds
        rsi_time = self.last_rsi_signal['time'] // 1000
        macd_time = self.last_macd_signal['time'] // 1000
        current_time = current_time // 1000
        
        # Check if both signals occurred within buffer window
        latest_signal = max(rsi_time, macd_time)
        earliest_signal = min(rsi_time, macd_time)
        
        return (latest_signal - earliest_signal) <= self.signal_buffer_seconds

    def analyze_candles(self, candles: List[Dict]) -> str:
        """
        Analyze candlestick data and return trading signal.
        
        Returns:
            str: 'buy', 'sell', or None
        """
        if len(candles) < max(self.rsi_period, self.macd_slow + self.macd_signal):
            return None
            
        closes = [float(candle['close']) for candle in candles]
        current_time = candles[-1]['timestamp']
        
        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        macd, signal, hist = self.calculate_macd(closes)
        prev_hist = self.get_previous_hist(candles)
        
        # Check RSI conditions
        if rsi < self.rsi_lower:
            self.last_rsi_signal = {'type': 'buy', 'time': current_time}
        elif rsi > self.rsi_upper:
            self.last_rsi_signal = {'type': 'sell', 'time': current_time}
            
        # Check MACD conditions
        if hist > 0 and prev_hist <= 0:  # Bullish crossover
            self.last_macd_signal = {'type': 'buy', 'time': current_time}
        elif hist < 0 and prev_hist >= 0:  # Bearish crossover
            self.last_macd_signal = {'type': 'sell', 'time': current_time}
            
        # Check if signals match within buffer window
        if self.check_signals_match('buy', current_time):
            return 'buy'
        elif self.check_signals_match('sell', current_time):
            return 'sell'
            
        return None

    def get_previous_hist(self, candles: List[Dict]) -> float:
        """Calculate previous MACD histogram value."""
        if len(candles) < max(self.rsi_period, self.macd_slow + self.macd_signal) + 1:
            return 0
            
        closes = [float(candle['close']) for candle in candles[:-1]]
        _, _, hist = self.calculate_macd(closes)
        return hist 