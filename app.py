from flask import Flask, render_template, request, jsonify
from binance.um_futures import UMFutures
import os
from decimal import Decimal, ROUND_DOWN

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
client = UMFutures(key=API_KEY, secret=API_SECRET)

# Cache for symbol info to avoid repeated API calls
symbol_info_cache = {}

def get_symbol_precision(symbol):
    """Get price precision for a symbol from Binance exchange info"""
    if symbol in symbol_info_cache:
        return symbol_info_cache[symbol]
    
    try:
        exchange_info = client.exchange_info()
        for symbol_data in exchange_info['symbols']:
            if symbol_data['symbol'] == symbol:
                # Find price precision from filters
                for filter_data in symbol_data['filters']:
                    if filter_data['filterType'] == 'PRICE_FILTER':
                        tick_size = filter_data['tickSize']
                        # Count decimal places in tick size
                        precision = len(tick_size.rstrip('0').split('.')[-1]) if '.' in tick_size else 0
                        symbol_info_cache[symbol] = precision
                        return precision
        
        # Default precision if not found
        symbol_info_cache[symbol] = 8
        return 8
    except Exception as e:
        print(f"Error getting symbol precision: {e}")
        # Return default precision
        return 8

def round_price(price, precision):
    """Round price to the correct precision"""
    if precision == 0:
        return int(price)
    
    # Use Decimal for precise rounding
    decimal_price = Decimal(str(price))
    multiplier = Decimal('10') ** precision
    rounded = (decimal_price * multiplier).quantize(Decimal('1'), rounding=ROUND_DOWN) / multiplier
    return float(rounded)

