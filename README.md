# MAVLink to NMEA TCP bridge

This service reads ArduPilot MAVLink GPS data and broadcasts NMEA-0183 over TCP
to a Rajant BreadCrumb or another trusted client. It emits `$GPGGA` and
`$GPVTG` once per output interval. The TCP listener is unauthenticated and
unencrypted; bind it only to a trusted or isolated network.

The instructions below target a Raspberry Pi Compute Module 5 running 64-bit
Ubuntu Server 24.04 LTS. The application is ordinary Linux Python software, so
no Raspberry Pi-specific runtime is required. Confirm the image and Python
architecture before starting:

```bash
uname -m                    # expected: aarch64
dpkg --print-architecture   # expected: arm64
python3 --version           # must be 3.12 or newer
```

## How it works

`/dev/serial/by-id/...` (or `udpin:...`) -> MAVLink reader -> thread-safe GPS
state and freshness policy -> NMEA formatter -> non-blocking multi-client TCP
broadcaster.

`GPS_RAW_INT` is the default source because it provides fix type, satellites,
HDOP, GPS speed/course, and sometimes UTC. `GLOBAL_POSITION_INT` provides
position, altitude, velocity, and heading; when it is selected, the latest
`GPS_RAW_INT` fix metadata is retained when available. `time_boot_ms` is never
treated as UTC. If GPS epoch time is unavailable, Linux system UTC is used and
a warning is logged.

By default, data is valid through 2 seconds, stale through 5 seconds, and
invalid after 5 seconds. Invalid output has no fix, blank coordinates, and
empty VTG motion fields.

## Install on Ubuntu Server

Install the system packages needed to build Python dependencies, create a
virtual environment, run tests, and diagnose networking:

```bash
sudo apt update
sudo apt install -y git ca-certificates python3 python3-venv python3-pip \
  build-essential rsync netcat-openbsd iproute2 lsof
```

Clone the repository and install it in an isolated environment:

```bash
git clone <repository-url> ~/mavlink-nmea-bridge
cd ~/mavlink-nmea-bridge
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

Verify the installation before connecting the flight controller:

```bash
python -m pytest
python -m mavlink_nmea_bridge --help
```

Reactivate the environment in a new shell with `. .venv/bin/activate`.

## Connect and configure MAVLink

USB serial devices can change names after reconnects. Prefer the persistent
device path shown under `/dev/serial/by-id/` rather than `/dev/ttyACM0`:

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM* 2>/dev/null
sudo usermod -aG dialout "$USER"
```

Log out and back in after adding the group. Confirm the baud rate with the
flight-controller documentation. MAVProxy, QGroundControl, and this bridge
generally cannot all open the same serial device; use one owner and route
MAVLink over UDP when sharing is needed.

Some Ubuntu images have ModemManager installed. It can probe a flight
controller and interrupt or hold the serial device. Disable it only if this
machine does not need cellular modem management:

```bash
systemctl is-active ModemManager 2>/dev/null || true
sudo lsof /dev/ttyACM0 2>/dev/null || true
sudo systemctl disable --now ModemManager.service
```

If ModemManager is needed for another device, keep it enabled and configure a
udev exclusion for the flight controller instead.

Create a configuration file and change the endpoint, baud rate, and network
settings as required:

```bash
cp config.example.toml config.toml
${EDITOR:-vi} config.toml
```

Command-line options override values from `--config`. The file
`deploy/mavlink-nmea-bridge.env.example` only sets `PYTHONUNBUFFERED`; it is
not the application configuration file.

## Run manually

Use the configuration file:

```bash
python -m mavlink_nmea_bridge --config config.toml
```

Or specify options directly:

```bash
python -m mavlink_nmea_bridge \
  --mavlink-endpoint /dev/serial/by-id/<flight-controller> \
  --baud 115200 --position-source GPS_RAW_INT \
  --bind-address 0.0.0.0 --tcp-port 10110 --output-rate 1
```

For a UDP source routed by MAVProxy:

```bash
mavproxy.py --master=/dev/serial/by-id/<flight-controller> --baudrate=115200 \
  --out=udp:127.0.0.1:14550
python -m mavlink_nmea_bridge \
  --mavlink-endpoint udpin:0.0.0.0:14550 --tcp-port 10110
```

Inspect decoded state without starting the TCP listener:

