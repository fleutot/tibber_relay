# Tibber Relay Controller

Controls a Shelly Pro 1 relay based on Tibber electricity prices. Runs scheduled price fetching and automatic relay control, with web dashboard for monitoring and manual override.

**Hardware:** Tested on Raspberry Pi 3A+ and Linux laptops with Shelly Pro 1 relay.

## Architecture

Two independent services communicate via HTTP:

- **tibber_relay.py** (port 8001): Price fetching (daily 21:42), hourly relay control, Shelly hardware interface
- **web_backend.py** (port 8000/8080): Web dashboard, API proxy, Tailscale-protected

## Setup

### Secrets

Create `.env` in project root:
```
TIBBER_API_TOKEN=your_token_here
```

### Dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Running

### Manual (development)

```bash
./start_all.sh  # Starts both services on port 8000
./stop.sh       # Stops services
```

### Systemd (production)

```bash
# Install
sudo cp tibber_relay.service tibber_relay_web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tibber_relay.service tibber_relay_web.service
sudo systemctl start tibber_relay.service tibber_relay_web.service

# Manage
sudo systemctl status tibber_relay_web.service
sudo systemctl restart tibber_relay_web.service
sudo journalctl -u tibber_relay_web.service -f
```

**Note:** Systemd runs web backend on port 8080 (configurable via `PORT` environment variable).

## Web Dashboard

Access via Tailscale IP:
```
http://<tailscale-ip>:8000/  # Manual run
http://<tailscale-ip>:8080/  # Systemd
```

Find Tailscale IP: `tailscale ip -4`

**Security:** Only Tailscale network (100.x.x.x) and localhost can access.

### Features

- **Relay status** with manual ON/OFF controls
- **Real-time price** display (updates every 5s)
- **Price graph** with mode-specific coloring:
  - Green bars: N cheapest hours mode
  - Blue bars: Price limit mode (with threshold line)
  - Vivid shade indicates current hour

### Operating Modes

**Price Limit:** Relay ON when price < configured limit (blue bars)
**N Cheapest Today:** Relay ON during N cheapest hours (green bars)

Manual controls trigger configurable override period (pauses automatic control).

## API Endpoints

### GET `/api/status`
```json
{
  "relay_on": true,
  "current_price": 0.15,
  "mode": "PRICE_LIMIT",
  "override_hours_left": 0
}
```

### GET `/api/prices`
```json
{
  "prices": [{"time": "2025-11-01T00:00:00", "price": 0.18}],
  "n_cheapest_limit": 5
}
```

### GET `/api/config`
```json
{
  "mode": "PRICE_LIMIT",
  "price_limit_sek": 0.20,
  "n_cheapest_limit": 5,
  "relay_ip": "192.168.1.106"
}
```

### POST `/api/config`
Update configuration (mode, limits).

### POST `/api/relay/on|off`
Manual relay control with override.

### POST `/api/resume`
Cancel manual override, resume automatic control.

## Logs

```bash
# Manual runs
tail -f web_backend.log

# Systemd runs
sudo journalctl -u tibber_relay_web.service -f
```

## Troubleshooting

**403 Forbidden:** Not on Tailscale network. Test with `curl http://localhost:8000/api/status`

**Port conflict:** Change port in service file or use `lsof -i :8080` to find conflicting process.

**No prices:** Check logs for Tibber API errors, verify token in `.env`.

**Relay not responding:** Verify Shelly accessibility: `curl http://<relay-ip>/rpc/Shelly.GetStatus?id=0`

## Development

**Disable Tailscale check:** Comment out `@app.before_request` in `web_backend.py`

**Customize dashboard:** Edit `static/index.html`

## References

Tibber API: https://developer.tibber.com/docs/reference
