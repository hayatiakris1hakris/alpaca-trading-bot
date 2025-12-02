import os
import requests
from datetime import datetime, timedelta
import json
import time

# Alpaca API Configuration
API_KEY = os.environ.get('ALPACA_API_KEY')
SECRET_KEY = os.environ.get('ALPACA_SECRET_KEY')
BASE_URL = 'https://paper-api.alpaca.markets'

HEADERS = {
    'APCA-API-KEY-ID': API_KEY,
    'APCA-API-SECRET-KEY': SECRET_KEY
}

# Configuration
SYMBOL = 'UPRO'
QUANTITY = 5
LEVERAGE_MULTIPLIER = 3  # UPRO is 3x leveraged

def load_trading_config():
    """Load trading configuration from config file"""
    try:
        with open('sp500_stop_config.json', 'r') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        print("⚠️  sp500_stop_config.json not found.")
        return None

def get_market_clock():
    """Get market clock info"""
    url = f'{BASE_URL}/v2/clock'
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 200:
        return response.json()
    return None

def get_previous_close(symbol):
    """Get previous day's close price"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    url = f'https://data.alpaca.markets/v2/stocks/{symbol}/bars'
    params = {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'timeframe': '1Day',
        'limit': 5
    }
    
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        bars = data.get('bars', [])
        if len(bars) >= 2:
            return bars[-2]['c']  # Previous day's close
    return None

def get_sp500_data():
    """Get SPY open for stop calculation (SPY = SP500 Index / 10)"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    url = f'https://data.alpaca.markets/v2/stocks/SPY/bars'
    params = {
        'start': start_date.strftime('%Y-%m-%d'),
        'end': end_date.strftime('%Y-%m-%d'),
        'timeframe': '1Day',
        'limit': 5
    }
    
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code == 200:
        data = response.json()
        bars = data.get('bars', [])
        if len(bars) >= 1:
            today_open = bars[-1]['o']
            return today_open
    return None

def get_current_price(symbol):
    """Get current price from latest trade"""
    url = f'https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        return data['trade']['p']
    return None

def get_current_position(symbol):
    """Check if we have an open position"""
    url = f'{BASE_URL}/v2/positions/{symbol}'
    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        return response.json()
    return None

def place_market_order(symbol, qty, side):
    """Place a market order"""
    url = f'{BASE_URL}/v2/orders'
    order_data = {
        'symbol': symbol,
        'qty': qty,
        'side': side,
        'type': 'market',
        'time_in_force': 'day'
    }
    
    response = requests.post(url, headers=HEADERS, json=order_data)
    if response.status_code == 200:
        order = response.json()
        print(f"✅ {side.upper()} order placed: {qty} shares of {symbol}")
        print(f"   Order ID: {order['id']}")
        return order
    else:
        print(f"❌ Failed to place {side} order: {response.text}")
        return None

def calculate_dynamic_stop(sp500_index_stop, spy_open, upro_entry_price, trailing_percent):
    """Calculate UPRO stop price based on SP500 Index stop
    
    Args:
        sp500_index_stop: SP500 Index stop price (e.g., 5900)
        spy_open: SPY ETF open price (e.g., 590)
        upro_entry_price: UPRO entry price
        trailing_percent: Trailing stop percentage
    
    Returns:
        UPRO stop price
    """
    
    # Try to calculate stop from SP500 price
    if sp500_index_stop and spy_open:
        try:
            # Convert SP500 Index stop to SPY equivalent (Index / 10)
            spy_stop_price = sp500_index_stop / 10
            
            # Calculate SPY stop percentage
            spy_stop_pct = ((spy_stop_price - spy_open) / spy_open) * 100
            
            # UPRO is already 3x leveraged, so use the same percentage
            upro_stop_pct = spy_stop_pct
            
            # Calculate UPRO stop price
            upro_stop_price = upro_entry_price * (1 + upro_stop_pct / 100)
            
            print(f"\n📊 Dynamic Stop Calculation:")
            print(f"   SP500 Index Stop: {sp500_index_stop:.2f}")
            print(f"   SPY Stop (Index/10): ${spy_stop_price:.2f}")
            print(f"   SPY Open: ${spy_open:.2f}")
            print(f"   Stop %: {spy_stop_pct:.2f}%")
            print(f"   UPRO Entry: ${upro_entry_price:.2f}")
            print(f"   UPRO Stop Price: ${upro_stop_price:.2f}")
            
            return upro_stop_price
            
        except Exception as e:
            print(f"⚠️  Error calculating dynamic stop: {e}")
            print(f"   Falling back to trailing stop: {trailing_percent}%")
    
    # Fallback: Use trailing stop
    upro_stop_price = upro_entry_price * (1 - trailing_percent / 100)
    
    print(f"\n📊 Trailing Stop:")
    print(f"   UPRO Entry: ${upro_entry_price:.2f}")
    print(f"   Trailing %: -{trailing_percent:.2f}%")
    print(f"   UPRO Stop Price: ${upro_stop_price:.2f}")
    
    return upro_stop_price

