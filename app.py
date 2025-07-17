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
            leverage = data['leverage']

            client.cancel_open_orders(symbol=symbol)
            client.change_leverage(symbol=symbol, leverage=leverage)

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

        else:
            return jsonify({'success': False, 'message': 'Invalid order type.'})

    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

if __name__ == '__main__':
    app.run(debug=True)