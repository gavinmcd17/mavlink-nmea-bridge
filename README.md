# MAVLink to NMEA TCP bridge

This Linux Python 3.12+ service reads ArduPilot MAVLink GPS data from a serial or MAVLink endpoint and streams ASCII NMEA-0183 to a Rajant BreadCrumb. It emits `$GPGGA` and `$GPVTG` once per output interval. The TCP listener is intentionally unauthenticated and unencrypted; expose port 10110 only on a trusted or isolated network.

## Architecture

`/dev/ttyACM0` (or `udpin:...`) -> resilient MAVLink reader -> thread-safe GPS state/freshness policy -> NMEA formatter -> non-blocking multi-client TCP broadcaster.

`GPS_RAW_INT` is the default because it directly provides fix type, satellites, HDOP, GPS speed/course, and sometimes UTC. `GLOBAL_POSITION_INT` provides position, MSL altitude, velocity, and heading but does not directly provide GPS fix quality, satellite count, or HDOP. When selected, the bridge retains the latest valid `GPS_RAW_INT` metadata when available and otherwise emits conservative blank/zero metadata. `time_boot_ms` is never treated as UTC. If GPS epoch time is unavailable, Linux system UTC is used and a warning is logged.

Freshness is valid through 2 seconds, stale through 5 seconds, and invalid after 5 seconds. Invalid output is a no-fix GGA with blank coordinates and empty VTG motion fields.

## Install

```bash
cd /home/gmcdaniel/Projects/mavlink-nmea-bridge
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[test]'
```

The service account needs access to the USB device, normally by membership in `dialout`:

```bash
ls -l /dev/ttyACM*
ls -l /dev/serial/by-id/
groups
sudo usermod -aG dialout "$USER"
sudo lsof /dev/ttyACM0
```

Log out/in after changing group membership. MAVProxy, QGroundControl, and this bridge generally cannot all independently open the same USB serial device. Use one owner and route MAVLink over UDP when sharing is needed.

## Run directly

```bash
python -m mavlink_nmea_bridge \
  --mavlink-endpoint /dev/ttyACM0 --baud 115200 \
  --position-source GPS_RAW_INT --bind-address 0.0.0.0 \
  --tcp-port 10110 --output-rate 1
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
pytest
```

Install `deploy/mavlink-nmea-bridge.service`, copy `config.example.toml` to `/etc/mavlink-nmea-bridge/config.toml`, create the restricted `mavlink-bridge` account, grant only `dialout` device access, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now mavlink-nmea-bridge
journalctl -u mavlink-nmea-bridge -f
```

The unit starts after network readiness, restarts after failure, runs without root, and logs to journald. Resolve serial permission errors, port conflicts, and heartbeat/GPS problems from the logged state transitions. A TCP client must reconnect after a service restart; stale data is never retained indefinitely.
