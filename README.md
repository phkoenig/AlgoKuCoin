# AlgoKuCoin Trading Bot

An algorithmic trading bot for the KuCoin cryptocurrency exchange.

## Setup

1. Create a Python virtual environment:
```bash
conda create -n kucoin-bot python=3.11
conda activate kucoin-bot
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure your environment:
- Copy `.env.example` to `.env`
- Add your KuCoin API credentials to `.env`

## Project Structure

```
AlgoKuCoin/
├── config/          # Configuration files
├── src/            # Source code
│   ├── api/        # Exchange API integration
│   ├── strategies/ # Trading strategies
│   └── utils/      # Utility functions
├── .env            # Environment variables
└── requirements.txt # Project dependencies
```

## Usage

1. Set up your API credentials in `.env`
2. Configure your trading parameters
3. Run the bot:
```bash
python src/main.py
```

## WebSocket Market Data

### Symbol Format
For KuCoin Futures WebSocket, use the following symbol format:
- Spot Trading: `SOLUSDT`
- Futures Trading: `SOLUSDTM` (append 'M' to the base currency)

### Available Data Streams
The bot subscribes to three main data streams:

1. Trade Executions:
```
Topic: /contractMarket/execution:{symbol}
Example: /contractMarket/execution:SOLUSDTM
Data: Individual trades with side, price, size, and timestamp
```

2. Ticker Updates:
```
Topic: /contractMarket/tickerV2:{symbol}
Example: /contractMarket/tickerV2:SOLUSDTM
Data: Current price, volume, and other ticker information
```

3. Market Updates:
```
Topic: /contract/instrument:{symbol}
Example: /contract/instrument:SOLUSDTM
Data: Mark price, index price, and funding rate information
```

### Example WebSocket Response Format

1. Trade Execution:
```json
{
    "type": "message",
    "topic": "/contractMarket/execution:SOLUSDTM",
    "subject": "match",
    "data": {
        "symbol": "SOLUSDTM",
        "side": "buy",
        "price": "100.123",
        "size": "1.000",
        "ts": 1623456789000000000
    }
}
```

2. Ticker Update:
```json
{
    "type": "message",
    "topic": "/contractMarket/tickerV2:SOLUSDTM",
    "subject": "tickerV2",
    "data": {
        "symbol": "SOLUSDTM",
        "price": "100.123",
        "volume": "1000.000",
        "ts": 1623456789000000000
    }
}
```

3. Market Update:
```json
{
    "type": "message",
    "topic": "/contract/instrument:SOLUSDTM",
    "subject": "instrument",
    "data": {
        "symbol": "SOLUSDTM",
        "markPrice": "100.123",
        "indexPrice": "100.120",
        "ts": 1623456789000000000
    }
}
```

### Connection Process
1. The bot automatically handles WebSocket connection and token management
2. Reconnection is automatic in case of disconnection
3. Ping/Pong heartbeat is maintained every 20 seconds
4. All market data is logged to both console and `trading_bot.log`

## WebSocket Data Handling

### Data Flow
1. Raw WebSocket messages come in three types:
   - Ticker updates (`/contractMarket/tickerV2:{symbol}`)
   - Trade executions (`/contractMarket/execution:{symbol}`)
   - Market updates (`/contract/instrument:{symbol}`)

2. Each message contains:
   - `topic`: Identifies the data stream
   - `subject`: Message type (e.g., 'tickerV2', 'match', 'instrument')
   - `data`: The actual market data
   - `ts`: Timestamp in nanoseconds

### Message Format Examples
```json
// Ticker Update
{
    "topic": "/contractMarket/tickerV2:SOLUSDTM",
    "subject": "tickerV2",
    "data": {
        "bestBidPrice": "187.744",
        "bestBidSize": "3",
        "bestAskPrice": "187.745",
        "bestAskSize": "686",
        "ts": "1739744681183000000"
    }
}

// Trade Execution
{
    "topic": "/contractMarket/execution:SOLUSDTM",
    "subject": "match",
    "data": {
        "price": "187.744",
        "size": "0.1",
        "side": "sell",
        "ts": "1739744681183000000"
    }
}

// Market Update
{
    "topic": "/contract/instrument:SOLUSDTM",
    "subject": "instrument",
    "data": {
        "markPrice": "187.773",
        "indexPrice": "187.781",
        "fundingRate": "0.0001",
        "ts": "1739744681183000000"
    }
}
```

### Important Implementation Notes
1. **Timestamp Handling**:
   - WebSocket timestamps are in nanoseconds (ts field)
   - Convert to seconds: `ts_seconds = ts_nanoseconds // 1_000_000_000`
   - For display: `datetime.fromtimestamp(ts_seconds).strftime('%H:%M:%S.%f')[:-3]`

2. **Data Aggregation**:
   - Store latest data from each stream type separately
   - Use a dictionary to track recent updates:
   ```python
   self.recent_data = {
       'ticker': None,
       'execution': None,
       'instrument': None
   }
   ```

3. **Display Considerations**:
   - Don't clear screen (`\033[2J\033[H`) if you want to keep message history
   - Format timestamps consistently across all message types
   - Include message type in output for easy identification

4. **Best Practices**:
   - Always validate message structure before processing
   - Handle each topic type separately
   - Keep track of last update time for rate limiting
   - Store raw data for analysis/debugging

5. **Error Handling**:
   - Check for required fields before accessing
   - Use try/except blocks for data conversion
   - Log errors without interrupting the data stream

### Example Output Format
```
[23:38:22.720] TICKER | Bid: 187.744 (3) | Ask: 187.745 (686) | Spread: 0.001
[23:38:22.845] TRADE  | Price: 187.744 | Size: 0.1 | Side: sell
[23:38:22.901] MARKET | Mark: 187.773 | Index: 187.781 | Funding: 0.0100%

Last 5 Candlesticks:
   time     open    high     low   close  volume
23:38:18  187.744  187.745  187.744  187.745  0.8500
23:38:19  187.745  187.746  187.744  187.744  1.2300
23:38:20  187.744  187.745  187.744  187.745  0.9100
23:38:21  187.745  187.746  187.744  187.744  1.1200
23:38:22  187.744  187.745  187.744  187.745  0.7800
```

## Safety Notes

- Always start with small trade amounts
- Use stop-loss orders
- Monitor your bot regularly
- Test thoroughly in sandbox mode first

## License

MIT 