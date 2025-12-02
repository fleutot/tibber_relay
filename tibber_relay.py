#!/bin/env python3
import iso8601
import json
import os
import requests
import schedule
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
from enum import Enum
from flask import Flask, jsonify, request as flask_request
from threading import Thread

# Output to stdout and stderr directly, no buffering
sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
sys.stderr.reconfigure(line_buffering=True)

# Load environment variables
load_dotenv()

tibber_token = os.getenv("TIBBER_API_TOKEN")
tibber_url = "https://api.tibber.com/v1-beta/gql"
relay_ip_addr = "192.168.1.106"
relay_instance_id = 0  # Relay ID from within the Shelly unit
price_limit_sek = 0.2

price_data = {}

# Configuration file
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

# State log file
STATE_LOG_FILE = os.path.join(os.path.dirname(__file__), 'relay_state_log.json')

def load_config():
    """Load configuration from config.json file."""
    global price_limit_sek

    default_config = {
        'mode': 'N_CHEAPEST_TODAY',
        'price_limit_sek': 0.2,
        'n_cheapest_limit': 5
    }

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                print(f"Loaded configuration from {CONFIG_FILE}")
                return config
        except Exception as e:
            print(f"Error loading config file: {e}", file=sys.stderr)
            print("Using default configuration")
            return default_config
    else:
        print(f"No config file found, using defaults")
        return default_config

def save_config(mode, price_limit, n_cheapest):
    """Save configuration to config.json file."""
    config = {
        'mode': mode,
        'price_limit_sek': price_limit,
        'n_cheapest_limit': n_cheapest
    }

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"Error saving config file: {e}", file=sys.stderr)

def log_relay_state(relay_on, mode, override_state, price=None):
    """Append current relay state to log file."""
    now = datetime.now().replace(minute=0, second=0, microsecond=0)

    state_entry = {
        'time': now.isoformat(),
        'relay_on': relay_on,
        'mode': mode.name,
        'override_state': override_state,
        'price': price
    }

    try:
        # Load existing log
        if os.path.exists(STATE_LOG_FILE):
            with open(STATE_LOG_FILE, 'r') as f:
                states = json.load(f)
        else:
            states = []

        # Check if entry for this hour already exists
        existing_index = None
        for i, state in enumerate(states):
            if state['time'] == now.isoformat():
                existing_index = i
                break

        # Update or append
        if existing_index is not None:
            states[existing_index] = state_entry
        else:
            states.append(state_entry)

        # Save
        with open(STATE_LOG_FILE, 'w') as f:
            json.dump(states, f, indent=2)

        print(f"Logged state: relay_on={relay_on}, mode={mode.name}")
    except Exception as e:
        print(f"Error logging state: {e}", file=sys.stderr)

class PriceList:
    def __init__(self, n_cheapest_limit=5):
        self.n_cheapest_limit = n_cheapest_limit
        self.data = {}  # Initialize empty dict, populated by fetch()

    def fetch(self):
        headers = {
            "Authorization": f"Bearer {tibber_token}",
            "Content-Type": "application/json",
        }

        body = {
            "query": "{ viewer { homes { currentSubscription { priceInfo { today { total startsAt } tomorrow { total startsAt } } } } } }"
        }

        try:
            response = requests.post(tibber_url, headers=headers,
                                     json=body, timeout=15)
            response.raise_for_status()
            data = response.json().get("data", {}).get("viewer", {}).get("homes", [{}])[0]
            price_info = data.get("currentSubscription", {}).get("priceInfo", {})

            today_prices = price_info.get("today", [])
            tomorrow_prices = price_info.get("tomorrow", [])
            date_price = today_prices + tomorrow_prices

            self.data = {
                iso8601.parse_date(item['startsAt']).replace(tzinfo=None): item['total']
                for item in date_price
            }
            print(self.data)
        except requests.RequestException as e:
            print(f"!Error fetching price data: {e}", file=sys.stderr)
        except KeyError as e:
            print(f"!Error parsing price data: Missing key {e}",
                  file=sys.stderr)

    def price_now_get(self):
        now = datetime.now().replace(minute=0, second=0,
                                     microsecond=0)
        if now not in self.data:
            print(f"!Warning: No price data for {now}",
                  file=sys.stderr)
            raise Exception("No price data available")

        print(f"Price at {now}: {self.data[now]}")
        return self.data[now]

    def price_now_is_in_n_cheapest_today(self):
        now_date = datetime.now().date()

        today_prices = [v for k, v in self.data.items()
                        if k.date() == now_date]
        today_prices.sort()
        price_limit = today_prices[self.n_cheapest_limit]
        now_price = self.price_now_get()
        print(f"price {now_price} within {self.n_cheapest_limit} cheapest: {now_price <= price_limit}")
        return now_price <= price_limit

