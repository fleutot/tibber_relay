This script is intended to run on a separate computer, not in the
relay. Tested on a raspberry pi 3A+, as well as on a standard laptop
on Linux. Tested relay unit is a Shelly Pro 1.

Application: turn on the electric heating of my accumulator tank when
electricity is cheap.

Future work: only do so when the expected outdoor temperature in the
coming couple of days is expected to be low enough.

# Secrets
Store your Tibber API token in the file `.env` at the root of this
repo. Ignored by .gitignore.

Expected content format of `.env`:
```
TIBBER_API_TOKEN=abcd1234
```

# Start
To install the virtual environment, start in the background without
terminating at e.g. ssh logout, call `start.sh`.

# Tibber API
GraphQL data format: https://developer.tibber.com/docs/reference