def check_entry_conditions(symbol, prev_close):
    """Check if entry conditions are met"""
    # Get today's open price for gap calculation
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)
    
    url = f'https://data.alpaca.markets/v2/stocks/{symbol}/bars'
    params = {
        'start': start_date.strftime('%Y-%m-%d'),
        'timeframe': '1Day',
        'limit': 1
    }
    
    response = requests.get(url, headers=HEADERS, params=params)
    if response.status_code != 200:
        return False, None
    
    data = response.json()
    bars = data.get('bars', [])
    if not bars:
        return False, None
    
    today_open = bars[0]['o']
    gap_pct = ((today_open - prev_close) / prev_close) * 100
    
    print(f"\n📊 Gap Analysis:")
    print(f"   Previous Close: ${prev_close:.2f}")
    print(f"   Today's Open: ${today_open:.2f}")
    print(f"   Gap: {gap_pct:.2f}%")
    
    current_price = get_current_price(symbol)
    if not current_price:
        return False, None
    
    print(f"   Current Price: ${current_price:.2f}")
    
    # Entry logic
    if gap_pct > 1.0:
        print(f"   ⏳ Gap > 1%, waiting 15 minutes after open...")
        clock = get_market_clock()
        if clock and clock['is_open']:
            market_open_time = datetime.fromisoformat(clock['next_open'].replace('Z', '+00:00'))
            time_since_open = (datetime.now(market_open_time.tzinfo) - market_open_time).total_seconds() / 60
            
            if time_since_open < 15:
                print(f"   ⏰ Only {time_since_open:.1f} minutes since open, waiting...")
                return False, None
            else:
                print(f"   ✅ 15 minutes passed, checking price...")
    
    # Check if price is above previous close
    if current_price >= prev_close:
        print(f"   ✅ ENTRY CONDITION MET: Price ${current_price:.2f} >= Prev Close ${prev_close:.2f}")
        return True, current_price
    else:
        print(f"   ❌ Price ${current_price:.2f} < Prev Close ${prev_close:.2f}, waiting...")
        return False, None

# Global variable to track highest price for trailing stop
highest_price = {}

