"""Application orchestration."""
from __future__ import annotations
import asyncio
import logging
import signal
from .config import Config
from .logging_config import configure_logging
from .mavlink_input import MAVLinkReader
from .nmea import gga, vtg
from .state import Freshness, GPSStateStore
from .tcp_server import NMEAServer

LOG = logging.getLogger(__name__)

async def run(config: Config) -> None:
    configure_logging(config.log_level)
    LOG.info("Starting with configuration: %s", config)
    state = GPSStateStore(config.valid_age, config.stale_age, config.invalid_age)
    fallback_logged = False
    def system_time_warning() -> None:
        nonlocal fallback_logged
        if not fallback_logged:
            LOG.warning("MAVLink GPS UTC unavailable; using Linux system UTC clock")
            fallback_logged = True
    reader = MAVLinkReader(config.mavlink_endpoint, config.baud, config.position_source, state,
        config.message_rate, config.source_system, config.source_component, config.reconnect_max,
        system_time_warning)
    previous = Freshness.NEVER
    previous_fix: int | None = None
    def payload() -> bytes:
        nonlocal previous, previous_fix
        freshness = state.freshness()
        fix = state.snapshot().fix_type
        if fix != previous_fix:
            LOG.info("GPS fix type changed: %s -> %s", previous_fix, fix)
            previous_fix = fix
        if freshness != previous:
            if freshness in (Freshness.STALE, Freshness.INVALID):
                LOG.warning("GPS state is %s (age=%s)", freshness.value, state.age())
            elif freshness == Freshness.VALID and previous != Freshness.NEVER:
                LOG.info("GPS state is valid again")
            previous = freshness
        snapshot = state.snapshot()
        return (gga(snapshot, freshness) + vtg(snapshot, freshness)).encode("ascii")
    server = NMEAServer(config.bind_address, config.tcp_port, 1.0 / config.output_rate, payload)
    reader.start()
    loop = asyncio.get_running_loop()
    stopping = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stopping.set)
        except NotImplementedError:
            pass
    server_task = asyncio.create_task(server.run())
    stop_task = asyncio.create_task(stopping.wait())
    try:
        done, _ = await asyncio.wait((stop_task, server_task), return_when=asyncio.FIRST_COMPLETED)
        if server_task in done:
            server_task.result()
    finally:
        LOG.info("Shutting down")
        server.stop()
        try:
            await server_task
        finally:
            reader.stop()
            LOG.info("Clean shutdown")
