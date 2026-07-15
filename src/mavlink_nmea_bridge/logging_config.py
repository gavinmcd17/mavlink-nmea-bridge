"""Logging configuration for command-line bridge processes."""

import logging


def configure_logging(level: str) -> None:
    """Configure root logging with the requested named severity level."""

    logging.basicConfig(level=getattr(logging, level.upper()), format="%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
