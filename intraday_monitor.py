import os
import requests
from datetime import datetime, timedelta
import json

# Alpaca API Configuration
API_KEY = os.environ.get('ALPACA_API_KEY')
SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
BASE_URL = 'https://paper-api.alpaca.markets'

HEADERS = {
    'APCA-API-KEY-ID': API_KEY,
    'APCA-API-SECRET-KEY': SECRET_KEY
}

# Configuration
INTRADAY_SYMBOLS = ['SPXS']  # Intraday monitoring symbols

def get_historical_bars(symbol, days=25):
    """Get historical daily bars for SMA calculation"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days+10)
    
    url = f'https://data.alpaca.markets/v2/stocks/{symbol}/bars'
    params = {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'timeframe': '1Day',
        'limit': 30
    }
    
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        return data.get('bars', [])
    return []

def get_latest_price(symbol):
    """Get current price from latest trade"""
    url = f'https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        return data['trade']['p']
    return None

def calculate_sma20(bars):
    """Calculate 20-day Simple Moving Average"""
    if len(bars) < 20:
        print(f"Warning: Only {len(bars)} bars available, need 20 for SMA20")
        return None
    
    close_prices = [bar['c'] for bar in bars[-20:]]
    sma20 = sum(close_prices) / len(close_prices)
    return sma20

def get_current_position(symbol):
    """Check if we have an open position"""
    url = f'{BASE_URL}/v2/positions/{symbol}'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json()
    return None

def close_position(symbol, reason):
    """Close position with market order"""
    url = f'{BASE_URL}/v2/positions/{symbol}'
    response = requests.delete(url, headers=HEADERS)
    
    if response.status_code == 200:
        print(f"✅ CLOSED {symbol} - Reason: {reason}")
        return True
    else:
        print(f"❌ Failed to close {symbol}: {response.text}")
        return False

def is_market_open():
    """Check if market is currently open"""
    url = f'{BASE_URL}/v2/clock'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        clock = response.json()
        return clock['is_open']
    return False

def monitor_symbol(symbol):
    """Monitor a single symbol"""
    print(f"\n{'='*60}")
    print(f"Monitoring {symbol} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # Check if market is open
    if not is_market_open():
        print(f"⏸️  Market is closed, skipping intraday check")
        return
    
    # Get historical data for SMA20
    bars = get_historical_bars(symbol)
    if not bars:
        print(f"❌ No historical data for {symbol}")
        return
    
    # Calculate SMA20
    sma20 = calculate_sma20(bars)
    if sma20 is None:
        print(f"❌ Cannot calculate SMA20 for {symbol}")
        return
    
    # Get current price
    current_price = get_latest_price(symbol)
    if current_price is None:
        print(f"❌ Cannot get current price for {symbol}")
        return
    
    print(f"📊 Current Price: ${current_price:.2f}")
    print(f"📈 SMA20: ${sma20:.2f}")
    print(f"📉 Difference: ${current_price - sma20:.2f} ({((current_price/sma20 - 1)*100):.2f}%)")
    
    # Check if we have a position
    position = get_current_position(symbol)
    
    if position:
        qty = float(position['qty'])
        entry_price = float(position['avg_entry_price'])
        position_price = float(position['current_price'])
        unrealized_pl = float(position['unrealized_pl'])
        
        print(f"\n💼 Current Position:")
        print(f"   Quantity: {qty}")
        print(f"   Entry Price: ${entry_price:.2f}")
        print(f"   Current Price: ${position_price:.2f}")
        print(f"   Unrealized P/L: ${unrealized_pl:.2f}")
        
        # Check stop condition: Current Price < SMA20
        if current_price < sma20:
            print(f"\n🚨 STOP TRIGGERED: Price (${current_price:.2f}) < SMA20 (${sma20:.2f})")
            close_position(symbol, f"Price < SMA20 (${current_price:.2f} < ${sma20:.2f})")
        else:
            print(f"\n✅ Position OK: Price (${current_price:.2f}) > SMA20 (${sma20:.2f})")
    else:
        print(f"\n💤 No open position for {symbol}")

def main():
    """Main monitoring function"""
    print(f"\n{'#'*60}")
    print(f"# INTRADAY MONITORING - Hourly Check")
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"{'#'*60}")
    
    if not API_KEY or not SECRET_KEY:
        print("❌ ERROR: Alpaca API credentials not found!")
        print("Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables")
        return
    
    for symbol in INTRADAY_SYMBOLS:
        try:
            monitor_symbol(symbol)
        except Exception as e:
            print(f"❌ Error monitoring {symbol}: {str(e)}")
    
    print(f"\n{'#'*60}")
    print(f"# Intraday monitoring completed")
    print(f"{'#'*60}\n")

if __name__ == "__main__":
    main()