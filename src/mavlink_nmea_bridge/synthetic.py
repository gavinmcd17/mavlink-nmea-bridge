"""Synthetic NMEA TCP server for BreadCrumb integration testing."""

from __future__ import annotations

import argparse
import asyncio
import time

from .nmea import gga, vtg
from .state import Freshness, GPSState
from .tcp_server import NMEAServer


async def run(args: argparse.Namespace) -> None:
    """Run a TCP server that broadcasts a fixed synthetic GPS position."""

    state = GPSState(latitude=args.latitude, longitude=args.longitude, altitude_m=args.altitude,
        fix_type=args.fix_type, satellites=args.satellites, hdop=args.hdop, speed_mps=args.speed,
        course_deg=args.course, utc=None, source="synthetic", last_update_monotonic=time.monotonic())
    server = NMEAServer(args.bind_address, args.tcp_port, 1.0 / args.output_rate,
        lambda: (gga(state, Freshness.VALID) + vtg(state, Freshness.VALID)).encode("ascii"))
    await server.run()


def main() -> int:
    """Parse command-line arguments and run the synthetic TCP server."""

    p = argparse.ArgumentParser()
    p.add_argument("--latitude", type=float, required=True)
    p.add_argument("--longitude", type=float, required=True)
    p.add_argument("--altitude", type=float, default=0.0)
    p.add_argument("--fix-type", type=int, default=3)
    p.add_argument("--satellites", type=int, default=10)
    p.add_argument("--hdop", type=float, default=1.0)
    p.add_argument("--speed", type=float, default=0.0)
    p.add_argument("--course", type=float)
    p.add_argument("--bind-address", default="0.0.0.0")
    p.add_argument("--tcp-port", type=int, default=10110)
    p.add_argument("--output-rate", type=float, default=1.0)
    args = p.parse_args()
    if not -90 <= args.latitude <= 90 or not -180 <= args.longitude <= 180 or not 1 <= args.tcp_port <= 65535:
        p.error("coordinates or TCP port out of range")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
