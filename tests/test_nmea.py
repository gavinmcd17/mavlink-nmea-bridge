from datetime import datetime, timezone
from mavlink_nmea_bridge.nmea import _coord, checksum, gga, vtg
from mavlink_nmea_bridge.state import Freshness, GPSState

def test_coordinates_positive_negative_and_near_zero():
    assert _coord(40.1234567, True) == ("4007.4074", "N")
    assert _coord(-75.1234567, False) == ("07507.4074", "W")
    assert _coord(0.000001, True) == ("0000.0001", "N")
    assert _coord(-0.000001, False) == ("00000.0001", "W")

def test_checksum_independently_known_sentence():
    body = "GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,,M,,"
    # This body includes all fields required by this bridge, including the
    # empty DGPS age and station fields.
    assert checksum(body) == "52"
    assert gga(GPSState(latitude=48.1173, longitude=11.5166667, altitude_m=545.4,
        fix_type=3, satellites=8, hdop=0.9, utc=datetime(2020, 1, 1, 12, 35, 19, tzinfo=timezone.utc),
        last_update_monotonic=0), Freshness.VALID).startswith("$GPGGA,123519.00")
    assert gga(GPSState(latitude=48.1173, longitude=11.5166667, altitude_m=545.4,
        fix_type=3, satellites=8, hdop=0.9, utc=datetime(2020, 1, 1, 12, 35, 19, tzinfo=timezone.utc),
        last_update_monotonic=0), Freshness.VALID).strip().endswith("*7C")

def test_vtg_and_speed_conversions():
    result = vtg(GPSState(course_deg=54.7, speed_mps=2.829, last_update_monotonic=0), Freshness.VALID)
    assert result.startswith("$GPVTG,54.7,T,,M,5.50,N,10.18,K*")
    assert result.endswith("\r\n")

def test_no_fix_gga_has_empty_coordinates():
    result = gga(GPSState(latitude=40, longitude=-75, fix_type=3, utc=datetime(2020, 1, 1, tzinfo=timezone.utc)), Freshness.INVALID)
    assert ",,,0," in result
