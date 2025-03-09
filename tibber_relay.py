#!/bin/env python3
import requests
from datetime import datetime
import iso8601
import schedule
import time
from dotenv import load_dotenv
import os
import sys

# Output to stdout and stderr directly, no buffering
sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
sys.stderr.reconfigure(line_buffering=True)

load_dotenv()

tibber_token = os.getenv("TIBBER_API_TOKEN")
tibber_url = "https://api.tibber.com/v1-beta/gql"
relay_ip_addr = "192.168.1.106"
price_limit_sek = 0.5

price_data = []

def price_list_fetch():
    headers = {
        "Authorization": f"Bearer {tibber_token}",
        "Content-Type": "application/json",
    }

    body = {
        "query": "{ viewer { homes { currentSubscription { priceInfo { today { total startsAt } tomorrow { total startsAt } } } } } }"
    }

    response = requests.post(tibber_url, headers=headers, json=body)

    date_price = response.json()["data"]["viewer"]["homes"][0]["currentSubscription"]["priceInfo"]
    date_price = date_price["today"] + date_price["tomorrow"]

    global price_data
    price_data = {iso8601.parse_date(item['startsAt']).replace(tzinfo=None): item['total']
                  for item in date_price}

    print(price_data)

def relay_turn(enable):
    enable_str = "on" if enable else "off"
    requests.get(f"http://{relay_ip_addr}/relay/0?turn={enable_str}")

def relay_update():
    ### TODO: use outside temperature! Or/and inside temperature

    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    enable = price_data[now] < price_limit_sek
    relay_turn(enable)
    if enable:
        print(f"Turn relay on at {datetime.now()}, price {price_data[now]}")
    else:
        print(f"Turn relay off at {datetime.now()}, price {price_data[now]}")

schedule.every().hour.at(":00").do(relay_update)
# Tomorrow's prices are available from 13:00.
schedule.every().day.at("21:42").do(price_list_fetch)

price_list_fetch()
relay_update()

while True:
    schedule.run_pending()
    time.sleep(3 * 60)