```bash
python -m mavlink_nmea_bridge.inspect \
  --mavlink-endpoint /dev/serial/by-id/<flight-controller> --baud 115200
```

## Test the TCP output

Configure the BreadCrumb with:

- External GPS IP: the Compute Module’s reachable IP address
- External GPS TCP port: `10110`
- Timeout: start with 10 seconds

Check the listener and read local output:

```bash
ss -ltnp | grep ':10110'
nc -v 127.0.0.1 10110
```

If UFW is active, allow only the BreadCrumb (replace the address and
interface):

```bash
sudo ufw status
sudo ufw allow from <breadcrumb-ip> to any port 10110 proto tcp
```

To test the BreadCrumb without a flight controller, stop the bridge if it is
already using port 10110, then run:

```bash
python -m mavlink_nmea_bridge.synthetic \
  --latitude 40.1234567 --longitude -75.1234567 \
  --altitude 120.5 --tcp-port 10110
```

Example sentences are:

```text
$GPGGA,123519.000,4807.0380,N,01131.0000,E,1,8,0.9,545.4,M,,M,,*7C
$GPVTG,54.7,T,,M,5.50,N,10.18,K*6E
```

## Run as a systemd service

The supplied unit expects the application at `/opt/mavlink-nmea-bridge` and
the configuration at `/etc/mavlink-nmea-bridge/config.toml`. From the
repository root, install a restricted service account and copy the checkout:

```bash
sudo useradd --system --home /opt/mavlink-nmea-bridge \
  --shell /usr/sbin/nologin mavlink-bridge
sudo usermod -aG dialout mavlink-bridge
sudo install -d -o mavlink-bridge -g mavlink-bridge /opt/mavlink-nmea-bridge
sudo rsync -a --exclude='.venv' --exclude='__pycache__' ./ \
  /opt/mavlink-nmea-bridge/
sudo chown -R mavlink-bridge:mavlink-bridge /opt/mavlink-nmea-bridge
sudo -u mavlink-bridge python3 -m venv /opt/mavlink-nmea-bridge/.venv
sudo -u mavlink-bridge /opt/mavlink-nmea-bridge/.venv/bin/python \
  -m pip install --upgrade pip
sudo -u mavlink-bridge /opt/mavlink-nmea-bridge/.venv/bin/python \
  -m pip install /opt/mavlink-nmea-bridge
sudo install -d -o root -g mavlink-bridge -m 0750 \
  /etc/mavlink-nmea-bridge
sudo install -o root -g mavlink-bridge -m 0640 config.example.toml \
  /etc/mavlink-nmea-bridge/config.toml
sudoedit /etc/mavlink-nmea-bridge/config.toml
sudo install -o root -g root -m 0644 deploy/mavlink-nmea-bridge.env.example \
  /etc/default/mavlink-nmea-bridge
sudo install -o root -g root -m 0644 deploy/mavlink-nmea-bridge.service \
  /etc/systemd/system/mavlink-nmea-bridge.service
```

The `useradd` command is for a new installation. If the account already
exists, use this instead:

```bash
sudo usermod --home /opt/mavlink-nmea-bridge \
  --shell /usr/sbin/nologin mavlink-bridge
```

Edit the installed TOML file before starting the service. In particular, use
the persistent `/dev/serial/by-id/...` endpoint when one is available.

Enable it and inspect the first startup:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mavlink-nmea-bridge
sudo systemctl status mavlink-nmea-bridge
sudo journalctl -u mavlink-nmea-bridge -f
```

The unit waits for network readiness, restarts after failures, runs without
root, and logs to journald. Common startup issues are a wrong serial endpoint,
serial ownership by another process, missing `dialout` access, a heartbeat
timeout, or TCP port 10110 already being in use.

When updating an existing deployment, copy the new checkout, reinstall the
package, review the configuration, and restart:

```bash
sudo rsync -a --exclude='.venv' --exclude='__pycache__' ./ \
  /opt/mavlink-nmea-bridge/
sudo chown -R mavlink-bridge:mavlink-bridge /opt/mavlink-nmea-bridge
sudo -u mavlink-bridge /opt/mavlink-nmea-bridge/.venv/bin/python \
  -m pip install /opt/mavlink-nmea-bridge
sudo systemctl restart mavlink-nmea-bridge
```

## Development

Run the test suite from an activated virtual environment:

```bash
python -m pytest
```
