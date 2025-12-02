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
SYMBOL = 'SPXS'
QUANTITY = 5
LEVERAGE_MULTIPLIER = 3  # SPXS is 3x inverse leveraged

def load_trading_config():
    """Load trading configuration from config file"""
    try:
        with open('spxs_config.json', 'r') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        print("⚠️  spxs_config.json not found.")
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

def get_spy_open():
    """Get SPY open for stop calculation"""
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

def calculate_dynamic_stop(sp500_index_stop, spy_open, spxs_entry_price):
    """Calculate SPXS stop price based on SP500 Index stop
    
    SPXS is INVERSE 3x leveraged, so:
    - If SP500 goes UP, SPXS goes DOWN
    - Stop is when SP500 goes ABOVE the stop level
    
    Args:
        sp500_index_stop: SP500 Index stop price (e.g., 5900)
        spy_open: SPY ETF open price (e.g., 590)
        spxs_entry_price: SPXS entry price
    
    Returns:
        SPXS stop price
    """
    if not sp500_index_stop or not spy_open:
        return None
    
    # Convert SP500 Index stop to SPY equivalent (Index / 10)
    spy_stop_price = sp500_index_stop / 10
    
    # Calculate SPY stop percentage (how much UP from open)
    spy_stop_pct = ((spy_stop_price - spy_open) / spy_open) * 100
    
    # SPXS is INVERSE 3x, so when SPY goes up, SPXS goes down with same %
    spxs_stop_pct = spy_stop_pct
    
    # Calculate SPXS stop price (entry + percentage, because when SPY goes up, SPXS also goes up to trigger stop)
    spxs_stop_price = spxs_entry_price * (1 + abs(spxs_stop_pct) / 100)
    
    print(f"\n📊 Dynamic Stop Calculation (INVERSE):")
    print(f"   SP500 Index Stop: {sp500_index_stop:.2f}")
    print(f"   SPY Stop (Index/10): ${spy_stop_price:.2f}")
    print(f"   SPY Open: ${spy_open:.2f}")
    print(f"   SPY Stop %: +{spy_stop_pct:.2f}% (UP)")
    print(f"   SPXS Entry: ${spxs_entry_price:.2f}")
    print(f"   SPXS Stop Price: ${spxs_stop_price:.2f} (triggers when price goes ABOVE this)")
    print(f"   Note: When SP500 goes UP, SPXS goes DOWN, but we exit when SPXS goes ABOVE stop")
    
    return spxs_stop_price

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
    
    # Entry logic (same as UPRO but for SPXS)
    if abs(gap_pct) > 1.0:  # Check absolute gap
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
    
    # Check if price is BELOW previous close (INVERSE entry signal - opposite of UPRO)
    if current_price <= prev_close:
        print(f"   ✅ ENTRY CONDITION MET: Price ${current_price:.2f} <= Prev Close ${prev_close:.2f}")
        return True, current_price
    else:
        print(f"   ❌ Price ${current_price:.2f} > Prev Close ${prev_close:.2f}, waiting...")
        return False, None

def main():
    """Main SPXS trading logic"""
    print(f"\n{'#'*60}")
    print(f"# SPXS AUTOMATED TRADING SYSTEM (INVERSE 3X)")
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
    
    trading_enabled = config.get('spxs_trading_enabled', False)
    sp500_stop_price = config.get('sp500_stop_price')
    
    print(f"\n⚙️  Trading Configuration:")
    print(f"   Trading Enabled: {'✅ YES' if trading_enabled else '❌ NO (Position management only)'}")
    print(f"   SP500 Stop Price: {sp500_stop_price:.2f}" if sp500_stop_price else "   SP500 Stop: Not set")
    print(f"   Last Updated: {config.get('last_updated', 'Unknown')}")
    
    # Get previous close
    prev_close = get_previous_close(SYMBOL)
    if not prev_close:
        print(f"❌ Cannot get previous close for {SYMBOL}")
        return
    
    # Get SPY open for stop calculation
    spy_open = get_spy_open()
    
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
        
        # Calculate dynamic stop
        if sp500_stop_price and spy_open:
            spxs_stop_price = calculate_dynamic_stop(sp500_stop_price, spy_open, entry_price)
            
            # SPXS is inverse: stop triggers when price goes ABOVE stop (not below)
            if spxs_stop_price and current_price >= spxs_stop_price:
                print(f"\n🚨 STOP LOSS TRIGGERED!")
                print(f"   Current: ${current_price:.2f} >= Stop: ${spxs_stop_price:.2f}")
                place_market_order(SYMBOL, qty, 'sell')
                return
        
        # Check if it's near market close (15:58 ET = 20:58 UTC)
        now = datetime.now()
        if now.hour == 20 and now.minute >= 58:
            print(f"\n⏰ Near market close (15:58 ET), closing position...")
            place_market_order(SYMBOL, qty, 'sell')
        else:
            print(f"\n✅ Position OK, monitoring continues...")
    
    else:
        # No position - check if trading is enabled today
        print(f"\n💤 No open position")
        
        if not trading_enabled:
            print(f"\n🚫 Trading disabled for today (spxs_trading_enabled = false)")
            print(f"   Only position management is active.")
            print(f"   To enable trading, set 'spxs_trading_enabled: true' in spxs_config.json")
            return
        
        print(f"\n✅ Trading enabled for today, checking entry conditions...")
        
        should_enter, entry_price = check_entry_conditions(SYMBOL, prev_close)
        
        if should_enter:
            print(f"\n🚀 ENTERING POSITION!")
            place_market_order(SYMBOL, QUANTITY, 'buy')
        else:
            print(f"\n⏳ Entry conditions not met, waiting...")
    
    print(f"\n{'#'*60}")
    print(f"# SPXS monitoring cycle completed")
    print(f"{'#'*60}\n")

if __name__ == "__main__":
    main()