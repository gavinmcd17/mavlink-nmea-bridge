# MAVLink to NMEA TCP bridge

This Linux Python 3.12+ service reads ArduPilot MAVLink GPS data from a serial or MAVLink endpoint and streams ASCII NMEA-0183 to a Rajant BreadCrumb. It emits `$GPGGA` and `$GPVTG` once per output interval. The TCP listener is intentionally unauthenticated and unencrypted; expose port 10110 only on a trusted or isolated network.

## Architecture

`/dev/ttyACM0` (or `udpin:...`) -> resilient MAVLink reader -> thread-safe GPS state/freshness policy -> NMEA formatter -> non-blocking multi-client TCP broadcaster.

`GPS_RAW_INT` is the default because it directly provides fix type, satellites, HDOP, GPS speed/course, and sometimes UTC. `GLOBAL_POSITION_INT` provides position, MSL altitude, velocity, and heading but does not directly provide GPS fix quality, satellite count, or HDOP. When selected, the bridge retains the latest valid `GPS_RAW_INT` metadata when available and otherwise emits conservative blank/zero metadata. `time_boot_ms` is never treated as UTC. If GPS epoch time is unavailable, Linux system UTC is used and a warning is logged.

Freshness is valid through 2 seconds, stale through 5 seconds, and invalid after 5 seconds. Invalid output is a no-fix GGA with blank coordinates and empty VTG motion fields.

## Fresh-machine setup

The commands below prefer Fedora and assume a user with `sudo` access. The
application requires Python 3.12 or newer. On an older Fedora release, install
the newest available Python that satisfies that requirement and use its
interpreter in place of `python3` below.

Install the OS prerequisites, including the virtual-environment module and tools
used by the diagnostics below:

```bash
sudo dnf install -y git ca-certificates python3 python3-devel \
  gcc gcc-c++ make rsync nmap-ncat iproute lsof
python3 --version
```

If your distribution is not Fedora, use its equivalent package manager and
packages. Confirm that the installed Python version is at least 3.12 before
continuing.

Obtain the source on the new machine. Replace the URL with the repository's
actual clone URL:

```bash
git clone <repository-url> ~/mavlink-nmea-bridge
cd ~/mavlink-nmea-bridge
```

Create an isolated environment and install the application. The `test` extra is
optional, but is useful for verifying a fresh installation:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

Verify the installation before connecting hardware:

```bash
python -m pytest
python -m mavlink_nmea_bridge --help
```

Keep the virtual environment activated for the direct-run, inspection, and test
commands below. If it is closed, reactivate it with `. .venv/bin/activate`.

If MAVLink must be routed through MAVProxy, install it separately in this same
environment:

```bash
python -m pip install MAVProxy
```

## Connect and configure the MAVLink source

The service account needs access to the USB device, normally by membership in `dialout`:

```bash
ls -l /dev/ttyACM*
ls -l /dev/serial/by-id/
groups
sudo usermod -aG dialout "$USER"
sudo lsof /dev/ttyACM0
```

Log out/in after changing group membership, or start a new login session, before
expecting the bridge to open the device. Confirm the selected device and baud
rate with the flight controller documentation. MAVProxy, QGroundControl, and
this bridge generally cannot all independently open the same USB serial device.
Use one owner and route MAVLink over UDP when sharing is needed.

For a repeatable configuration, copy and edit the supplied TOML file:

```bash
cp config.example.toml config.toml
${EDITOR:-vi} config.toml
```

The command-line options override values from `--config`; the checked-in
`deploy/mavlink-nmea-bridge.env.example` only sets `PYTHONUNBUFFERED` and is not
used for application configuration.

## Run directly

```bash
python -m mavlink_nmea_bridge \
  --mavlink-endpoint /dev/ttyACM0 --baud 115200 \
  --position-source GPS_RAW_INT --bind-address 0.0.0.0 \
  --tcp-port 10110 --output-rate 1
```

Alternatively, run the values from the TOML file:

```bash
python -m mavlink_nmea_bridge --config config.toml
```

Future UDP input, for example after MAVProxy routing:

```bash
mavproxy.py --master=/dev/ttyACM0 --baudrate=115200 \
  --out=udp:127.0.0.1:14550 --out=udp:127.0.0.1:14551
python -m mavlink_nmea_bridge --mavlink-endpoint udpin:0.0.0.0:14550 --tcp-port 10110
```

