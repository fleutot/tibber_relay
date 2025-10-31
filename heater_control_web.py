#!/usr/bin/env python3
"""
Flask web server for controlling heating element parameters.
Communicates with tibber_relay.py via WebSocket for real-time updates.
"""

from flask import Flask, render_template_string
from flask_sock import Sock
import json
import asyncio
import websockets
import threading
import os

app = Flask(__name__)
sock = Sock(app)

# WebSocket clients connected to this Flask app
flask_clients = []
# Connection to tibber_relay WebSocket server
relay_ws = None
relay_ws_lock = threading.Lock()

# HTML template with WebSocket integration
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Heater Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .status-bar {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
            margin-bottom: 20px;
            font-size: 14px;
        }
        .status-item {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #ccc;
        }
        .status-indicator.connected {
            background: #4CAF50;
            animation: pulse 2s infinite;
        }
        .status-indicator.relay-on {
            background: #ff9800;
        }
        .status-indicator.relay-off {
            background: #9e9e9e;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .current-price {
            font-size: 24px;
            font-weight: bold;
            color: #2196F3;
            margin: 10px 0;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            color: #555;
            font-weight: bold;
        }
        input[type="number"], select {
            width: 100%;
            padding: 10px;
            border: 1px solid #ddd;
            border-radius: 5px;
            font-size: 16px;
        }
        .checkbox-group {
            display: flex;
            align-items: center;
            padding: 10px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        input[type="checkbox"] {
            width: 20px;
            height: 20px;
            margin-right: 10px;
        }
        button {
            background-color: #4CAF50;
            color: white;
            padding: 12px 30px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 16px;
            width: 100%;
        }
        button:hover {
            background-color: #45a049;
        }
        button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .success {
            background-color: #d4edda;
            color: #155724;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .warning {
            background-color: #fff3cd;
            color: #856404;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .info {
            background-color: #e7f3ff;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
            font-size: 14px;
            color: #004085;
        }
        .chart-container {
            margin-top: 20px;
            padding: 15px;
            background: #f8f9fa;
            border-radius: 5px;
        }
        .price-bars {
            display: flex;
            gap: 4px;
            align-items: flex-end;
            height: 150px;
            margin-top: 10px;
        }
        .price-bar {
            flex: 1;
            background: #2196F3;
            opacity: 0.6;
            border-radius: 3px 3px 0 0;
            position: relative;
            cursor: pointer;
            transition: opacity 0.2s;
        }
        .price-bar:hover {
            opacity: 1;
        }
        .price-bar.current {
            background: #ff9800;
            opacity: 0.9;
        }
        .price-bar.cheap {
            background: #4CAF50;
        }
        .hidden {
            display: none;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔥 Ack tank</h1>

        <div class="status-bar">
            <div class="status-item">
                <div class="status-indicator" id="wsIndicator"></div>
                <span id="wsStatus">Connecting...</span>
            </div>
            <div class="status-item">
                <div class="status-indicator" id="relayIndicator"></div>
                <span id="relayStatus">Relay: Unknown</span>
            </div>
        </div>

        <div class="warning hidden" id="overrideWarning">
            ⚠️ Manual override active! Automatic control will resume in <span id="overrideHours">0</span> hours.
        </div>

        <div id="successMessage" class="success hidden">
            ✓ Parameters saved successfully!
        </div>

        <div class="current-price" id="currentPrice">
            Current Price: --
        </div>

        <form id="configForm">
            <div class="form-group">
                <label>Control Mode:</label>
                <select name="mode" id="mode">
                    <option value="N_CHEAPEST_TODAY">N Cheapest Hours Today</option>
                    <option value="PRICE_LIMIT">Price Limit</option>
                </select>
            </div>

            <div class="form-group" id="nCheapestGroup">
                <label>Number of Cheapest Hours:</label>
                <input type="number" name="n_cheapest" id="n_cheapest" min="1" max="24" value="8" required>
            </div>

            <div class="form-group hidden" id="priceLimitGroup">
                <label>Max Electricity Price (SEK/kWh):</label>
                <input type="number" name="max_price" id="max_price" step="0.01" value="0.2" required>
            </div>

            <div class="checkbox-group">
                <input type="checkbox" name="enabled" id="enabled" checked>
                <label for="enabled" style="margin-bottom: 0;">Enable automatic control</label>
            </div>

            <button type="submit" id="saveButton">Save Parameters</button>
        </form>

        <div class="chart-container">
            <strong>Today's Prices</strong>
            <div class="price-bars" id="priceChart"></div>
        </div>
    </div>

    <script>
        let ws = null;
        let reconnectInterval = null;

        function connectWebSocket() {
            // Connect to Flask's WebSocket proxy (same origin)
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            ws = new WebSocket(wsUrl);

            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('wsIndicator').classList.add('connected');
                document.getElementById('wsStatus').textContent = 'Connected';
                if (reconnectInterval) {
                    clearInterval(reconnectInterval);
                    reconnectInterval = null;
                }
            };

            ws.onmessage = (event) => {
                const state = JSON.parse(event.data);
                console.log('Received state:', state);
                updateUI(state);
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };

            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('wsIndicator').classList.remove('connected');
                document.getElementById('wsStatus').textContent = 'Disconnected';

                // Try to reconnect every 5 seconds
                if (!reconnectInterval) {
                    reconnectInterval = setInterval(() => {
                        console.log('Attempting to reconnect...');
                        connectWebSocket();
                    }, 5000);
                }
            };
        }

        function updateUI(state) {
            // Update config form
            if (state.config) {
                document.getElementById('mode').value = state.config.mode;
                document.getElementById('n_cheapest').value = state.config.n_cheapest;
                document.getElementById('max_price').value = state.config.max_price;
                document.getElementById('enabled').checked = state.config.enabled;
                toggleModeFields();
            }

            // Update relay status
            if (state.relay_on !== undefined) {
                const relayIndicator = document.getElementById('relayIndicator');
                const relayStatus = document.getElementById('relayStatus');

                if (state.relay_on) {
                    relayIndicator.className = 'status-indicator relay-on';
                    relayStatus.textContent = 'Relay: ON';
                } else {
                    relayIndicator.className = 'status-indicator relay-off';
                    relayStatus.textContent = 'Relay: OFF';
                }
            }

            // Update override warning
            if (state.overridden) {
                document.getElementById('overrideWarning').classList.remove('hidden');
                document.getElementById('overrideHours').textContent = state.override_hours_left || 0;
            } else {
                document.getElementById('overrideWarning').classList.add('hidden');
            }

            // Update current price
            if (state.current_price !== undefined && state.current_price !== null) {
                document.getElementById('currentPrice').textContent =
                    `Current Price: ${state.current_price.toFixed(2)} SEK/kWh`;
            }

            // Update price chart
            if (state.today_prices && state.today_prices.length > 0) {
                updatePriceChart(state.today_prices, state.current_price, state.config);
            }
        }

        function updatePriceChart(prices, currentPrice, config) {
            const chart = document.getElementById('priceChart');
            chart.innerHTML = '';

            if (prices.length === 0) return;

            const maxPrice = Math.max(...prices.map(p => p.price));
            const currentHour = new Date().getHours();

            // Determine which hours are "cheap" based on mode
            let cheapHours = new Set();
            if (config && config.mode === 'N_CHEAPEST_TODAY') {
                const sortedPrices = [...prices].sort((a, b) => a.price - b.price);
                const nCheapest = Math.min(config.n_cheapest, sortedPrices.length);
                for (let i = 0; i < nCheapest; i++) {
                    const time = new Date(sortedPrices[i].time);
                    cheapHours.add(time.getHours());
                }
            }

            prices.forEach(item => {
                const time = new Date(item.time);
                const hour = time.getHours();
                const heightPercent = (item.price / maxPrice) * 100;

                const bar = document.createElement('div');
                bar.className = 'price-bar';
                bar.style.height = `${heightPercent}%`;
                bar.title = `${hour}:00 - ${item.price.toFixed(2)} SEK/kWh`;

                if (hour === currentHour) {
                    bar.classList.add('current');
                }

                if (cheapHours.has(hour)) {
                    bar.classList.add('cheap');
                }

                chart.appendChild(bar);
            });
        }

        function toggleModeFields() {
            const mode = document.getElementById('mode').value;
            const nCheapestGroup = document.getElementById('nCheapestGroup');
            const priceLimitGroup = document.getElementById('priceLimitGroup');

            if (mode === 'N_CHEAPEST_TODAY') {
                nCheapestGroup.classList.remove('hidden');
                priceLimitGroup.classList.add('hidden');
            } else {
                nCheapestGroup.classList.add('hidden');
                priceLimitGroup.classList.remove('hidden');
            }
        }

        document.getElementById('mode').addEventListener('change', toggleModeFields);

        document.getElementById('configForm').addEventListener('submit', (e) => {
            e.preventDefault();

            const config = {
                mode: document.getElementById('mode').value,
                n_cheapest: parseInt(document.getElementById('n_cheapest').value),
                max_price: parseFloat(document.getElementById('max_price').value),
                enabled: document.getElementById('enabled').checked
            };

            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    type: 'config_update',
                    config: config
                }));

                // Show success message
                const msg = document.getElementById('successMessage');
                msg.classList.remove('hidden');
                setTimeout(() => msg.classList.add('hidden'), 3000);
            } else {
                alert('Not connected to controller. Please wait and try again.');
            }
        });

        // Initialize
        toggleModeFields();
        connectWebSocket();
    </script>