class RelayMode(Enum):
    PRICE_LIMIT = 1
    N_CHEAPEST_TODAY = 2

class Relay:
    """See Shelly webhook documentation:
    https://shelly.guide/webhooks-https-requests/
    """

    def __init__(self, ip, instance_id, price_list,
                 manual_override_nb_runs=5,
                 relay_mode=RelayMode.PRICE_LIMIT):
        self._ip = ip
        self._id = instance_id
        self._price_list = price_list
        self._mode = relay_mode
        self._prev_status = None  # Status set by this script
        self._overridden_hours_left = 0
        self._override_state = None  # None (auto), True (forced on), False (forced off)
        self.manual_override_nb_runs = manual_override_nb_runs  # Override delay
        self._errors = {}

    def status_get(self):
        try:
            response = requests.get(
                f"http://{self._ip}/rpc/Shelly.GetStatus?id={self._id}",
                timeout=5
            )
            response.raise_for_status()
            return response.json().get(f"switch:{self._id}").get("output") is True
        except requests.RequestException as e:
            print(f"!Error fetching relay status: {e}",
                  file=sys.stderr)
            return None

    def turn(self, enable):
        status = self.status_get()
        if (
                status != self._prev_status
                and self._prev_status is not None
                and status is not None
        ):
            # Something else changed the status externally.
            self._overridden_hours_left = self.manual_override_nb_runs
            self._prev_status = status

        if self._overridden_hours_left > 0:
            print(
                f"-> External change detected, skipping relay update. "
                f"{self._overridden_hours_left} loops left"
            )
            self._overridden_hours_left -= 1
            return

        enable_str = "on" if enable else "off"
        try:
            requests.get(
                f"http://{self._ip}/relay/{self._id}?turn={enable_str}",
                timeout=5
            )
        except requests.RequestException as e:
            print(f"!Error actuating relay: {e}", file=sys.stderr)
            return

        print(f"-> Relay {enable_str}")
        self._prev_status = self.status_get()

    def update(self, retry=True):
        try:
            if self._mode == RelayMode.PRICE_LIMIT:
                enable = (
                    self._price_list.price_now_get() < price_limit_sek
                )
            elif self._mode == RelayMode.N_CHEAPEST_TODAY:
                enable = self._price_list.price_now_is_in_n_cheapest_today()
            else:
                raise ValueError(f"Unidentified mode")

            self.turn(enable)
            self._errors.pop('price_fetch', None)

            # Log the state after update
            current_status = self.status_get()
            if current_status is not None:
                try:
                    current_price = self._price_list.price_now_get()
                except:
                    current_price = None
                log_relay_state(current_status, self._mode, self._override_state, current_price)
        except Exception as e:
            if retry:
                print("Price data missing, fetching fresh prices...")
                self._price_list.fetch()
                self.update(retry=False)
            else:
                error_msg = f"No price data available: {str(e)}"
                print(error_msg)
                self._errors['price_fetch'] = {
                    'message': error_msg,
                    'timestamp': datetime.now().isoformat()
                }
                self.turn(False)


# Load saved configuration
saved_config = load_config()
price_limit_sek = saved_config['price_limit_sek']

# Initialize objects at module level so they can be imported
price_list = PriceList(n_cheapest_limit=saved_config['n_cheapest_limit'])

# Convert mode string to enum
relay_mode = RelayMode.PRICE_LIMIT if saved_config['mode'] == 'PRICE_LIMIT' else RelayMode.N_CHEAPEST_TODAY
relay = Relay(relay_ip_addr, relay_instance_id, price_list, relay_mode=relay_mode)

# Flask API for inter-service communication (localhost only)
api = Flask(__name__)

@api.route('/api/status')
def api_get_status():
    """Get current relay status and price."""
    try:
        current_price = price_list.price_now_get()
    except Exception:
        current_price = None

    relay_on = relay.status_get()

    return jsonify({
        'relay_on': relay_on,
        'current_price': current_price,
        'mode': relay._mode.name,
        'override_hours_left': relay._overridden_hours_left,
        'override_state': relay._override_state,
        'errors': relay._errors,
        'timestamp': datetime.now().isoformat()
    })

