#!/bin/env python3
import iso8601
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
            raise Exception("Now price data available")

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
        self.manual_override_nb_runs = manual_override_nb_runs  # Override delay

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

    def update(self):
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
        except e:
            print("Could not fetch price for now, turn off")
            self.turn(False)


# Initialize objects at module level so they can be imported
price_list = PriceList(n_cheapest_limit=5)
relay = Relay(relay_ip_addr, relay_instance_id, price_list,
              relay_mode=RelayMode.N_CHEAPEST_TODAY)

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
        'manual_override_runs': relay.manual_override_nb_runs,
        'relay_ip': relay._ip
    })

@api.route('/api/command', methods=['POST'])
def api_command():
    """Execute relay command (turn on/off)."""
    try:
        data = flask_request.get_json()
        command = data.get('command')

        if command == 'turn_on':
            relay.turn(True)
            return jsonify({'success': True, 'message': 'Relay turned on'})
        elif command == 'turn_off':
            relay.turn(False)
            return jsonify({'success': True, 'message': 'Relay turned off'})
        else:
            return jsonify({'success': False, 'error': 'Unknown command'}), 400
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
    schedule.every().day.at("21:42").do(price_list.fetch)  # Fetch tomorrow's prices

    # Initial fetch and update
    price_list.fetch()
    relay.update()

    print("Scheduler running - relay updates hourly, prices fetched daily at 21:42")

    # Main scheduler loop
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute
