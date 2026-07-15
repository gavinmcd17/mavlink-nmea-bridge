"""Print decoded position state without starting TCP output."""

from __future__ import annotations

import argparse
import time

from .mavlink_input import MAVLinkReader
from .state import GPSStateStore


def main() -> int:
    """Read MAVLink messages and print the latest normalized GPS state."""

    p = argparse.ArgumentParser()
    p.add_argument("--mavlink-endpoint", default="/dev/ttyACM0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--position-source", choices=("GPS_RAW_INT", "GLOBAL_POSITION_INT"), default="GPS_RAW_INT")
    args = p.parse_args()
    state = GPSStateStore()
    reader = MAVLinkReader(args.mavlink_endpoint, args.baud, args.position_source, state, 5)
    reader.start()
    try:
        while True:
            print(state.snapshot(), "freshness=", state.freshness().value, flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        reader.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
