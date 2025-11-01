#!/bin/env python3
"""
Web backend for Tibber Relay control.
Provides a Flask API for monitoring and controlling the relay via web interface.
Access restricted to Tailscale network (100.x.x.x).
"""
from flask import Flask, jsonify, request, abort, send_from_directory
from datetime import datetime
import sys

# Import relay components from existing script
from tibber_relay import relay, price_list, RelayMode

app = Flask(__name__, static_folder='static')

# Tailscale security middleware
@app.before_request
def require_tailscale():
    """Only allow requests from Tailscale network (100.x.x.x)."""
    client_ip = request.remote_addr

    # Allow localhost for development/testing
    if client_ip in ['127.0.0.1', 'localhost', '::1']:
        return None

    # Require Tailscale IP range (100.64.0.0/10)
    if not client_ip.startswith('100.'):
        print(f"Blocked request from non-Tailscale IP: {client_ip}", file=sys.stderr)
        abort(403, description="Access restricted to Tailscale network")

    return None

# API Endpoints

@app.route('/api/status')
def get_status():
    """Get current relay status, price, and system state."""
    try:
        current_price = price_list.price_now_get()
    except Exception as e:
        current_price = None

    relay_on = relay.status_get()

    return jsonify({
        'relay_on': relay_on,
        'current_price': current_price,
        'mode': relay._mode.name,
        'override_hours_left': relay._overridden_hours_left,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/api/prices')
def get_prices():
    """Get all available price data (today + tomorrow)."""
    prices = [
        {
            'time': time.isoformat(),
            'price': price
        }
        for time, price in sorted(price_list.data.items())
    ]

    return jsonify({
        'prices': prices,
        'n_cheapest_limit': price_list.n_cheapest_limit
    })

@app.route('/api/relay/on', methods=['POST'])
def turn_relay_on():
    """Manually turn relay on."""
    try:
        relay.turn(True)
        return jsonify({'success': True, 'message': 'Relay turned on'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/relay/off', methods=['POST'])
def turn_relay_off():
    """Manually turn relay off."""
    try:
        relay.turn(False)
        return jsonify({'success': True, 'message': 'Relay turned off'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config')
def get_config():
    """Get current configuration."""
    return jsonify({
        'mode': relay._mode.name,
        'n_cheapest_limit': price_list.n_cheapest_limit,
        'manual_override_runs': relay.manual_override_nb_runs,
        'relay_ip': relay._ip
    })

# Serve static files (HTML/CSS/JS)
@app.route('/')
def index():
    """Serve main dashboard page."""
    return send_from_directory('static', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve other static files."""
    return send_from_directory('static', path)

if __name__ == '__main__':
    print("Starting Tibber Relay Web Backend...")
    print("Access restricted to Tailscale network (100.x.x.x)")
    print("Dashboard available at http://<tailscale-ip>:8000/")

    # Run on all interfaces, but protected by Tailscale middleware
    app.run(host='0.0.0.0', port=8000, debug=False)