def main():
    """Main UPRO trading logic"""
    global highest_price
    print(f"\n{'#'*60}")
    print(f"# UPRO AUTOMATED TRADING SYSTEM")
    print(f"# Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}")
    print(f"{'#'*60}")
    
    if not API_KEY or not SECRET_KEY:
        print("❌ ERROR: Alpaca API credentials not found!")
        return
    
    # Check market status
    clock = get_market_clock()
    if not clock:
        print("❌ Cannot get market clock")
        return
    
    if not clock['is_open']:
        print("⏸️  Market is closed")
        return
    
    # Load trading configuration
    config = load_trading_config()
    if not config:
        print("❌ Cannot load trading config")
        return
    
    trading_enabled = config.get('upro_trading_enabled', False)
    sp500_stop_price = config.get('sp500_stop_price')
    trailing_percent = config.get('trailing_stop_percent', 3.0)
    
    # Validate trailing percent
    if trailing_percent is None or trailing_percent <= 0 or trailing_percent > 3:
        trailing_percent = 3.0
    
    print(f"\n⚙️  Trading Configuration:")
    print(f"   Trading Enabled: {'✅ YES' if trading_enabled else '❌ NO (Position management only)'}")
    print(f"   SP500 Stop Price: ${sp500_stop_price:.2f}" if sp500_stop_price else "   SP500 Stop: Not set")
    print(f"   Trailing Stop %: {trailing_percent:.2f}%")
    print(f"   Last Updated: {config.get('last_updated', 'Unknown')}")
    
    # Get previous close
    prev_close = get_previous_close(SYMBOL)
    if not prev_close:
        print(f"❌ Cannot get previous close for {SYMBOL}")
        return
    
    # Get SP500 data for stop calculation
    spy_open = get_sp500_data()
    
    # Check if we have a position
    position = get_current_position(SYMBOL)
    
    if position:
        # We have a position - monitor for exit
        qty = float(position['qty'])
        entry_price = float(position['avg_entry_price'])
        current_price = float(position['current_price'])
        unrealized_pl = float(position['unrealized_pl'])
        
        print(f"\n💼 Current Position:")
        print(f"   Quantity: {qty}")
        print(f"   Entry Price: ${entry_price:.2f}")
        print(f"   Current Price: ${current_price:.2f}")
        print(f"   Unrealized P/L: ${unrealized_pl:.2f}")
        
        # Initialize highest price tracker
        if SYMBOL not in highest_price:
            highest_price[SYMBOL] = current_price
        
        # Update highest price
        if current_price > highest_price[SYMBOL]:
            highest_price[SYMBOL] = current_price
            print(f"   🔝 New high: ${highest_price[SYMBOL]:.2f}")
        
        # Calculate dynamic stop
        initial_stop = calculate_dynamic_stop(sp500_stop_price, spy_open, entry_price, trailing_percent)
        
        # Update trailing stop based on highest price
        trailing_stop = highest_price[SYMBOL] * (1 - trailing_percent / 100)
        
        # Use the higher of initial stop or trailing stop
        final_stop = max(initial_stop, trailing_stop)
        
        print(f"\n📊 Stop Management:")
        print(f"   Initial Stop: ${initial_stop:.2f}")
        print(f"   Trailing Stop (from ${highest_price[SYMBOL]:.2f}): ${trailing_stop:.2f}")
        print(f"   Final Stop: ${final_stop:.2f}")
        
        if current_price <= final_stop:
            print(f"\n🚨 STOP LOSS TRIGGERED!")
            print(f"   Current: ${current_price:.2f} <= Stop: ${final_stop:.2f}")
            place_market_order(SYMBOL, qty, 'sell')
            # Reset highest price tracker
            if SYMBOL in highest_price:
                del highest_price[SYMBOL]
            return
        
        # Check if it's near market close (15:58 ET = 20:58 UTC)
        now = datetime.now()
        if now.hour == 20 and now.minute >= 58:
            print(f"\n⏰ Near market close (15:58 ET), closing position...")
            place_market_order(SYMBOL, qty, 'sell')
            # Reset highest price tracker
            if SYMBOL in highest_price:
                del highest_price[SYMBOL]
        else:
            print(f"\n✅ Position OK, monitoring continues...")
    
    else:
        # No position - check if trading is enabled today
        print(f"\n💤 No open position")
        
        if not trading_enabled:
            print(f"\n🚫 Trading disabled for today (upro_trading_enabled = false)")
            print(f"   Only position management is active.")
            print(f"   To enable trading, set 'upro_trading_enabled: true' in sp500_stop_config.json")
            return
        
        print(f"\n✅ Trading enabled for today, checking entry conditions...")
        
        should_enter, entry_price = check_entry_conditions(SYMBOL, prev_close)
        
        if should_enter:
            print(f"\n🚀 ENTERING POSITION!")
            place_market_order(SYMBOL, QUANTITY, 'buy')
        else:
            print(f"\n⏳ Entry conditions not met, waiting...")
    
    print(f"\n{'#'*60}")
    print(f"# UPRO monitoring cycle completed")
    print(f"{'#'*60}\n")

if __name__ == "__main__":
    main()