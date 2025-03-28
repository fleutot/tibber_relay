#!/usr/bin/env bash

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

script_name="tibber_relay.py"
log_file="tibber_relay.log"

echo "Starting $script_name..."
nohup $python_bin -u "$script_name" >> "$log_file" 2>&1 &

echo "Script started. Check $log_file for logs."
