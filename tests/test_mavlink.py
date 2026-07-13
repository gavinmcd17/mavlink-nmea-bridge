from mavlink_nmea_bridge.mavlink_input import MAVLinkReader, _number
from mavlink_nmea_bridge.state import GPSStateStore

class Message:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
    def get_srcSystem(self): return 7
    def get_srcComponent(self): return 1

def test_scaling_and_unknown_sentinels():
    state = GPSStateStore()
    reader = MAVLinkReader("test", 115200, "GPS_RAW_INT", state, 5)
    reader._handle_gps(Message(lat=401234567, lon=-751234567, alt=120500, fix_type=3,
        satellites_visible=10, eph=125, vel=250, cog=9000, time_usec=0))
    s = state.snapshot()
    assert (s.latitude, s.longitude, s.altitude_m, s.hdop, s.speed_mps, s.course_deg) == (40.1234567, -75.1234567, 120.5, 1.25, 2.5, 90.0)
    reader._handle_gps(Message(lat=401234567, lon=-751234567, alt=2147483647, fix_type=3,
        satellites_visible=65535, eph=65535, vel=65535, cog=65535, time_usec=0))
    s = state.snapshot()
    assert s.altitude_m is None and s.hdop is None and s.speed_mps is None and s.course_deg is None
    assert _number(65535, unknown=(65535,)) is None

def test_global_position_speed_and_metadata():
    state = GPSStateStore()
    reader = MAVLinkReader("test", 115200, "GLOBAL_POSITION_INT", state, 5)
    reader._handle_gps(Message(lat=1, lon=2, alt=1000, fix_type=3, satellites_visible=8, eph=100, vel=1, cog=2, time_usec=0))
    reader._handle_global(Message(lat=401234567, lon=-751234567, alt=120500, vx=300, vy=400, hdg=9000, time_boot_ms=5))
    s = state.snapshot()
    assert s.source == "GLOBAL_POSITION_INT" and s.speed_mps == 5 and s.fix_type == 3 and s.satellites == 8

