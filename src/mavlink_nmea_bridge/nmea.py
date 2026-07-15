"""NMEA-0183 sentence formatting."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite

from .state import Freshness, GPSState


def checksum(body: str) -> str:
    """Return the two-character hexadecimal NMEA checksum for a sentence body."""

    value = 0
    for char in body:
        value ^= ord(char)
    return f"{value:02X}"


def sentence(body: str) -> str:
    """Wrap an NMEA body with delimiters, checksum, and CRLF termination."""

    return f"${body}*{checksum(body)}\r\n"


def _coord(value: float | None, latitude: bool) -> tuple[str, str]:
    if value is None or not isfinite(value) or (latitude and abs(value) > 90) or (not latitude and abs(value) > 180):
        return "", ""
    hemi = ("N" if value >= 0 else "S") if latitude else ("E" if value >= 0 else "W")
    absolute = abs(value)
    degrees = int(absolute)
    minutes = (absolute - degrees) * 60
    width = 2 if latitude else 3
    return f"{degrees:0{width}d}{minutes:07.4f}", hemi


def fix_quality(fix_type: int) -> int:
    """Map a MAVLink GPS fix type to an NMEA GGA quality indicator."""

    return {4: 2, 5: 5, 6: 4}.get(fix_type, 1 if fix_type in (2, 3) else 0)


def _time(utc: datetime | None) -> str:
    if utc is None:
        return ""
    return utc.astimezone(timezone.utc).strftime("%H%M%S.%f")[:10]


def gga(state: GPSState, freshness: Freshness) -> str:
    """Format position, fix, and altitude state as a GGA sentence."""

    quality = fix_quality(state.fix_type) if freshness in (Freshness.VALID, Freshness.STALE) else 0
    lat, ns = _coord(state.latitude if quality else None, True)
    lon, ew = _coord(state.longitude if quality else None, False)
    sats = str(max(0, state.satellites or 0)) if state.satellites is not None else ""
    hdop = f"{state.hdop:.1f}" if state.hdop is not None and isfinite(state.hdop) else ""
    alt = f"{state.altitude_m:.1f}" if quality and state.altitude_m is not None else ""
    body = f"GPGGA,{_time(state.utc)},{lat},{ns},{lon},{ew},{quality},{sats},{hdop},{alt},M,,M,,"
    return sentence(body)


def vtg(state: GPSState, freshness: Freshness) -> str:
    """Format course and ground speed state as a VTG sentence."""

    course = f"{state.course_deg:.1f}" if freshness in (Freshness.VALID, Freshness.STALE) and state.course_deg is not None else ""
    knots = f"{state.speed_mps * 1.943844492:.2f}" if freshness in (Freshness.VALID, Freshness.STALE) and state.speed_mps is not None else ""
    kph = f"{state.speed_mps * 3.6:.2f}" if knots else ""
    return sentence(f"GPVTG,{course},T,,M,{knots},N,{kph},K")
