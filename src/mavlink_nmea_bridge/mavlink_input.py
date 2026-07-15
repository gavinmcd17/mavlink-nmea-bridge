"""Resilient MAVLink reader with serial/UDP endpoint support."""

from __future__ import annotations

import logging
import math
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable

from .state import GPSState, GPSStateStore, system_utc

LOG = logging.getLogger(__name__)
UNKNOWN_U16 = 65535
UNKNOWN_I32 = 2147483647
UNKNOWN_GPS_EPH = (UNKNOWN_U16, 9999)


def _number(value: Any, *, unknown: tuple[int, ...] = ()) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if not math.isfinite(result) or int(result) in unknown else result


def _utc_from_gps(time_usec: Any) -> datetime | None:
    value = _number(time_usec)
    # MAVLink GPS time_usec is Unix epoch microseconds when it is large enough;
    # smaller values may be time since boot and must never be treated as UTC.
    if value is None or value < 1_000_000_000_000:
        return None
    return datetime.fromtimestamp(value / 1_000_000, tz=timezone.utc)


class MAVLinkReader:
    """Read and normalize MAVLink position messages on a background thread."""

    def __init__(self, endpoint: str, baud: int, source: str, state: GPSStateStore,
                 message_rate: float, source_system: int | None = None,
                 source_component: int | None = None, reconnect_max: float = 30.0,
                 on_system_time_fallback: Callable[[], None] | None = None) -> None:
        self.endpoint, self.baud, self.source, self.state = endpoint, baud, source, state
        self.message_rate, self.source_system, self.source_component = message_rate, source_system, source_component
        self.reconnect_max, self.on_system_time_fallback = reconnect_max, on_system_time_fallback
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._metadata = GPSState()
        self._have_heartbeat = False

    def start(self) -> None:
        """Start the background reader thread."""

        self._thread = threading.Thread(target=self.run, name="mavlink-reader", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Request reader shutdown and briefly wait for the thread to exit."""

        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _accept(self, msg: Any) -> bool:
        return ((self.source_system is None or msg.get_srcSystem() == self.source_system) and
                (self.source_component is None or msg.get_srcComponent() == self.source_component))

    def _request_rate(self, connection: Any, name: str) -> None:
        from pymavlink import mavutil

        # pymavlink exposes message IDs as MAVLINK_MSG_ID_<NAME>; they are not
        # attributes named after the message itself on either object.
        message_id = getattr(mavutil.mavlink, f"MAVLINK_MSG_ID_{name}", None)
        if message_id is not None:
            connection.mav.command_long_send(connection.target_system, connection.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0, message_id,
                1_000_000.0 / self.message_rate, 0, 0, 0, 0, 0)
        else:
            LOG.warning("pymavlink has no message ID for %s; cannot request its rate", name)

    def _handle_gps(self, msg: Any) -> None:
        lat = _number(msg.lat, unknown=(UNKNOWN_I32,))
        lon = _number(msg.lon, unknown=(UNKNOWN_I32,))
        fix_type = int(getattr(msg, "fix_type", 0) or 0)
        satellites = _number(getattr(msg, "satellites_visible", None), unknown=(UNKNOWN_U16,))
        eph = _number(getattr(msg, "eph", None), unknown=UNKNOWN_GPS_EPH)
        LOG.info(
            "GPS_RAW_INT received: lat=%s lon=%s fix_type=%s satellites=%s hdop=%s",
            None if lat is None else lat / 1e7,
            None if lon is None else lon / 1e7,
            fix_type,
            None if satellites is None else int(satellites),
            None if eph is None else eph / 100.0,
        )
        if lat is None or lon is None:
            return
        utc = _utc_from_gps(getattr(msg, "time_usec", None))
        if utc is None:
            utc = system_utc()
            if self.on_system_time_fallback:
                self.on_system_time_fallback()
        altitude = _number(msg.alt, unknown=(UNKNOWN_I32,))
        velocity = _number(getattr(msg, "vel", None), unknown=(UNKNOWN_U16,))
        course = _number(getattr(msg, "cog", None), unknown=(UNKNOWN_U16,))
        s = GPSState(latitude=lat / 1e7, longitude=lon / 1e7,
            altitude_m=altitude / 1000.0 if altitude is not None else None,
            fix_type=fix_type,
            satellites=int(satellites) if satellites is not None else None,
            hdop=eph / 100.0 if eph is not None else None,
            speed_mps=velocity / 100.0 if velocity is not None else None,
            course_deg=course / 100.0 if course is not None else None,
            utc=utc, source="GPS_RAW_INT", last_update_monotonic=time.monotonic(),
            system_id=msg.get_srcSystem(), component_id=msg.get_srcComponent())
        if self.source == "GPS_RAW_INT":
            self.state.update(s)
        else:
            # GLOBAL_POSITION_INT supplies the position; retain the freshest
            # GPS_RAW_INT fix metadata without changing the selected source.
            self.state.update_metadata(fix_type=s.fix_type, satellites=s.satellites, hdop=s.hdop)

    def _handle_global(self, msg: Any) -> None:
        lat, lon = _number(msg.lat, unknown=(UNKNOWN_I32,)), _number(msg.lon, unknown=(UNKNOWN_I32,))
        vx, vy = _number(msg.vx, unknown=(UNKNOWN_I32,)), _number(msg.vy, unknown=(UNKNOWN_I32,))
        LOG.info(
            "GLOBAL_POSITION_INT received: lat=%s lon=%s alt_mm=%s vx=%s vy=%s heading_cdeg=%s",
            None if lat is None else lat / 1e7,
            None if lon is None else lon / 1e7,
            getattr(msg, "alt", None),
            getattr(msg, "vx", None),
            getattr(msg, "vy", None),
            getattr(msg, "hdg", None),
        )
        if lat is None or lon is None:
            return
        speed = math.hypot(vx, vy) / 100.0 if vx is not None and vy is not None else None
        heading = _number(getattr(msg, "hdg", None), unknown=(UNKNOWN_U16,))
        metadata = self.state.snapshot()
        altitude = _number(msg.alt, unknown=(UNKNOWN_I32,))
        if self.on_system_time_fallback:
            self.on_system_time_fallback()
        self.state.update(GPSState(latitude=lat / 1e7, longitude=lon / 1e7,
            altitude_m=altitude / 1000.0 if altitude is not None else None,
            fix_type=metadata.fix_type, satellites=metadata.satellites, hdop=metadata.hdop,
            speed_mps=speed, course_deg=heading / 100.0 if heading is not None else None,
            utc=system_utc(), source="GLOBAL_POSITION_INT", last_update_monotonic=time.monotonic(),
            system_id=msg.get_srcSystem(), component_id=msg.get_srcComponent()))

    def run(self) -> None:
        """Run the reconnecting MAVLink receive loop until stopped."""

        from pymavlink import mavutil
        backoff = 1.0
        while not self._stop.is_set():
            connection = None
            try:
                LOG.info("Connecting to MAVLink endpoint %s", self.endpoint)
                connection = mavutil.mavlink_connection(self.endpoint, baud=self.baud, autoreconnect=True)
                LOG.info("Waiting for MAVLink heartbeat")
                heartbeat = connection.wait_heartbeat(timeout=10)
                if heartbeat is None:
                    raise TimeoutError("MAVLink heartbeat timeout")
                if not self._accept(heartbeat):
                    LOG.warning("Heartbeat did not match configured system/component filter")
                LOG.info("Heartbeat acquired from system %s component %s", connection.target_system, connection.target_component)
                self._request_rate(connection, "GPS_RAW_INT")
                self._request_rate(connection, "GLOBAL_POSITION_INT")
                backoff = 1.0
                while not self._stop.is_set():
                    msg = connection.recv_match(blocking=True, timeout=1)
                    if msg is None or not self._accept(msg):
                        continue
                    name = msg.get_type()
                    if name == "GPS_RAW_INT":
                        self._handle_gps(msg)
                    elif name == "GLOBAL_POSITION_INT" and self.source == "GLOBAL_POSITION_INT":
                        self._handle_global(msg)
            except Exception as exc:  # serial disconnects and malformed messages must not kill the service
                if not self._stop.is_set():
                    LOG.warning("MAVLink connection lost: %s; reconnecting in %.1fs", exc, backoff)
                    self._stop.wait(backoff)
                    backoff = min(self.reconnect_max, backoff * 2)
            finally:
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