def get_best_bid_ask(symbol):
    """Get the best bid and ask prices from order book"""
    try:
        order_book = client.depth(symbol=symbol, limit=5)
        best_bid = float(order_book['bids'][0][0])  # Best bid price
        best_ask = float(order_book['asks'][0][0])  # Best ask price
        return best_bid, best_ask
    except Exception as e:
        print(f"Error getting order book: {e}")
        # Fallback to ticker price
        ticker = client.ticker_price(symbol=symbol)
        current_price = float(ticker['price'])
        return current_price, current_price

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/execute_trade', methods=['POST'])
def execute_trade():
    try:
        data = request.json
        symbol = data['symbol']
        quantity = data['quantity']

        # Get symbol precision
        precision = get_symbol_precision(symbol)

        if data['type'] == 'limit':
            side = data['side']
            price = round_price(data['price'], precision)

            client.new_order(
                symbol=symbol,
                side=side,
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=price
            )
            return jsonify({'success': True, 'message': f'✅ Limit {side.lower()} order placed at ${price}'})
                
        elif data['type'] == 'chase':
            side = data['side']
            
            # Get best bid and ask prices
            best_bid, best_ask = get_best_bid_ask(symbol)
            
            if side == 'BUY':
                # For buy orders, use best bid price to get better position in queue
                chase_price = round_price(best_bid, precision)
                order_side = 'BUY'
            else:
                # For sell orders, use best ask price to get better position in queue
                chase_price = round_price(best_ask, precision)
                order_side = 'SELL'
            
            try:
                client.new_order(
                    symbol=symbol,
                    side=order_side,
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=quantity,
                    price=chase_price
                )
                return jsonify({
                    'success': True, 
                    'message': f'✅ Chase {side.lower()} order placed at ${chase_price} (Best {"Bid" if side == "BUY" else "Ask"})'
                })
            except Exception as e:
                return jsonify({'success': False, 'message': f'Chase order failed: {str(e)}'})

        elif data['type'] == 'stop':
            stop_price = round_price(data['stop_price'], precision)
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs stop price
            if stop_price > current_price:
                primary_side = 'BUY'
                secondary_side = 'SELL'
            else:
                primary_side = 'SELL'
                secondary_side = 'BUY'
            
            # Try primary side first
            try:
                client.new_order(
                    symbol=symbol,
                    side=primary_side,
                    type='STOP',
                    timeInForce='GTC',
                    quantity=quantity,
                    stopPrice=stop_price,
                    price=stop_price,
                    reduceOnly=True
                )
                return jsonify({'success': True, 'message': f'✅ Stop-limit order placed ({primary_side} side) at ${stop_price}.'})
            
            except Exception as primary_error:
                if "-2021" in str(primary_error) or "would immediately trigger" in str(primary_error).lower():
                    try:
                        client.new_order(
                            symbol=symbol,
                            side=secondary_side,
                            type='STOP',
                            timeInForce='GTC',
                            quantity=quantity,
                            stopPrice=stop_price,
                            price=stop_price,
                            reduceOnly=True
                        )
                        return jsonify({'success': True, 'message': f'✅ Stop-limit order placed ({secondary_side} side) at ${stop_price}.'})
                    except Exception as secondary_error:
                        return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})
                else:
                    return jsonify({'success': False, 'message': str(primary_error)})

        elif data['type'] == 'market_stop':
            stop_price = round_price(data['stop_price'], precision)
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs stop price
            if stop_price > current_price:
                primary_side = 'BUY'
                secondary_side = 'SELL'
            else:
                primary_side = 'SELL'
                secondary_side = 'BUY'
            
            # Try primary side first with STOP_MARKET order
            try:
                client.new_order(
                    symbol=symbol,
                    side=primary_side,
                    type='STOP_MARKET',
                    timeInForce='GTC',
                    quantity=quantity,
                    stopPrice=stop_price,
                    reduceOnly=True
                )
                return jsonify({'success': True, 'message': f'✅ Market stop order placed ({primary_side} side) at ${stop_price}.'})
            
            except Exception as primary_error:
                if "-2021" in str(primary_error) or "would immediately trigger" in str(primary_error).lower():
                    try:
                        client.new_order(
                            symbol=symbol,
                            side=secondary_side,
                            type='STOP_MARKET',
                            timeInForce='GTC',
                            quantity=quantity,
                            stopPrice=stop_price,
                            reduceOnly=True
                        )
                        return jsonify({'success': True, 'message': f'✅ Market stop order placed ({secondary_side} side) at ${stop_price}.'})
                    except Exception as secondary_error:
                        return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})
                else:
                    return jsonify({'success': False, 'message': str(primary_error)})

        elif data['type'] == 'market':
            side = data['side']
            
            client.new_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            return jsonify({'success': True, 'message': f'✅ Market {side.lower()} order executed.'})

        elif data['type'] == 'take_profit':
            target_price = round_price(data['target_price'], precision)
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs target price
            if target_price > current_price:
                primary_side = 'SELL'
                secondary_side = 'BUY'
            else:
                primary_side = 'BUY'
                secondary_side = 'SELL'
            
            # Try primary side first with LIMIT order for better fees (market maker)
            try:
                client.new_order(
                    symbol=symbol,
                    side=primary_side,
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=quantity,
                    price=target_price,
                    reduceOnly=True
                )
                return jsonify({'success': True, 'message': f'✅ Take profit limit order placed ({primary_side} side) at ${target_price} - Market maker fees!'})
            
            except Exception as primary_error:
                try:
                    client.new_order(
                        symbol=symbol,
                        side=secondary_side,
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=quantity,
                        price=target_price,
                        reduceOnly=True
                    )
                    return jsonify({'success': True, 'message': f'✅ Take profit limit order placed ({secondary_side} side) at ${target_price} - Market maker fees!'})
                except Exception as secondary_error:
                    return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})

        elif data['type'] == 'auto_sl_tp':
            rr_percentage = data['rr_percentage'] / 100
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Get current position to determine direction
            try:
                positions = client.get_position_risk(symbol=symbol)
                position_amt = 0
                for pos in positions:
                    if pos['symbol'] == symbol:
                        position_amt = float(pos['positionAmt'])
                        break
                
                if position_amt == 0:
                    return jsonify({'success': False, 'message': 'No open position found for this symbol.'})
                
                # Determine if long or short position
                is_long = position_amt > 0
                
                if is_long:
                    # Long position: SL below current price, TP above current price
                    sl_price = round_price(current_price * (1 - rr_percentage), precision)
                    tp_price = round_price(current_price * (1 + rr_percentage), precision)
                    sl_side = 'SELL'
                    tp_side = 'SELL'
                else:
                    # Short position: SL above current price, TP below current price
                    sl_price = round_price(current_price * (1 + rr_percentage), precision)
                    tp_price = round_price(current_price * (1 - rr_percentage), precision)
                    sl_side = 'BUY'
                    tp_side = 'BUY'
                
                # Use absolute value of position amount for order quantity
                position_quantity = abs(position_amt)
                
                results = []
                
                # Place Stop Loss
                try:
                    client.new_order(
                        symbol=symbol,
                        side=sl_side,
                        type='STOP',
                        timeInForce='GTC',
                        quantity=position_quantity,
                        stopPrice=sl_price,
                        price=sl_price,
                        reduceOnly=True
                    )
                    results.append(f'✅ Stop Loss set at ${sl_price}')
                except Exception as sl_error:
                    results.append(f'❌ Stop Loss failed: {str(sl_error)}')
                
                # Place Take Profit (Limit Order)
                try:
                    client.new_order(
                        symbol=symbol,
                        side=tp_side,
                        type='LIMIT',
                        timeInForce='GTC',
                        quantity=position_quantity,
                        price=tp_price,
                        reduceOnly=True
                    )
                    results.append(f'✅ Take Profit set at ${tp_price}')
                except Exception as tp_error:
                    results.append(f'❌ Take Profit failed: {str(tp_error)}')
                
                return jsonify({'success': True, 'message': ' | '.join(results)})
                
            except Exception as e:
                return jsonify({'success': False, 'message': f'Error getting position: {str(e)}'})

        else:
            return jsonify({'success': False, 'message': 'Invalid order type.'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)