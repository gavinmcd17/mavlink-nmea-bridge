"""Configuration loading, command-line parsing, and validation."""

from __future__ import annotations

import argparse
import os
import tomllib
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    """Runtime settings for MAVLink input and NMEA TCP output."""

    mavlink_endpoint: str = "/dev/ttyACM0"
    baud: int = 115200
    position_source: str = "GPS_RAW_INT"
    bind_address: str = "0.0.0.0"
    tcp_port: int = 10110
    output_rate: float = 1.0
    message_rate: float = 5.0
    source_system: int | None = None
    source_component: int | None = None
    valid_age: float = 2.0
    stale_age: float = 5.0
    invalid_age: float = 5.0
    reconnect_max: float = 30.0
    log_level: str = "INFO"

    def validate(self) -> None:
        """Raise ``ValueError`` when any setting is outside its valid range."""

        if not self.mavlink_endpoint:
            raise ValueError("mavlink endpoint must not be empty")
        if self.baud <= 0:
            raise ValueError("baud must be positive")
        if self.position_source not in {"GPS_RAW_INT", "GLOBAL_POSITION_INT"}:
            raise ValueError("position-source must be GPS_RAW_INT or GLOBAL_POSITION_INT")
        if not 1 <= self.tcp_port <= 65535:
            raise ValueError("tcp-port must be between 1 and 65535")
        if self.output_rate <= 0 or self.message_rate <= 0:
            raise ValueError("output-rate and message-rate must be positive")
        if self.valid_age < 0 or self.invalid_age <= self.valid_age:
            raise ValueError("invalid-age must be greater than valid-age")
        if self.stale_age < self.valid_age or self.stale_age > self.invalid_age:
            raise ValueError("stale-age must be between valid-age and invalid-age")
        if self.source_system is not None and not 1 <= self.source_system <= 255:
            raise ValueError("source-system must be between 1 and 255")
        if self.source_component is not None and not 0 <= self.source_component <= 255:
            raise ValueError("source-component must be between 0 and 255")
        if self.reconnect_max <= 0:
            raise ValueError("reconnect-max must be positive")


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", type=Path)
    for name, typ in [("mavlink-endpoint", str), ("baud", int), ("position-source", str),
                      ("bind-address", str), ("tcp-port", int), ("output-rate", float),
                      ("message-rate", float), ("source-system", int), ("source-component", int),
                      ("valid-age", float), ("stale-age", float), ("invalid-age", float),
                      ("reconnect-max", float), ("log-level", str)]:
        p.add_argument(f"--{name}", dest=name.replace("-", "_"), type=typ)
    return p


def load_config(argv: list[str] | None = None) -> Config:
    """Load, merge, and validate configuration-file and CLI settings.

    Command-line values take precedence over values read from the optional
    TOML configuration file.
    """

    args = vars(_parser().parse_args(argv))
    config_path = args.pop("config")
    values: dict[str, Any] = {}
    if config_path:
        try:
            with config_path.open("rb") as f:
                values.update(tomllib.load(f))
        except OSError as exc:
            raise ValueError(f"cannot read config file {config_path}: {exc}") from exc
        except tomllib.TOMLDecodeError as exc:
            raise ValueError(f"malformed config file {config_path}: {exc}") from exc
    values.update({k: v for k, v in args.items() if v is not None})
    allowed = {f.name for f in fields(Config)}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown configuration keys: {', '.join(sorted(unknown))}")
    cfg = replace(Config(), **values)
    cfg.validate()
    return cfg
