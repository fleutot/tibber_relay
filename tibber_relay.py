#!/bin/env python3
import asyncio
import iso8601
import json
import os
import requests
import schedule
import sys
import threading
import time
import websockets
from datetime import datetime
from dotenv import load_dotenv
from enum import Enum

# Output to stdout and stderr directly, no buffering
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

# Load environment variables
load_dotenv()

tibber_token = os.getenv("TIBBER_API_TOKEN")
tibber_url = "https://api.tibber.com/v1-beta/gql"
relay_ip_addr = "192.168.1.106"
relay_instance_id = 0
config_file_path = os.path.join(os.path.dirname(__file__), 'heater_config.json')

# Global references for WebSocket access
price_list_global = None
relay_global = None
connected_clients = set()

DEFAULT_CONFIG = {
    'max_price': 0.2,
    'n_cheapest': 8,
    'mode': 'N_CHEAPEST_TODAY',
    'enabled': True
}

def load_config():
    """Load configuration from file."""
    try:
        with open(config_file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    except json.JSONDecodeError as e:
        print(f"!Error parsing config file: {e}", file=sys.stderr)
        return DEFAULT_CONFIG.copy()

def save_config(config):
    """Save configuration to file."""
    with open(config_file_path, 'w') as f:
        json.dump(config, f, indent=2)


def now_at_price_time_resolution_get():
    return datetime.now().replace(minute=0, second=0,
                                  microsecond=0)

class PriceList:
    def __init__(self, n_cheapest_limit=5):
        self.n_cheapest_limit = n_cheapest_limit
        self.data = {}

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
            # Schedule broadcast in the event loop
            if connected_clients:
                asyncio.run_coroutine_threadsafe(broadcast_state(), asyncio_loop)
        except requests.RequestException as e:
            print(f"!Error fetching price data: {e}", file=sys.stderr)
        except KeyError as e:
            print(f"!Error parsing price data: Missing key {e}",
                  file=sys.stderr)

    def price_now_get(self):
        now = now_at_price_time_resolution_get()
        if now not in self.data:
            print(f"!Warning: No price data for {now}",
                  file=sys.stderr)
            raise Exception("No price data available")

        return self.data[now]

    def price_now_is_in_n_cheapest_today(self):
        now_date = datetime.now().date()

        today_prices = [v for k, v in self.data.items()
                        if k.date() == now_date]
        today_prices.sort()
        if len(today_prices) < self.n_cheapest_limit:
            print(f"!Warning: Not enough price data for today")
            return False

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
        self._prev_status = None
        self._overridden_hours_left = 0
        self.manual_override_nb_runs = manual_override_nb_runs

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
            self._overridden_hours_left = self.manual_override_nb_runs
            self._prev_status = status

        if self._overridden_hours_left > 0:
            print(
                f"-> External change detected, skipping relay update. "
                f"{self._overridden_hours_left} loops left"
            )
            self._overridden_hours_left -= 1
            if connected_clients:
                asyncio.run_coroutine_threadsafe(broadcast_state(), asyncio_loop)
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
        if connected_clients:
            asyncio.run_coroutine_threadsafe(broadcast_state(), asyncio_loop)

    def update(self):
        try:
            config = load_config()

            if not config['enabled']:
                print("-> System disabled via config")
                self.turn(False)
                return

            # Update parameters from config
            self._price_list.n_cheapest_limit = config['n_cheapest']

            if config['mode'] == 'PRICE_LIMIT':
                self._mode = RelayMode.PRICE_LIMIT
                price_now = self._price_list.price_now_get()
                enable = price_now < config['max_price']
                print(f"Price at {now_at_price_time_resolution_get}: {price_now}")

            else:
                self._mode = RelayMode.N_CHEAPEST_TODAY
                enable = self._price_list.price_now_is_in_n_cheapest_today()

            self.turn(enable)
            schedule.clear('retry')

        except ValueError as e:
            raise e
        except Exception as e:
            print(f"Could not update relay: {e}, turn off and retry")
            self.turn(False)
            if not schedule.get_jobs('retry'):
                schedule.every(1).minutes.do(self.update).tag('retry')

# Global event loop reference
asyncio_loop = None

# WebSocket server
async def websocket_handler(websocket):
    """Handle WebSocket connections from web interface."""
    connected_clients.add(websocket)
    print(f"WebSocket client connected. Total clients: {len(connected_clients)}")

    try:
        # Send initial state
        await websocket.send(json.dumps(get_current_state()))

        # Listen for messages (config updates)
        async for message in websocket:
            try:
                data = json.loads(message)
                if data.get('type') == 'config_update':
                    config = data.get('config')
                    print(f"Received config update via WebSocket: {config}")
                    save_config(config)

                    # Apply immediately
                    if relay_global:
                        relay_global.update()

                    # Broadcast new state to all clients
                    await broadcast_state()
            except json.JSONDecodeError as e:
                print(f"!Invalid JSON from WebSocket client: {e}", file=sys.stderr)
    except websockets.exceptions.ConnectionClosed:
        print("WebSocket client disconnected")
    finally:
        connected_clients.remove(websocket)

def get_current_state():
    """Get current system state for broadcasting."""
    state = {
        'timestamp': datetime.now().isoformat(),
        'config': load_config()
    }

    if relay_global:
        state['relay_on'] = relay_global.status_get()
        state['overridden'] = relay_global._overridden_hours_left > 0
        state['override_hours_left'] = relay_global._overridden_hours_left

    if price_list_global:
        try:
            state['current_price'] = price_list_global.price_now_get()
        except:
            state['current_price'] = None

        # Get today's prices for chart
        now_date = datetime.now().date()
        today_prices = [
            {'time': k.isoformat(), 'price': v}
            for k, v in sorted(price_list_global.data.items())
            if k.date() == now_date
        ]
        state['today_prices'] = today_prices

    return state

async def broadcast_state():
    """Broadcast current state to all connected WebSocket clients."""
    if not connected_clients:
        return

    state = get_current_state()
    message = json.dumps(state)

    disconnected = set()
    for client in connected_clients:
        try:
            await client.send(message)
        except websockets.exceptions.ConnectionClosed:
            disconnected.add(client)

    # Clean up disconnected clients
    for client in disconnected:
        connected_clients.discard(client)

def run_websocket_server():
    """Run WebSocket server in separate thread."""
    global asyncio_loop

    async def serve():
        async with websockets.serve(websocket_handler, '127.0.0.1', 8765):
            print("WebSocket server started on ws://127.0.0.1:8765")
            await asyncio.Future()  # Run forever

    asyncio_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(asyncio_loop)
    asyncio_loop.run_until_complete(serve())

if __name__ == "__main__":
    # Start WebSocket server in background thread
    ws_thread = threading.Thread(target=run_websocket_server, daemon=True)
    ws_thread.start()

    # Initialize system
    config = load_config()
    price_list_global = PriceList(n_cheapest_limit=config['n_cheapest'])

    relay_mode = (RelayMode.N_CHEAPEST_TODAY if config['mode'] == 'N_CHEAPEST_TODAY'
                  else RelayMode.PRICE_LIMIT)
    relay_global = Relay(relay_ip_addr, relay_instance_id, price_list_global,
                        relay_mode=relay_mode)

    # Schedule tasks
    schedule.every().hour.at(":00").do(relay_global.update)
    schedule.every().day.at("21:42").do(price_list_global.fetch)

    # Initial run
    price_list_global.fetch()
    relay_global.update()

    # Main loop
    while True:
        schedule.run_pending()
        time.sleep(3 * 60)
