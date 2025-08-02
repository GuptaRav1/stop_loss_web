from flask import Flask, render_template, request, jsonify
from binance.um_futures import UMFutures
import os

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
API_SECRET = os.getenv("API_SECRET")
client = UMFutures(key=API_KEY, secret=API_SECRET)

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/execute_trade', methods=['POST'])
def execute_trade():
    try:
        data = request.json
        symbol = data['symbol']
        quantity = data['quantity']

        if data['type'] == 'limit':
            buy_price = data['buy_price']
            sell_price = data['sell_price']
            # leverage = data['leverage']

            client.cancel_open_orders(symbol=symbol)
            # client.change_leverage(symbol=symbol, leverage=leverage)

            client.new_order(
                symbol=symbol,
                side='BUY',
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=buy_price
            )
            client.new_order(
                symbol=symbol,
                side='SELL',
                type='LIMIT',
                timeInForce='GTC',
                quantity=quantity,
                price=sell_price
            )
            return jsonify({'success': True, 'message': '✅ Limit orders placed.'})

        elif data['type'] == 'stop':
            stop_price = data['stop_price']
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs stop price
            if stop_price > current_price:
                # Stop price is above current price, so we want to BUY when price goes up
                primary_side = 'BUY'
                secondary_side = 'SELL'
            else:
                # Stop price is below current price, so we want to SELL when price goes down
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
                return jsonify({'success': True, 'message': f'✅ Stop-limit order placed ({primary_side} side).'})
            
            except Exception as primary_error:
                # If primary side fails with trigger error, try secondary side
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
                        return jsonify({'success': True, 'message': f'✅ Stop-limit order placed ({secondary_side} side).'})
                    except Exception as secondary_error:
                        return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})
                else:
                    # If it's not a trigger error, return the original error
                    return jsonify({'success': False, 'message': str(primary_error)})

        elif data['type'] == 'market_stop':
            stop_price = data['stop_price']
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs stop price
            if stop_price > current_price:
                # Stop price is above current price, so we want to BUY when price goes up
                primary_side = 'BUY'
                secondary_side = 'SELL'
            else:
                # Stop price is below current price, so we want to SELL when price goes down
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
                return jsonify({'success': True, 'message': f'✅ Market stop order placed ({primary_side} side).'})
            
            except Exception as primary_error:
                # If primary side fails with trigger error, try secondary side
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
                        return jsonify({'success': True, 'message': f'✅ Market stop order placed ({secondary_side} side).'})
                    except Exception as secondary_error:
                        return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})
                else:
                    # If it's not a trigger error, return the original error
                    return jsonify({'success': False, 'message': str(primary_error)})

        elif data['type'] == 'market':
            side = data['side']  # 'BUY' or 'SELL'
            # leverage = data.get('leverage')
            
            # if leverage:
                # client.change_leverage(symbol=symbol, leverage=leverage)
            
            client.new_order(
                symbol=symbol,
                side=side,
                type='MARKET',
                quantity=quantity
            )
            return jsonify({'success': True, 'message': f'✅ Market {side.lower()} order executed.'})

        elif data['type'] == 'take_profit':
            target_price = data['target_price']
            
            # Get current market price
            ticker = client.ticker_price(symbol=symbol)
            current_price = float(ticker['price'])
            
            # Determine the appropriate side based on current price vs target price
            if target_price > current_price:
                # Target price is above current price, so we want to SELL when price goes up (take profit on long)
                primary_side = 'SELL'
                secondary_side = 'BUY'
            else:
                # Target price is below current price, so we want to BUY when price goes down (take profit on short)
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
                return jsonify({'success': True, 'message': f'✅ Take profit limit order placed ({primary_side} side) - Market maker fees!'})
            
            except Exception as primary_error:
                # If primary side fails, try secondary side
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
                    return jsonify({'success': True, 'message': f'✅ Take profit limit order placed ({secondary_side} side) - Market maker fees!'})
                except Exception as secondary_error:
                    return jsonify({'success': False, 'message': f'Both sides failed. Primary: {str(primary_error)}, Secondary: {str(secondary_error)}'})

        elif data['type'] == 'auto_sl_tp':
            rr_percentage = data['rr_percentage'] / 100  # Convert percentage to decimal (same for both SL and TP)
            
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
                    sl_price = current_price * (1 - rr_percentage)
                    tp_price = current_price * (1 + rr_percentage)
                    sl_side = 'SELL'
                    tp_side = 'SELL'
                else:
                    # Short position: SL above current price, TP below current price
                    sl_price = current_price * (1 + rr_percentage)
                    tp_price = current_price * (1 - rr_percentage)
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
                    results.append(f'✅ Stop Loss set at ${sl_price:.6f}')
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
                    results.append(f'✅ Take Profit set at ${tp_price:.6f}')
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