</body>
</html>
"""

@sock.route('/ws')
def websocket_proxy(ws):
    """Proxy WebSocket connection between browser and tibber_relay."""
    global flask_clients
    flask_clients.append(ws)
    print(f"Browser client connected. Total: {len(flask_clients)}")

    try:
        while True:
            message = ws.receive()
            if message is None:
                break

            # Forward message to tibber_relay
            with relay_ws_lock:
                if relay_ws:
                    try:
                        asyncio.run(relay_ws.send(message))
                    except Exception as e:
                        print(f"Error forwarding to relay: {e}")
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        flask_clients.remove(ws)
        print(f"Browser client disconnected. Remaining: {len(flask_clients)}")

async def connect_to_relay():
    """Maintain connection to tibber_relay WebSocket and forward messages to browsers."""
    global relay_ws

    while True:
        try:
            async with websockets.connect('ws://127.0.0.1:8765') as websocket:
                print("Connected to tibber_relay WebSocket")
                with relay_ws_lock:
                    relay_ws = websocket

                async for message in websocket:
                    # Broadcast to all connected browser clients
                    disconnected = []
                    for client in flask_clients[:]:
                        try:
                            client.send(message)
                        except Exception as e:
                            print(f"Error sending to client: {e}")
                            disconnected.append(client)

                    # Clean up disconnected clients
                    for client in disconnected:
                        if client in flask_clients:
                            flask_clients.remove(client)

        except Exception as e:
            print(f"Relay connection error: {e}. Reconnecting in 5s...")
            with relay_ws_lock:
                relay_ws = None
            await asyncio.sleep(5)

def run_relay_connection():
    """Run relay connection in background thread."""
    asyncio.run(connect_to_relay())

@app.route('/')
def index():
    """Main page with real-time WebSocket updates."""
    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    # Start background thread to connect to tibber_relay
    relay_thread = threading.Thread(target=run_relay_connection, daemon=True)
    relay_thread.start()

    # Bind to localhost - Tailscale will handle external access
    app.run(host='127.0.0.1', port=5000, debug=False)