Inspect decoded state without TCP using `python -m mavlink_nmea_bridge.inspect --mavlink-endpoint /dev/ttyACM0 --baud 115200`.

## BreadCrumb and TCP test

Configure the BreadCrumb as follows:

* External GPS IP: the Linux computer's reachable IP
* External GPS TCP port: `10110`
* Timeout: initially `10` seconds

If Fedora's firewall is enabled, allow the port only on the trusted zone or
interface used by the BreadCrumb:

```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --permanent --zone=trusted --add-port=10110/tcp
sudo firewall-cmd --reload
```

Use the appropriate active zone instead of `trusted` when your network policy
requires a more restrictive zone.

Test locally with `nc 127.0.0.1 10110`. Example output:

```text
$GPGGA,123519.000,4807.0380,N,01131.0000,E,1,8,0.9,545.4,M,,M,,*7C\r\n
$GPVTG,54.7,T,,M,5.50,N,10.18,K*6E\r\n
```

Use synthetic mode to test the BreadCrumb without a flight controller:

```bash
python -m mavlink_nmea_bridge.synthetic --latitude 40.1234567 --longitude -75.1234567 --altitude 120.5 --tcp-port 10110
```

Useful checks:

```bash
ss -ltnp | grep 10110
```

Compare coordinates and fix data against MAVProxy's `GPS_RAW_INT`/`GLOBAL_POSITION_INT` output, remembering MAVLink integer scaling documented in the source.

## Tests and systemd

```bash
python -m pytest
```

For an unattended installation, deploy the checkout at the path expected by the
unit file. Run these commands from the repository root. They create a restricted
service account, install the virtual environment and package, install the
configuration, and grant the account access to serial devices:

```bash
sudo useradd --system --home /opt/mavlink-nmea-bridge \
  --shell /usr/sbin/nologin mavlink-bridge
sudo usermod -aG dialout mavlink-bridge
sudo install -d -o mavlink-bridge -g mavlink-bridge /opt/mavlink-nmea-bridge
sudo rsync -a --exclude='.venv' --exclude='__pycache__' ./ /opt/mavlink-nmea-bridge/
sudo chown -R mavlink-bridge:mavlink-bridge /opt/mavlink-nmea-bridge
sudo -u mavlink-bridge python3 -m venv /opt/mavlink-nmea-bridge/.venv
sudo -u mavlink-bridge /opt/mavlink-nmea-bridge/.venv/bin/python -m pip install --upgrade pip
sudo -u mavlink-bridge /opt/mavlink-nmea-bridge/.venv/bin/python -m pip install /opt/mavlink-nmea-bridge
sudo install -d -o root -g mavlink-bridge -m 0750 /etc/mavlink-nmea-bridge
sudo install -o root -g mavlink-bridge -m 0640 config.example.toml \
  /etc/mavlink-nmea-bridge/config.toml
sudoedit /etc/mavlink-nmea-bridge/config.toml
sudo install -o root -g root -m 0644 deploy/mavlink-nmea-bridge.env.example \
  /etc/default/mavlink-nmea-bridge
sudo install -o root -g root -m 0644 deploy/mavlink-nmea-bridge.service \
  /etc/systemd/system/mavlink-nmea-bridge.service
```

If `mavlink-bridge` already exists, replace the `useradd` command with
`sudo usermod --home /opt/mavlink-nmea-bridge --shell /usr/sbin/nologin mavlink-bridge`.
If the repository has already been copied to `/opt/mavlink-nmea-bridge`, omit the
`rsync` command. Review the installed TOML values, especially the MAVLink endpoint,
before starting the service.

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mavlink-nmea-bridge
sudo systemctl status mavlink-nmea-bridge
sudo journalctl -u mavlink-nmea-bridge -f
```

The unit starts after network readiness, restarts after failure, runs without root, and logs to journald. Resolve serial permission errors, port conflicts, and heartbeat/GPS problems from the logged state transitions. A TCP client must reconnect after a service restart; stale data is never retained indefinitely.

When updating an existing deployment, repeat the copy, ownership, package, and
configuration steps as appropriate, then restart it:

```bash
sudo systemctl restart mavlink-nmea-bridge
```
