"""Thread-safe GPS state and freshness policy."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum


class Freshness(str, Enum):
    """Age classification for the most recently received GPS position."""

    VALID = "valid"
    STALE = "stale"
    INVALID = "invalid"
    NEVER = "never"


@dataclass(frozen=True)
class GPSState:
    """Immutable snapshot of normalized GPS position and fix metadata."""

    latitude: float | None = None
    longitude: float | None = None
    altitude_m: float | None = None
    fix_type: int = 0
    satellites: int | None = None
    hdop: float | None = None
    speed_mps: float | None = None
    course_deg: float | None = None
    utc: datetime | None = None
    source: str = ""
    last_update_monotonic: float | None = None
    system_id: int | None = None
    component_id: int | None = None


class GPSStateStore:
    """Synchronize GPS snapshots shared by reader and output threads."""

    def __init__(self, valid_age: float = 2.0, stale_age: float = 5.0, invalid_age: float = 5.0) -> None:
        self._state = GPSState()
        self._lock = threading.Lock()
        self.valid_age, self.stale_age, self.invalid_age = valid_age, stale_age, invalid_age

    def update(self, state: GPSState) -> None:
        """Replace the current GPS snapshot atomically."""

        with self._lock:
            self._state = state

    def update_metadata(self, **kwargs: object) -> None:
        """Replace selected fields on the current snapshot atomically."""

        with self._lock:
            self._state = replace(self._state, **kwargs)

    def snapshot(self) -> GPSState:
        """Return the current immutable GPS snapshot."""

        with self._lock:
            return self._state

    def freshness(self, now: float | None = None) -> Freshness:
        """Classify the current snapshot by its monotonic-clock age."""

        stamp = self.snapshot().last_update_monotonic
        if stamp is None:
            return Freshness.NEVER
        age = (time.monotonic() if now is None else now) - stamp
        if age <= self.valid_age:
            return Freshness.VALID
        if age <= self.stale_age:
            return Freshness.STALE
        return Freshness.INVALID

    def age(self, now: float | None = None) -> float | None:
        """Return the snapshot age in seconds, or ``None`` before an update."""

        stamp = self.snapshot().last_update_monotonic
        return None if stamp is None else (time.monotonic() if now is None else now) - stamp


def system_utc() -> datetime:
    """Return the current system time as a timezone-aware UTC datetime."""

    return datetime.now(timezone.utc)
