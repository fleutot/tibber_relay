# Tibber Relay Web Interface - Usage Guide

## Architecture Overview

Your system now consists of **two independent services**:

```
┌─────────────────────────────────────────┐
│  1. Relay Service (tibber_relay.py)     │
│     - Scheduled price fetching          │
│     - Automatic relay control           │
│     - Runs independently                │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│  2. Web Backend (web_backend.py)        │
│     - Flask API server                  │
│     - Serves web dashboard              │
│     - Tailscale-protected               │
│     - Port: 8000                        │
└─────────────────────────────────────────┘
```

## Starting the Services

### Option 1: Start Both Services Together (Recommended)
```bash
./start_all.sh
```

This will:
- Create/activate Python virtual environment
- Install dependencies (including Flask)
- Start relay service in background
- Start web backend in background
- Show PIDs and log file locations

### Option 2: Start Services Individually

**Start relay service only:**
```bash
./start.sh
```

**Start web backend only:**
```bash
source venv/bin/activate
python3 web_backend.py
```

## Accessing the Dashboard

1. **Find your Tailscale IP:**
   ```bash
   tailscale ip -4
   ```

2. **Open in browser:**
   ```
   http://<your-tailscale-ip>:8000/
   ```

3. **From localhost (for testing):**
   ```
   http://localhost:8000/
   ```

## Security

The web interface is **protected by Tailscale**:
- Only clients on your Tailscale network (100.x.x.x) can access it
- Localhost (127.0.0.1) is allowed for testing
- Other IPs receive a 403 Forbidden error

To disable Tailscale restriction temporarily:
- Comment out the `@app.before_request` section in `web_backend.py`

## Web Dashboard Features

The dashboard provides:

### 1. **Relay Status Card**
   - Current relay state (ON/OFF)
   - Operating mode (PRICE_LIMIT or N_CHEAPEST_TODAY)
   - Manual override indicator
   - Manual control buttons

### 2. **Current Price Card**
   - Real-time electricity price (SEK/kWh)
   - Updates every 5 seconds

### 3. **Price Graph**
   - Today's hourly prices
   - Cheapest hours highlighted in green
   - Auto-updates every minute

### 4. **Manual Controls**
   - Turn ON button - forces relay on
   - Turn OFF button - forces relay off
   - Triggers 5-hour override (automatic control paused)

## API Endpoints

### GET `/api/status`
Returns current system status:
```json
{
  "relay_on": true,
  "current_price": 0.15,
  "mode": "N_CHEAPEST_TODAY",
  "override_hours_left": 0,
  "timestamp": "2025-11-01T10:30:00"
}
```

### GET `/api/prices`
Returns all available price data:
```json
{
  "prices": [
    {"time": "2025-11-01T00:00:00", "price": 0.18},
    {"time": "2025-11-01T01:00:00", "price": 0.15}
  ],
  "n_cheapest_limit": 5
}
```

### POST `/api/relay/on`
Manually turn relay on:
```json
{"success": true, "message": "Relay turned on"}
```

### POST `/api/relay/off`
Manually turn relay off:
```json
{"success": true, "message": "Relay turned off"}
```

### GET `/api/config`
Get current configuration:
```json
{
  "mode": "N_CHEAPEST_TODAY",
  "n_cheapest_limit": 5,
  "manual_override_runs": 5,
  "relay_ip": "192.168.1.106"
}
```

## Monitoring

### View Logs
```bash
# Relay service logs
tail -f tibber_relay.log

# Web backend logs
tail -f web_backend.log
```

### Check Running Processes
```bash
ps aux | grep python
```

### Stop Services
```bash
# Find PIDs
ps aux | grep "tibber_relay.py\|web_backend.py"

# Kill by PID
kill <relay_pid> <web_pid>

# Or kill all Python processes (careful!)
pkill -f "tibber_relay.py"
pkill -f "web_backend.py"
```

## Future Expansion

The current architecture makes it easy to add more services:

### Option 1: Add routes to web_backend.py
```python
# Import new service
from solar_monitor import solar_panel

@app.route('/api/solar/status')
def solar_status():
    return jsonify(solar_panel.get_status())
```

### Option 2: Run new service with its own API
```python
# solar_service.py - runs on port 8001
app.run(port=8001)

# web_backend.py aggregates
@app.route('/api/solar/status')
def solar_status():
    response = requests.get('http://localhost:8001/status')
    return response.json()
```

## Troubleshooting

### "403 Forbidden" Error
- Check you're accessing from Tailscale network
- Verify with: `curl http://localhost:8000/api/status`
- Temporarily disable Tailscale check in `web_backend.py`

### Services Not Starting
- Check logs: `tail -f tibber_relay.log web_backend.log`
- Verify virtual environment: `source venv/bin/activate`
- Check dependencies: `pip install -r requirements.txt`

### Relay Not Updating
- The relay service is independent - web backend just reads its state
- Check relay service is running: `ps aux | grep tibber_relay`
- Manual controls trigger 5-hour override period

### Port 8000 Already in Use
- Find process: `lsof -i :8000`
- Kill process: `kill <pid>`
- Or change port in `web_backend.py`: `app.run(port=9000)`

## Development

### Testing Locally (Without Tailscale)
Comment out the Tailscale middleware in `web_backend.py`:
```python
# @app.before_request
# def require_tailscale():
#     ...
```

### Adding New API Endpoints
Edit `web_backend.py`:
```python
@app.route('/api/new-endpoint')
def new_endpoint():
    # Your logic here
    return jsonify({'data': 'value'})
```

### Customizing the Dashboard
Edit `static/index.html` - it's a self-contained HTML file with embedded CSS and JavaScript.
