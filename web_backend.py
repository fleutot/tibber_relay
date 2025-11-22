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
import os
import json

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
    """Manually turn relay on with optional override duration."""
    try:
        data = request.get_json() or {}
        payload = {'command': 'turn_on'}
        if 'override_hours' in data:
            payload['override_hours'] = data['override_hours']

        response = requests.post(f'{RELAY_API}/command', json=payload, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/relay/off', methods=['POST'])
def turn_relay_off():
    """Manually turn relay off with optional override duration."""
    try:
        data = request.get_json() or {}
        payload = {'command': 'turn_off'}
        if 'override_hours' in data:
            payload['override_hours'] = data['override_hours']

        response = requests.post(f'{RELAY_API}/command', json=payload, timeout=5)
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

@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration (mode, price limit, n_cheapest)."""
    try:
        data = request.get_json()
        response = requests.post(f'{RELAY_API}/config', json=data, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/resume', methods=['POST'])
def resume_automatic():
    """Resume automatic control by clearing override."""
    try:
        response = requests.post(f'{RELAY_API}/resume', timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        return jsonify({'success': False, 'error': f'Failed to communicate with relay service: {str(e)}'}), 503

@app.route('/api/state_history')
def get_state_history():
    """Get relay state history (filtered to today)."""
    state_log_file = os.path.join(os.path.dirname(__file__), 'relay_state_log.json')

    if not os.path.exists(state_log_file):
        return jsonify({'states': []})

    try:
        with open(state_log_file, 'r') as f:
            all_states = json.load(f)

        # Filter to only today's entries
        today = datetime.now().date()
        today_states = [
            s for s in all_states
            if datetime.fromisoformat(s['time']).date() == today
        ]

        return jsonify({'states': today_states})
    except Exception as e:
        return jsonify({'error': f'Failed to read state history: {str(e)}'}), 500

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
    # Port can be configured via environment variable
    # Default: 8000 for manual runs, systemd can set PORT=8080
    port = int(os.getenv('PORT', 8000))

    print("Starting Tibber Relay Web Backend...")
    print("Access restricted to Tailscale network (100.x.x.x)")
    print(f"Dashboard available at http://<tailscale-ip>:{port}/")

    # Run on all interfaces, protected by Tailscale middleware
    app.run(host='0.0.0.0', port=port, debug=False)
