from __future__ import annotations
import asyncio
import sys
from .app import run
from .config import load_config

def main() -> int:
    try:
        asyncio.run(run(load_config()))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

