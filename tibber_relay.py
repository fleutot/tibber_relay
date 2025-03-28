#!/bin/env python3
import os
import sys
import time
import requests
import schedule
import iso8601
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

tibber_token = os.getenv("TIBBER_API_TOKEN")
tibber_url = "https://api.tibber.com/v1-beta/gql"
relay_ip_addr = "192.168.1.106"
relay_instance_id = 0  # Relay ID from within the Shelly unit
price_limit_sek = 0.2

price_data = {}

def price_list_fetch():
    headers = {
        "Authorization": f"Bearer {tibber_token}",
        "Content-Type": "application/json",
    }

    body = {
        "query": "{ viewer { homes { currentSubscription { priceInfo { today { total startsAt } tomorrow { total startsAt } } } } } }"
    }

    try:
        response = requests.post(tibber_url, headers=headers, json=body, timeout=15)
        response.raise_for_status()
        data = response.json().get("data", {}).get("viewer", {}).get("homes", [{}])[0]
        price_info = data.get("currentSubscription", {}).get("priceInfo", {})

        today_prices = price_info.get("today", [])
        tomorrow_prices = price_info.get("tomorrow", [])
        date_price = today_prices + tomorrow_prices

        global price_data
        price_data = {
            iso8601.parse_date(item['startsAt']).replace(tzinfo=None): item['total']
            for item in date_price
        }
        print(price_data)
    except requests.RequestException as e:
        print(f"!Error fetching price data: {e}", file=sys.stderr)
    except KeyError as e:
        print(f"!Error parsing price data: Missing key {e}", file=sys.stderr)


class Relay:
    """See Shelly webhook documentation:
    https://shelly.guide/webhooks-https-requests/
    """

    def __init__(self, ip, instance_id, manual_override_nb_runs=5):
        self._ip = ip
        self._id = instance_id
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
        # TODO: Use outside temperature! Or/and inside temperature
        now = datetime.now().replace(minute=0, second=0, microsecond=0)

        if now not in price_data:
            print(f"!Warning: No price data for {now}", file=sys.stderr)
            enable = False
        else:
            print(f"Price at {now}: {price_data[now]} (limit: {price_limit_sek})")
            enable = price_data[now] < price_limit_sek

        self.turn(enable)


if __name__ == "__main__":
    relay = Relay(relay_ip_addr, relay_instance_id)

    schedule.every().hour.at(":00").do(relay.update)
    schedule.every().day.at("21:42").do(price_list_fetch)  # Fetch tomorrow's prices

    price_list_fetch()
    relay.update()

    while True:
        schedule.run_pending()
        time.sleep(3 * 60)  # Run every 3 minutes
