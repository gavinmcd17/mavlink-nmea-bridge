from mavlink_nmea_bridge.config import Config, load_config
from mavlink_nmea_bridge.state import Freshness, GPSState, GPSStateStore

def test_freshness_boundaries():
    store = GPSStateStore()
    store.update(GPSState(last_update_monotonic=100.0))
    assert store.freshness(102.0) == Freshness.VALID
    assert store.freshness(102.01) == Freshness.STALE
    assert store.freshness(105.0) == Freshness.STALE
    assert store.freshness(105.01) == Freshness.INVALID

def test_never_is_invalid_for_output_but_distinct_state():
    assert GPSStateStore().freshness(10) == Freshness.NEVER

def test_configuration_validation_and_cli_override():
    cfg = load_config(["--tcp-port", "12000", "--position-source", "GLOBAL_POSITION_INT"])
    assert cfg.tcp_port == 12000 and cfg.position_source == "GLOBAL_POSITION_INT"
    try:
        Config(tcp_port=0).validate()
        assert False
    except ValueError as exc:
        assert "tcp-port" in str(exc)

