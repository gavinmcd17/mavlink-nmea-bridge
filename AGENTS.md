# AGENTS.md

## Project overview

`mavlink-nmea-bridge` is a Python service that reads ArduPilot MAVLink GPS
data and broadcasts NMEA-0183 sentences to TCP clients. Runtime code lives in
`src/mavlink_nmea_bridge/`; tests live in `tests/`.

## Development

- Use Python 3.12 or newer.
- Install development dependencies with `python -m pip install -e '.[test]'`.
- Run the test suite with `python -m pytest` or `make test`.
- Run the CLI with `python -m mavlink_nmea_bridge --help`.
- Keep changes focused and preserve the existing `src/` package layout.

## Code and test conventions

- Add or update tests in `tests/` for behavior changes.
- Preserve the bridge's freshness policy and invalid-data behavior unless a
  change explicitly updates that contract.
- Keep network and serial operations compatible with the service's
  non-blocking, multi-client design.
- Use the type-checking settings in `pyproject.toml` when adding or changing
  code.

## Configuration and deployment

- Use `config.example.toml` as the template for local configuration; do not
  commit machine-specific `config.toml` files or credentials.
- Deployment artifacts are under `deploy/` and target systemd on Linux.
- Be careful when changing TCP defaults, serial endpoint handling, or service
  user/permission settings because these affect deployed Raspberry Pi systems.

