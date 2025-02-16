import numpy as np
import pandas as pd
import logging
from typing import List, Dict
from datetime import datetime
import time

class RsiMacdStrategy:
    def __init__(self, rsi_lower=40, rsi_upper=60, signal_buffer_seconds=3):
        self.rsi_lower = rsi_lower
        self.rsi_upper = rsi_upper
        self.signal_buffer_seconds = signal_buffer_seconds
        self.last_signal = None
        self.last_signal_time = None
        self.logger = logging.getLogger('strategy')

    def calculate_rsi(self, closes):
        """Calculate RSI using pandas for better accuracy"""
        # Convert to pandas Series if not already
        closes = pd.Series(closes) if not isinstance(closes, pd.Series) else closes
        
        # Calculate price changes
        delta = closes.diff()
        
        # Separate gains and losses
        gains = delta.where(delta > 0, 0)
        losses = -delta.where(delta < 0, 0)
        
        # Calculate EMAs for gains and losses
        avg_gains = gains.ewm(alpha=1/14, min_periods=14).mean()
        avg_losses = losses.ewm(alpha=1/14, min_periods=14).mean()
        
        # Calculate RS and RSI
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        
        # Log the calculation
        self.logger.debug(f"Calculated RSI: {rsi.iloc[-1]:.2f}")
        
        return rsi.iloc[-1]

    def calculate_macd(self, closes):
        """Calculate MACD using pandas for better accuracy"""
        # Convert to pandas Series if not already
        closes = pd.Series(closes) if not isinstance(closes, pd.Series) else closes
        
        # Calculate EMAs
        ema12 = closes.ewm(span=12, adjust=False).mean()
        ema26 = closes.ewm(span=26, adjust=False).mean()
        
        # Calculate MACD line
        macd = ema12 - ema26
        
        # Calculate signal line
        signal = macd.ewm(span=9, adjust=False).mean()
        
        # Calculate histogram
        histogram = macd - signal
        
        # Log the calculations
        self.logger.debug(
            f"Calculated MACD - Line: {macd.iloc[-1]:.4f}, "
            f"Signal: {signal.iloc[-1]:.4f}, "
            f"Histogram: {histogram.iloc[-1]:.4f}"
        )
        
        return macd.iloc[-1], signal.iloc[-1], histogram.iloc[-1]

    def check_signal(self, candlestick_df):
        """Check for trading signals based on RSI and MACD"""
        if len(candlestick_df) < 100:  # Need at least 100 candles for reliable signals
            return None
            
        # Calculate indicators
        rsi = self.calculate_rsi(candlestick_df['close'])
        macd, signal, histogram = self.calculate_macd(candlestick_df['close'])
        
        # Get current time
        current_time = time.time()
        
        # Check if enough time has passed since last signal
        if (self.last_signal_time and 
            current_time - self.last_signal_time < self.signal_buffer_seconds):
            return None
            
        # Check for buy signal
        if rsi <= self.rsi_lower and macd > signal:
            self.last_signal = "BUY"
            self.last_signal_time = current_time
            self.logger.info(f"BUY Signal - RSI: {rsi:.2f}, MACD: {macd:.4f}, Signal: {signal:.4f}")
            return "BUY"
            
        # Check for sell signal
        elif rsi >= self.rsi_upper and macd < signal:
            self.last_signal = "SELL"
            self.last_signal_time = current_time
            self.logger.info(f"SELL Signal - RSI: {rsi:.2f}, MACD: {macd:.4f}, Signal: {signal:.4f}")
            return "SELL"
            
        return None

    def analyze_candles(self, candles: List[Dict]) -> str:
        """
        Analyze candlestick data and return trading signal.
        
        Returns:
            str: 'buy', 'sell', or None
        """
        if len(candles) < 100:
            return None
            
        closes = [float(candle['close']) for candle in candles]
        current_time = candles[-1]['timestamp']
        
        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        macd, signal, hist = self.calculate_macd(closes)
        
        # Log indicator values
        self.logger.info(f"RSI: {rsi:.2f}, MACD: {macd:.3f}, Signal: {signal:.3f}, Hist: {hist:.3f}")
        
        # Check RSI conditions
        if rsi < self.rsi_lower:
            self.last_signal = 'buy'
            self.logger.info(f"RSI Buy Signal: {rsi:.2f} < {self.rsi_lower}")
        elif rsi > self.rsi_upper:
            self.last_signal = 'sell'
            self.logger.info(f"RSI Sell Signal: {rsi:.2f} > {self.rsi_upper}")
            
        # Check MACD conditions
        if hist > 0 and self.calculate_rsi(closes[:-1]) <= self.rsi_lower:  # Bullish crossover
            self.last_signal = 'buy'
            self.logger.info(f"MACD Buy Signal: Crossover from {self.calculate_rsi(closes[:-1]):.3f} to {rsi:.3f}")
        elif hist < 0 and self.calculate_rsi(closes[:-1]) >= self.rsi_upper:  # Bearish crossover
            self.last_signal = 'sell'
            self.logger.info(f"MACD Sell Signal: Crossover from {self.calculate_rsi(closes[:-1]):.3f} to {rsi:.3f}")
            
        # Check if enough time has passed since last signal
        if (self.last_signal_time and 
            current_time - self.last_signal_time < self.signal_buffer_seconds):
            return None
            
        return self.last_signal 