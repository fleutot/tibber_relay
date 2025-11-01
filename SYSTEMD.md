# Systemd Setup

This guide explains how to run Tibber Relay services as systemd services for automatic startup.

## Benefits of systemd

- Services start automatically on boot
- Automatic restart on failure
- Logs managed by systemd/journalctl
- Web backend runs on port 8080 (standard alternative HTTP port)

## Installation

1. **Copy service files to systemd directory:**
   ```bash
   sudo cp tibber_relay.service /etc/systemd/system/
   sudo cp tibber_relay_web.service /etc/systemd/system/
   ```

3. **Reload systemd to recognize new services:**
   ```bash
   sudo systemctl daemon-reload
   ```

4. **Enable services to start on boot:**
   ```bash
   sudo systemctl enable tibber_relay.service
   sudo systemctl enable tibber_relay_web.service
   ```

5. **Start services now:**
   ```bash
   sudo systemctl start tibber_relay.service
   sudo systemctl start tibber_relay_web.service
   ```

## Management Commands

### Check status
```bash
sudo systemctl status tibber_relay.service
sudo systemctl status tibber_relay_web.service
```

### View logs
```bash
# View recent logs
sudo journalctl -u tibber_relay.service -n 50
sudo journalctl -u tibber_relay_web.service -n 50

# Follow logs in real-time
sudo journalctl -u tibber_relay.service -f
sudo journalctl -u tibber_relay_web.service -f
```

### Stop/Start/Restart
```bash
sudo systemctl stop tibber_relay.service
sudo systemctl start tibber_relay.service
sudo systemctl restart tibber_relay.service

sudo systemctl stop tibber_relay_web.service
sudo systemctl start tibber_relay_web.service
sudo systemctl restart tibber_relay_web.service
```

### Disable (prevent auto-start on boot)
```bash
sudo systemctl disable tibber_relay.service
sudo systemctl disable tibber_relay_web.service
```

## Port Configuration

- **Manual runs** (via `start_all.sh`): Web backend uses port 8000
- **Systemd runs**: Web backend uses port 8080 (set via `Environment="PORT=8080"` in service file)

The web backend reads the port from the `PORT` environment variable, defaulting to 8000 if not set.

Port 8080 is used instead of 80 to avoid:
- Requiring root privileges
- Browser forcing HTTPS on standard port 80

## Manual Testing vs Production

You can still use `start_all.sh` and `stop.sh` for manual testing on port 8000. Systemd services are independent and won't interfere.

## Troubleshooting

If services fail to start:

1. **Check logs for errors:**
   ```bash
   sudo journalctl -u tibber_relay.service -n 100 --no-pager
   ```

2. **Verify Python environment exists:**
   ```bash
   ls -la /home/gauthier/sjobacken/tibber_relay/venv/bin/python3
   ```

3. **Check permissions:**
   ```bash
   # Both services run as user 'gauthier'
   # No root privileges required
   ```

4. **Test manually first:**
   ```bash
   ./start_all.sh
   # Check if services work
   ./stop.sh
   ```
