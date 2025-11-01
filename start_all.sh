#!/usr/bin/env bash
#
# Start both Tibber Relay services
# - tibber_relay.py: Core relay control + API (localhost:8001)
# - web_backend.py: Web dashboard (port 8000, Tailscale protected)
#

script_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$script_dir"

# Set up virtual environment
venv_dir="$script_dir/venv"
python_bin=python3

if [ ! -d "$venv_dir" ]; then
    echo "Creating virtual environment..."
    $python_bin -m venv "$venv_dir"
fi

source "$venv_dir/bin/activate"

if [ -f "requirements.txt" ]; then
    echo "Installing dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

# Start relay service (with internal API on localhost:8001)
relay_script="tibber_relay.py"
relay_log="tibber_relay.log"

echo "Starting relay service ($relay_script)..."
nohup $python_bin -u "$relay_script" >> "$relay_log" 2>&1 &
relay_pid=$!
echo "Relay service started (PID: $relay_pid)"

# Give relay service time to start API server
sleep 2

# Start web backend (proxies to relay API)
web_script="web_backend.py"
web_log="web_backend.log"

echo "Starting web backend ($web_script)..."
nohup $python_bin -u "$web_script" >> "$web_log" 2>&1 &
web_pid=$!
echo "Web backend started (PID: $web_pid)"

echo ""
echo "========================================="
echo "Both services started successfully!"
echo "========================================="
echo "Relay Service:"
echo "  PID: $relay_pid"
echo "  API: http://127.0.0.1:8001 (localhost only)"
echo "  Log: $relay_log"
echo ""
echo "Web Backend:"
echo "  PID: $web_pid"
echo "  Dashboard: http://<tailscale-ip>:8000/"
echo "  Log: $web_log"
echo ""
echo "To stop services:"
echo "  kill $relay_pid $web_pid"
echo ""
echo "To view logs:"
echo "  tail -f $relay_log"
echo "  tail -f $web_log"
echo "========================================="