@api.route('/api/prices')
def api_get_prices():
    """Get all available price data."""
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

@api.route('/api/config')
def api_get_config():
    """Get current configuration."""
    return jsonify({
        'mode': relay._mode.name,
        'n_cheapest_limit': price_list.n_cheapest_limit,
        'price_limit_sek': price_limit_sek,
        'manual_override_runs': relay.manual_override_nb_runs,
        'relay_ip': relay._ip
    })

@api.route('/api/config', methods=['POST'])
def api_update_config():
    """Update configuration (mode, price limit, n_cheapest)."""
    global price_limit_sek

    try:
        data = flask_request.get_json()

        # Update mode
        if 'mode' in data:
            mode_str = data['mode']
            if mode_str == 'PRICE_LIMIT':
                relay._mode = RelayMode.PRICE_LIMIT
            elif mode_str == 'N_CHEAPEST_TODAY':
                relay._mode = RelayMode.N_CHEAPEST_TODAY
            else:
                return jsonify({'success': False, 'error': f'Invalid mode: {mode_str}'}), 400
            print(f"Mode updated to: {relay._mode.name}")

        # Update price limit (for PRICE_LIMIT mode)
        if 'price_limit_sek' in data:
            price_limit_sek = float(data['price_limit_sek'])
            print(f"Price limit updated to: {price_limit_sek} SEK")

        # Update n_cheapest_limit (for N_CHEAPEST_TODAY mode)
        if 'n_cheapest_limit' in data:
            price_list.n_cheapest_limit = int(data['n_cheapest_limit'])
            print(f"N cheapest limit updated to: {price_list.n_cheapest_limit}")

        # Save configuration to file
        save_config(relay._mode.name, price_limit_sek, price_list.n_cheapest_limit)

        return jsonify({
            'success': True,
            'message': 'Configuration updated',
            'config': {
                'mode': relay._mode.name,
                'price_limit_sek': price_limit_sek,
                'n_cheapest_limit': price_list.n_cheapest_limit
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/api/command', methods=['POST'])
def api_command():
    """Execute relay command (turn on/off) with optional override duration."""
    try:
        data = flask_request.get_json()
        command = data.get('command')
        override_hours = data.get('override_hours')

        if command == 'turn_on':
            relay.turn(True)
            if override_hours is not None:
                relay._overridden_hours_left = int(override_hours)
                relay._override_state = True
                print(f"Relay turned on with {override_hours} hour override")
            return jsonify({'success': True, 'message': 'Relay turned on'})
        elif command == 'turn_off':
            relay.turn(False)
            if override_hours is not None:
                relay._overridden_hours_left = int(override_hours)
                relay._override_state = False
                print(f"Relay turned off with {override_hours} hour override")
            return jsonify({'success': True, 'message': 'Relay turned off'})
        else:
            return jsonify({'success': False, 'error': 'Unknown command'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api.route('/api/resume', methods=['POST'])
def api_resume():
    """Resume automatic control by clearing override."""
    try:
        relay._overridden_hours_left = 0
        relay._override_state = None
        relay._prev_status = None  # Reset to prevent external change detection
        relay.update()  # Immediately apply automatic control
        print("Override cleared - automatic control resumed")
        return jsonify({'success': True, 'message': 'Automatic control resumed'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def run_api_server():
    """Run Flask API server in background thread (localhost only)."""
    api.run(host='127.0.0.1', port=8001, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("Starting Tibber Relay Service...")

    # Start API server in background thread (localhost:8001)
    api_thread = Thread(target=run_api_server, daemon=True)
    api_thread.start()
    print("API server started on http://127.0.0.1:8001")

    # Schedule tasks
    schedule.every().hour.at(":00").do(relay.update)
    schedule.every().day.at("14:30").do(price_list.fetch)  # Fetch tomorrow's prices (published ~14:15)
    schedule.every().day.at("15:30").do(price_list.fetch)  # Retry if unavailable
    schedule.every().day.at("16:30").do(price_list.fetch)  # Second retry
    schedule.every().day.at("17:30").do(price_list.fetch)  # Third retry

    # Initial fetch and update
    price_list.fetch()
    relay.update()

    print("Scheduler running - relay updates hourly, prices fetched at 14:30 (with retries)")

    # Main scheduler loop
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
