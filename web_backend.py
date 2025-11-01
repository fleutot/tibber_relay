#!/bin/env python3
"""
Web backend for Tibber Relay control.
Provides a Flask API for monitoring and controlling the relay via web interface.
Access restricted to Tailscale network (100.x.x.x).

Communicates with tibber_relay service via HTTP API on localhost:8001
"""
from flask import Flask, jsonify, request, abort, send_from_directory
from datetime import datetime
import requests
import sys

app = Flask(__name__, static_folder='static')

# Relay service API endpoint (localhost only)
RELAY_API = 'http://127.0.0.1:8001/api'

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
        response = requests.get(f'{RELAY_API}/status', timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/prices')
def get_prices():
    """Get all available price data (today + tomorrow)."""
    try:
        response = requests.get(f'{RELAY_API}/prices', timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/relay/on', methods=['POST'])
def turn_relay_on():
    """Manually turn relay on."""
    try:
        response = requests.post(f'{RELAY_API}/command', json={'command': 'turn_on'}, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/relay/off', methods=['POST'])
def turn_relay_off():
    """Manually turn relay off."""
    try:
        response = requests.post(f'{RELAY_API}/command', json={'command': 'turn_off'}, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/config')
def get_config():
    """Get current configuration."""
    try:
        response = requests.get(f'{RELAY_API}/config', timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'error': f'Failed to communicate with relay service: {str(e)}'}), 503

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
