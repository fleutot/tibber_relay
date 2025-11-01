#!/usr/bin/env bash
#
# Start both Tibber Relay service and Web Backend
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

# Start relay service
relay_script="tibber_relay.py"
relay_log="tibber_relay.log"

echo "Starting relay service ($relay_script)..."
nohup $python_bin -u "$relay_script" >> "$relay_log" 2>&1 &
relay_pid=$!
echo "Relay service started (PID: $relay_pid)"

# Give the relay service a moment to initialize
sleep 2

# Start web backend
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
echo "Relay service PID: $relay_pid"
echo "  Log file: $relay_log"
echo ""
echo "Web backend PID: $web_pid"
echo "  Log file: $web_log"
echo ""
echo "Access dashboard at: http://<tailscale-ip>:8000/"
echo ""
echo "To stop services:"
echo "  kill $relay_pid $web_pid"
echo ""
echo "To view logs:"
echo "  tail -f $relay_log"
echo "  tail -f $web_log"
echo "========================================="
