#!/usr/bin/env bash
#
# Stop Tibber Relay services
#

echo "Stopping Tibber Relay services..."

pkill -f tibber_relay.py
pkill -f web_backend.py

# Wait a moment to let processes terminate
sleep 1

# Check if any processes are still running
if pgrep -f "tibber_relay.py|web_backend.py" > /dev/null; then
    echo "Warning: Some processes may still be running"
    pgrep -af "tibber_relay.py|web_backend.py"
else
    echo "All services stopped successfully"
fi
