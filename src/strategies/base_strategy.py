from abc import ABC, abstractmethod
from datetime import datetime
import logging

from src.api.kucoin_client import KuCoinClient
from config.config import TRADING_PAIR, ORDER_SIZE, STOP_LOSS_PERCENTAGE, TAKE_PROFIT_PERCENTAGE

class BaseStrategy(ABC):
    def __init__(self, client: KuCoinClient):
        """Initialize base strategy with KuCoin client."""
        self.client = client
        self.trading_pair = TRADING_PAIR
        self.order_size = ORDER_SIZE
        self.stop_loss_pct = STOP_LOSS_PERCENTAGE
        self.take_profit_pct = TAKE_PROFIT_PERCENTAGE
        
        # Setup logging
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    @abstractmethod
    def generate_signal(self) -> str:
        """Generate trading signal based on strategy logic.
        
        Returns:
            str: 'buy', 'sell', or 'hold'
        """
        pass

    def execute_trade(self, signal: str) -> bool:
        """Execute trade based on signal."""
        try:
            if signal == 'buy':
                self.logger.info(f"Placing buy order for {self.order_size} {self.trading_pair}")
                order = self.client.place_market_buy(self.trading_pair, self.order_size)
                self.logger.info(f"Buy order placed: {order}")
                return True
            
            elif signal == 'sell':
                self.logger.info(f"Placing sell order for {self.order_size} {self.trading_pair}")
                order = self.client.place_market_sell(self.trading_pair, self.order_size)
                self.logger.info(f"Sell order placed: {order}")
                return True
            
            elif signal == 'hold':
                self.logger.info("Hold signal - no trade executed")
                return True
            
            else:
                self.logger.error(f"Invalid signal: {signal}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error executing trade: {str(e)}")
            return False

    def check_balance(self, currency: str) -> float:
        """Check account balance for a currency."""
        try:
            balance = self.client.get_balance(currency)
            if balance:
                self.logger.info(f"Balance for {currency}: {balance['balance']}")
                return float(balance['balance'])
            return 0.0
        except Exception as e:
            self.logger.error(f"Error checking balance: {str(e)}")
            return 0.0

    def run(self):
        """Main strategy execution loop."""
        self.logger.info(f"Starting strategy for {self.trading_pair}")
        
        while True:
            try:
                signal = self.generate_signal()
                if signal in ['buy', 'sell']:
                    success = self.execute_trade(signal)
                    if not success:
                        self.logger.error("Trade execution failed")
                
            except Exception as e:
                self.logger.error(f"Error in strategy execution: {str(e)}")
                break  # Exit loop on error

    def calculate_stop_loss(self, entry_price: float) -> float:
        """Calculate stop loss price."""
        return entry_price * (1 - self.stop_loss_pct / 100)

    def calculate_take_profit(self, entry_price: float) -> float:
        """Calculate take profit price."""
        return entry_price * (1 + self.take_profit_pct / 100) 