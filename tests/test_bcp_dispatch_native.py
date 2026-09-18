# ruff: noqa

"""
BCP command dispatch native (C) test -- BCLIBC_BCP=1 usermod builds only.
Dispatch lives directly in `_tiny_bclibc` (see src/bcp_dispatch_mp.h and
tiny_bclibc_mp.c's umbrella comment: BCP doesn't get its own separate
native module, it's `_tiny_bclibc` + `#ifdef BCLIBC_BCP`).
Run with:
    micropython test_bcp_dispatch_native.py
or from repo root:
    /path/to/micropython test_bcp_dispatch_native.py

IDENT, LOAD_CONFIG, LOAD_PROFILE and LOAD_CONDITIONS are implemented so
far (see BACKLOG.md Epic 3/8) -- this test covers IDENT itself, the
drop_count telemetry it reports (from parse_frame's own failure counter),
LOAD_CONFIG's size validation and its ERR_NOT_LOADED response, the
unknown-command NotImplementedError, one full
parse_frame -> dispatch -> build_frame round trip, LOAD_PROFILE's
drag_type tagged union (G1/G7/CUSTOM/*_MULTIBC) plus its array-count
validation, and LOAD_CONDITIONS' atmosphere/wind parsing plus its own
array-count validation.

BCP state is real persistent C state across dispatch() calls in this one
process (RESET isn't implemented yet to clear it) -- so test order
matters here more than in most test files: the LOAD_CONFIG and
LOAD_CONDITIONS ERR_NOT_LOADED checks below run *before* any LOAD_PROFILE
call and depend on no profile being cached yet; the LOAD_PROFILE section
loads a real profile, the LOAD_CONDITIONS section after it depends on
that profile being cached, and the final section re-checks LOAD_CONFIG
now succeeds once one is cached. Don't reorder sections without checking
this.
"""

import struct
import sys

try:
    import _tiny_bclibc as d
    import _tiny_bclibc as f
except ImportError as ex:
    print("SKIP: _tiny_bclibc not built into this firmware:", ex)
    sys.exit(0)
if not hasattr(d, "dispatch"):
    print("SKIP: _tiny_bclibc built without BCLIBC_BCP=1 (no BCP dispatch)")
    sys.exit(0)

_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


print("=== BCP dispatch native (_tiny_bclibc) test ===")

# -- IDENT ---------------------------------------------------------------------
print("\n--- IDENT ---")
try:
    status, payload = d.dispatch(d.CMD_IDENT, 1, b"")
    if status != d.STATUS_OK:
        _fail("IDENT status", "got {}".format(status))
    else:
        _pass("IDENT status == STATUS_OK")
except Exception as ex:
    _fail("IDENT dispatch", ex)
    status, payload = None, b""

try:
    (
        proto_ver,
        real_size,
        traj_row_size,
        base_traj_size,
        max_winds,
        max_drag_pts,
        max_bc_points,
        drop_count,
        version_len,
    ) = struct.unpack_from("<BBHHBHBIB", payload, 0)
    version = payload[15 : 15 + version_len]

    checks = [
        ("proto_ver == 1", proto_ver == 1),
        ("real_size in (4, 8)", real_size in (4, 8)),
        ("traj_row_size matches real_size (64 sp / 124 dp)", traj_row_size == (64 if real_size == 4 else 124)),
        ("base_traj_size matches real_size (32 sp / 64 dp)", base_traj_size == (32 if real_size == 4 else 64)),
        ("max_winds == 5 (BCP cap, PROTOCOL.md §4.1)", max_winds == 5),
        ("max_drag_pts == 200 (BCP cap)", max_drag_pts == 200),
        ("max_bc_points == 5 (BCP cap)", max_bc_points == 5),
        ("version_len matches payload length", len(payload) == 15 + version_len),
        ("version is non-empty", len(version) > 0),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name)
    print("  (informational) version={!r} drop_count={}".format(version, drop_count))
except Exception as ex:
    _fail("IDENT payload decode", ex)

# -- LOAD_CONFIG -----------------------------------------------------------------
print("\n--- LOAD_CONFIG ---")
# Config()'s own Python-side defaults (tiny_bclibc.py) -- same values the
# device applies before the first LOAD_CONFIG (PROTOCOL.md §4.2a).
_CFG_PAYLOAD = struct.pack("<6fi", 0.5, 0.001, 50.0, -15000.0, -32.17405, -1500.0, 50)

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONFIG, 1, _CFG_PAYLOAD)
    # No LOAD_PROFILE yet -- nothing cached to re-solve a zero against.
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("LOAD_CONFIG with no profile cached -> ERR_NOT_LOADED, empty payload")
    else:
        _fail("LOAD_CONFIG no-profile case", (status, payload))
except Exception as ex:
    _fail("LOAD_CONFIG no-profile case", ex)

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONFIG, 1, b"too short")
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("LOAD_CONFIG with wrong payload size -> ERR_BAD_SIZE")
    else:
        _fail("LOAD_CONFIG bad size", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_CONFIG bad size", ex)

try:
    status, _ = d.dispatch(d.CMD_LOAD_CONFIG, 1, _CFG_PAYLOAD + b"\x00")
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("LOAD_CONFIG one byte too long -> ERR_BAD_SIZE")
    else:
        _fail("LOAD_CONFIG one byte too long", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_CONFIG one byte too long", ex)

# -- LOAD_CONDITIONS (no profile yet) ---------------------------------------------
print("\n--- LOAD_CONDITIONS (no profile cached yet) ---")


def _pack_conditions(temp_c, pressure_hpa, altitude_ft, humidity, look_angle_rad, barrel_azimuth_rad, cant_angle_rad, latitude_deg, azimuth_deg, winds):
    """winds: list of (velocity_fps, direction_from_rad, until_distance_ft, max_distance_ft),
    matching PROTOCOL.md §4.3's wire layout exactly."""
    hdr = struct.pack("<9fB", temp_c, pressure_hpa, altitude_ft, humidity, look_angle_rad, barrel_azimuth_rad, cant_angle_rad, latitude_deg, azimuth_deg, len(winds)) + b"\x00\x00\x00"
    body = b"".join(struct.pack("<4f", *w) for w in winds)
    return hdr + body


_ICAO = (15.0, 1013.25, 0.0, 0.5, 0.0, 0.0, 0.0, float("nan"), float("nan"))

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("LOAD_CONDITIONS with no profile cached -> ERR_NOT_LOADED, empty payload")
    else:
        _fail("LOAD_CONDITIONS no-profile case", (status, payload))
except Exception as ex:
    _fail("LOAD_CONDITIONS no-profile case", ex)

try:
    status, _ = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, b"too short")
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("LOAD_CONDITIONS with wrong payload size -> ERR_BAD_SIZE")
    else:
        _fail("LOAD_CONDITIONS bad size", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_CONDITIONS bad size", ex)

# -- INTEGRATE_AT (no profile yet) -------------------------------------------------
print("\n--- INTEGRATE_AT (no profile cached yet) ---")

_KEY_TIME, _KEY_MACH, _KEY_POS_X, _KEY_POS_Y, _KEY_POS_Z, _KEY_VEL_X, _KEY_VEL_Y, _KEY_VEL_Z = range(8)


def _pack_integrate_at(key, target):
    return struct.pack("<B", key) + b"\x00\x00\x00" + struct.pack("<f", target)


try:
    status, payload = d.dispatch(d.CMD_INTEGRATE_AT, 1, _pack_integrate_at(_KEY_POS_X, 100.0))
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("INTEGRATE_AT with no profile cached -> ERR_NOT_LOADED, empty payload")
    else:
        _fail("INTEGRATE_AT no-profile case", (status, payload))
except Exception as ex:
    _fail("INTEGRATE_AT no-profile case", ex)

try:
    status, _ = d.dispatch(d.CMD_INTEGRATE_AT, 1, b"short")
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("INTEGRATE_AT with wrong payload size -> ERR_BAD_SIZE")
    else:
        _fail("INTEGRATE_AT bad size", "got status={}".format(status))
except Exception as ex:
    _fail("INTEGRATE_AT bad size", ex)

try:
    # key=8 is one past TINY_BCLIBC_KEY_VEL_Z (7) -- out of InterpKey's range.
    status, _ = d.dispatch(d.CMD_INTEGRATE_AT, 1, _pack_integrate_at(8, 100.0))
    if status == d.STATUS_ERR_BAD_ARG:
        _pass("INTEGRATE_AT with key out of range -> ERR_BAD_ARG")
    else:
        _fail("INTEGRATE_AT bad key", "got status={}".format(status))
except Exception as ex:
    _fail("INTEGRATE_AT bad key", ex)

# -- INTEGRATE / INTEGRATE_FAST (no profile yet) -----------------------------------
print("\n--- INTEGRATE / INTEGRATE_FAST (no profile cached yet) ---")


def _pack_integrate_req(range_limit_ft, range_step_ft, time_step, filter_flags):
    return struct.pack("<3fi", range_limit_ft, range_step_ft, time_step, filter_flags)


def _collect_frames():
    """Returns (emit_fn, frames_list) -- emit_fn appends every (status, payload)
    dispatch() reports through the MORE callback, so a test can inspect the
    whole stream after dispatch() returns its own final (status, payload)."""
    frames = []

    def emit(status, payload):
        frames.append((status, payload))

    return emit, frames


try:
    emit, _frames = _collect_frames()
    status, payload = d.dispatch(d.CMD_INTEGRATE, 1, _pack_integrate_req(1000.0, 100.0, 0.0, 0), emit)
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"" and _frames == []:
        _pass("INTEGRATE with no profile cached -> ERR_NOT_LOADED, empty payload, no MORE frames")
    else:
        _fail("INTEGRATE no-profile case", (status, payload, _frames))
except Exception as ex:
    _fail("INTEGRATE no-profile case", ex)

try:
    status, _ = d.dispatch(d.CMD_INTEGRATE, 1, b"short", (lambda s, p: None))
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("INTEGRATE with wrong payload size -> ERR_BAD_SIZE")
    else:
        _fail("INTEGRATE bad size", "got status={}".format(status))
except Exception as ex:
    _fail("INTEGRATE bad size", ex)

try:
    # emit is required (dispatch()'s optional 4th arg) -- without it any
    # rows the engine produces would just vanish, so this is a caller bug,
    # signaled as a plain TypeError rather than a wire status.
    d.dispatch(d.CMD_INTEGRATE, 1, _pack_integrate_req(1000.0, 100.0, 0.0, 0))
    _fail("INTEGRATE without emit", "expected TypeError, got a result")
except TypeError:
    _pass("INTEGRATE without an emit callback raises TypeError")
except Exception as ex:
    _fail("INTEGRATE without emit", "wrong exception type: " + str(ex))

# -- unknown command -------------------------------------------------------------
print("\n--- unknown command ---")
try:
    d.dispatch(99, 1, b"")
    _fail("unknown command", "expected NotImplementedError, got a result")
except NotImplementedError:
    _pass("unknown command raises NotImplementedError")
except Exception as ex:
    _fail("unknown command", "wrong exception type: " + str(ex))

# -- drop_count telemetry --------------------------------------------------------
print("\n--- drop_count telemetry ---")
try:
    before = f.drop_count()
    bad = bytearray(f.build_frame(1, 1, 0, b"x"))
    bad[3] ^= 0xFF  # corrupt CRC
    result = f.parse_frame(bytes(bad[1:-1]))
    after = f.drop_count()
    if result is None and after == before + 1:
        _pass("parse_frame drops a bad-CRC frame and bumps drop_count by 1")
    else:
        _fail("drop_count bump", "result={} before={} after={}".format(result, before, after))

    _, payload2 = d.dispatch(d.CMD_IDENT, 1, b"")
    reported = struct.unpack_from("<I", payload2, 10)[0]
    if reported == after:
        _pass("IDENT reports the live drop_count")
    else:
        _fail("IDENT drop_count", "reported={} actual={}".format(reported, after))
except Exception as ex:
    _fail("drop_count telemetry", ex)

# -- full parse_frame -> dispatch -> build_frame round trip ---------------------
print("\n--- full round trip ---")
try:
    req_frame = f.build_frame(d.CMD_IDENT, 42, 0, b"")
    type_, seq, req_status, req_payload = f.parse_frame(req_frame[1:-1])
    resp_status, resp_payload = d.dispatch(type_, seq, req_payload)
    resp_frame = f.build_frame(type_ | 0x80, seq, resp_status, resp_payload)
    type2, seq2, status2, payload2 = f.parse_frame(resp_frame[1:-1])

    checks = [
        ("request type/seq/status parsed correctly", (type_, seq, req_status) == (d.CMD_IDENT, 42, 0)),
        ("response type has the 0x80 response bit set", type2 == (d.CMD_IDENT | 0x80)),
        ("response seq echoes the request's seq", seq2 == 42),
        ("response status is OK", status2 == d.STATUS_OK),
        ("response payload matches what dispatch() returned", payload2 == resp_payload),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name)
except Exception as ex:
    _fail("full round trip", ex)

# -- LOAD_PROFILE ------------------------------------------------------------
print("\n--- LOAD_PROFILE ---")


def _pack_profile(bc, wg, dia, length, mv, sh, twist, zero_ft, drag_type, points):
    """(mach, second) pairs -- {mach,cd} for CUSTOM, {mach,bc} for *_MULTIBC,
    matching PROTOCOL.md §4.2's drag_points shape per drag_type."""
    hdr = struct.pack("<8fBBH", bc, wg, dia, length, mv, sh, twist, zero_ft, drag_type, 0, len(points))
    pts = b"".join(struct.pack("<ff", a, b) for a, b in points)
    return hdr + pts


_ZERO_FT = 300.0 * 3.28084  # 300 m in feet
_DRAG_G1, _DRAG_G7, _DRAG_CUSTOM, _DRAG_G1_MULTIBC, _DRAG_G7_MULTIBC = 0, 1, 2, 3, 4

try:
    p = _pack_profile(0.305, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    status, payload = d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    if status == d.STATUS_OK and len(payload) == 4:
        angle_g7 = struct.unpack("<f", payload)[0]
        _pass("LOAD_PROFILE G7 static table -> OK, angle={:.6f}".format(angle_g7))
    else:
        _fail("LOAD_PROFILE G7", (status, payload))
except Exception as ex:
    _fail("LOAD_PROFILE G7", ex)

try:
    p = _pack_profile(1.0, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_CUSTOM, [(0.5, 0.30), (2.0, 0.25), (3.5, 0.20)])
    status, payload = d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    if status == d.STATUS_OK and len(payload) == 4:
        _pass("LOAD_PROFILE CUSTOM curve -> OK")
    else:
        _fail("LOAD_PROFILE CUSTOM", (status, payload))
except Exception as ex:
    _fail("LOAD_PROFILE CUSTOM", ex)

try:
    p = _pack_profile(999.0, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7_MULTIBC, [(0.8, 0.30), (2.5, 0.28)])
    status, payload = d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    if status == d.STATUS_OK and len(payload) == 4:
        _pass("LOAD_PROFILE G7_MULTIBC -> OK (bc field ignored, not validated)")
    else:
        _fail("LOAD_PROFILE G7_MULTIBC", (status, payload))
except Exception as ex:
    _fail("LOAD_PROFILE G7_MULTIBC", ex)

# -- Regression: atmosphere defaults must actually be applied -----------------
# Caught for real during development: bcp_state's atmosphere fields
# (temp_c/pressure_hpa/altitude_ft/humidity) were left C-zero-initialized
# instead of ICAO standard atmosphere (PROTOCOL.md §4.3's documented
# fallback) -- pressure_hpa=0 makes TINY_BCLIBC_Atmosphere_from_conditions()
# return density_ratio=0 (its own documented vacuum case), so drag silently
# disappeared regardless of bc. A LOAD_PROFILE with a very different bc
# must produce a meaningfully different zero angle, not a bit-identical one.
print("\n--- regression: bc must actually affect the zero angle ---")
try:
    p_lowdrag = _pack_profile(2.0, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    _, payload_lowdrag = d.dispatch(d.CMD_LOAD_PROFILE, 1, p_lowdrag)
    p_highdrag = _pack_profile(0.05, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    _, payload_highdrag = d.dispatch(d.CMD_LOAD_PROFILE, 1, p_highdrag)
    angle_lowdrag = struct.unpack("<f", payload_lowdrag)[0]
    angle_highdrag = struct.unpack("<f", payload_highdrag)[0]
    # bc=0.05 is ~40x more drag than bc=2.0 -- expect a large (>2x), not
    # merely nonzero, difference at this range.
    if angle_highdrag > angle_lowdrag * 2.0:
        _pass(
            "bc=2.0 -> {:.6f} rad, bc=0.05 -> {:.6f} rad (drag clearly applied)".format(
                angle_lowdrag, angle_highdrag
            )
        )
    else:
        _fail("bc sensitivity regression", (angle_lowdrag, angle_highdrag))
except Exception as ex:
    _fail("bc sensitivity regression", ex)

# -- LOAD_PROFILE validation errors --------------------------------------------
print("\n--- LOAD_PROFILE validation errors ---")

_checks = [
    ("bad drag_type", _pack_profile(0.3, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, 5, []), d.STATUS_ERR_BAD_ARG),
    ("G1 with a nonzero drag_count", _pack_profile(0.3, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G1, [(0.5, 0.3)]), d.STATUS_ERR_BAD_ARG),
    ("too short to read the fixed header", b"short", d.STATUS_ERR_BAD_SIZE),
]
for name, payload_in, expect_status in _checks:
    try:
        status, _ = d.dispatch(d.CMD_LOAD_PROFILE, 1, payload_in)
        if status == expect_status:
            _pass("LOAD_PROFILE " + name)
        else:
            _fail("LOAD_PROFILE " + name, "got status={}".format(status))
    except Exception as ex:
        _fail("LOAD_PROFILE " + name, ex)

try:
    # MULTIBC with 0 breakpoints must be rejected, not read out-of-bounds.
    hdr = struct.pack("<8fBBH", 0.3, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G1_MULTIBC, 0, 0)
    status, _ = d.dispatch(d.CMD_LOAD_PROFILE, 1, hdr)
    if status == d.STATUS_ERR_BAD_ARG:
        _pass("LOAD_PROFILE *_MULTIBC with 0 breakpoints -> ERR_BAD_ARG, not a crash")
    else:
        _fail("LOAD_PROFILE MULTIBC 0 points", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_PROFILE MULTIBC 0 points", ex)

try:
    # One more CUSTOM point than the BCP cap (200) -- ERR_BAD_ARG, not silently clamped.
    hdr = struct.pack("<8fBBH", 0.3, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_CUSTOM, 0, 201)
    status, _ = d.dispatch(d.CMD_LOAD_PROFILE, 1, hdr + b"\x00" * (201 * 8))
    if status == d.STATUS_ERR_BAD_ARG:
        _pass("LOAD_PROFILE CUSTOM over the 200-point cap -> ERR_BAD_ARG")
    else:
        _fail("LOAD_PROFILE CUSTOM over cap", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_PROFILE CUSTOM over cap", ex)

# -- LOAD_CONDITIONS (profile now cached) -------------------------------------
print("\n--- LOAD_CONDITIONS (profile cached) ---")

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))
    if status == d.STATUS_OK and len(payload) == 4:
        angle_no_wind = struct.unpack("<f", payload)[0]
        _pass("LOAD_CONDITIONS ICAO/no-wind -> OK, angle={:.6f}".format(angle_no_wind))
    else:
        _fail("LOAD_CONDITIONS ICAO/no-wind", (status, payload))
        angle_no_wind = None
except Exception as ex:
    _fail("LOAD_CONDITIONS ICAO/no-wind", ex)
    angle_no_wind = None

try:
    # A strong crosswind must actually move the solved zero angle -- same
    # class of "not just nonzero, meaningfully different" regression check
    # LOAD_PROFILE's bc-sensitivity test above uses.
    winds = [(30.0, 1.5707963, 0.0, 1e7)]  # 30 fps from 90 deg (pure crosswind), full range
    status, payload = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=winds))
    if status == d.STATUS_OK and len(payload) == 4:
        angle_wind = struct.unpack("<f", payload)[0]
        _pass("LOAD_CONDITIONS with 1 wind segment -> OK, angle={:.6f}".format(angle_wind))
    else:
        _fail("LOAD_CONDITIONS with 1 wind segment", (status, payload))
except Exception as ex:
    _fail("LOAD_CONDITIONS with 1 wind segment", ex)

try:
    # Thin, cold air vs. a hot/low-density atmosphere -- must give a clearly
    # different zero angle, not a bit-identical one (regression class from
    # LOAD_PROFILE's own atmosphere-defaults bug, applied to LOAD_CONDITIONS
    # instead of the on-device defaults).
    cold = (-20.0, 1013.25, 8000.0, 0.1, 0.0, 0.0, 0.0, float("nan"), float("nan"))
    hot = (40.0, 1013.25, 0.0, 0.1, 0.0, 0.0, 0.0, float("nan"), float("nan"))
    _, payload_cold = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*cold, winds=[]))
    _, payload_hot = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*hot, winds=[]))
    angle_cold = struct.unpack("<f", payload_cold)[0]
    angle_hot = struct.unpack("<f", payload_hot)[0]
    if angle_cold != angle_hot:
        _pass("cold/thin -> {:.6f} rad, hot/dense -> {:.6f} rad (atmosphere clearly applied)".format(angle_cold, angle_hot))
    else:
        _fail("atmosphere sensitivity regression", (angle_cold, angle_hot))
except Exception as ex:
    _fail("atmosphere sensitivity regression", ex)

try:
    # 5 winds is the BCP cap (PROTOCOL.md §4.1) -- must be accepted.
    winds5 = [(10.0, 0.0, float(i) * 100.0, float(i + 1) * 100.0) for i in range(5)]
    status, payload = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=winds5))
    if status == d.STATUS_OK and len(payload) == 4:
        _pass("LOAD_CONDITIONS with 5 winds (BCP cap) -> OK")
    else:
        _fail("LOAD_CONDITIONS with 5 winds", (status, payload))
except Exception as ex:
    _fail("LOAD_CONDITIONS with 5 winds", ex)

try:
    # 6 winds is one past the BCP cap -- ERR_BAD_ARG, not silently clamped.
    winds6 = [(10.0, 0.0, float(i) * 100.0, float(i + 1) * 100.0) for i in range(6)]
    status, _ = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=winds6))
    if status == d.STATUS_ERR_BAD_ARG:
        _pass("LOAD_CONDITIONS with 6 winds (over cap) -> ERR_BAD_ARG")
    else:
        _fail("LOAD_CONDITIONS with 6 winds", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_CONDITIONS with 6 winds", ex)

try:
    # wind_count says 2 but only 1 wind's worth of bytes follow -- ERR_BAD_SIZE.
    bad = _pack_conditions(*_ICAO, winds=[(10.0, 0.0, 100.0, 200.0)])
    bad = bad[:36] + struct.pack("<B", 2) + b"\x00\x00\x00" + bad[40:]
    status, _ = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, bad)
    if status == d.STATUS_ERR_BAD_SIZE:
        _pass("LOAD_CONDITIONS wind_count/payload-length mismatch -> ERR_BAD_SIZE")
    else:
        _fail("LOAD_CONDITIONS wind_count mismatch", "got status={}".format(status))
except Exception as ex:
    _fail("LOAD_CONDITIONS wind_count mismatch", ex)

# reset back to the ICAO/no-wind baseline so later sections (LOAD_CONFIG
# re-solve check) aren't affected by whichever conditions ran last above.
try:
    d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))
except Exception:
    pass

# -- INTEGRATE_AT (profile cached) ---------------------------------------------
print("\n--- INTEGRATE_AT (profile cached) ---")

_BASE_TRAJ_NAMES = "time px py pz vx vy vz mach".split()
_TRAJ_NAMES = (
    "time distance_ft velocity_fps mach height_ft slant_height_ft drop_angle_rad "
    "windage_ft windage_angle_rad slant_distance_ft angle_rad density_ratio drag "
    "energy_ft_lb ogw_lb"
).split()


def _unpack_integrate_at(payload, base_size, traj_size):
    base = struct.unpack_from("<{}f".format(len(_BASE_TRAJ_NAMES)), payload, 0)
    traj = struct.unpack_from("<{}fi".format(len(_TRAJ_NAMES)), payload, base_size)
    return dict(zip(_BASE_TRAJ_NAMES, base)), dict(zip(_TRAJ_NAMES + ["flag"], traj))


try:
    # Reload a clean G7 profile + ICAO/no-wind conditions so this section
    # doesn't depend on whichever LOAD_CONDITIONS variant ran last above.
    p = _pack_profile(0.305, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))

    _, ident_payload = d.dispatch(d.CMD_IDENT, 1, b"")
    traj_row_size, base_traj_size = struct.unpack_from("<HH", ident_payload, 2)
    status, payload = d.dispatch(d.CMD_INTEGRATE_AT, 1, _pack_integrate_at(_KEY_POS_X, _ZERO_FT))
    if status != d.STATUS_OK:
        _fail("INTEGRATE_AT at the zero distance", (status, payload))
    elif len(payload) != base_traj_size + traj_row_size:
        _fail("INTEGRATE_AT payload size", "got {} expected {}".format(len(payload), base_traj_size + traj_row_size))
    else:
        base, traj = _unpack_integrate_at(payload, base_traj_size, traj_row_size)
        checks = [
            ("px matches the requested target distance", abs(base["px"] - _ZERO_FT) < 0.5),
            ("distance_ft matches the requested target too", abs(traj["distance_ft"] - _ZERO_FT) < 0.5),
            ("height_ft is ~0 at the zero range (rifle is zeroed there)", abs(traj["height_ft"]) < 0.1),
            ("drop_angle_rad is ~0 at the zero range", abs(traj["drop_angle_rad"]) < 1e-4),
            ("velocity_fps has decayed below the muzzle velocity", 0.0 < traj["velocity_fps"] < 2750.0),
            ("mach is positive and supersonic-range plausible", 0.5 < traj["mach"] < 5.0),
        ]
        for name, ok in checks:
            if ok:
                _pass(name)
            else:
                _fail(name, {"base": base, "traj": traj})
except Exception as ex:
    _fail("INTEGRATE_AT at the zero distance", ex)

try:
    # KEY_MACH target of 100.0 is never reached by a bullet that starts well
    # below it and only decelerates -- no bracketing crossing exists.
    status, payload = d.dispatch(d.CMD_INTEGRATE_AT, 1, _pack_integrate_at(_KEY_MACH, 100.0))
    if status == d.STATUS_ERR_INTERNAL and payload == b"":
        _pass("INTEGRATE_AT with an unreachable target -> ERR_INTERNAL, empty payload")
    else:
        _fail("INTEGRATE_AT unreachable target", (status, payload))
except Exception as ex:
    _fail("INTEGRATE_AT unreachable target", ex)

# -- INTEGRATE / INTEGRATE_FAST (profile cached) --------------------------------
print("\n--- INTEGRATE / INTEGRATE_FAST (profile cached) ---")

_TERM_TARGET_RANGE_REACHED = 1


def _decode_more_frames(frames, row_size):
    """Validates row_idx/count bookkeeping across a stream's MORE frames and
    returns the concatenated raw row bytes. Fails loudly (raises) on any
    inconsistency instead of silently under-checking."""
    next_idx = 0
    rows = b""
    for status, payload in frames:
        assert status == d.STATUS_MORE, "frame status {} != STATUS_MORE".format(status)
        row_idx, count, rsvd = struct.unpack_from("<HBB", payload, 0)
        assert row_idx == next_idx, "row_idx {} != expected {}".format(row_idx, next_idx)
        assert len(payload) == 4 + count * row_size, "frame payload length mismatch"
        rows += payload[4:]
        next_idx += count
    return rows, next_idx


try:
    p = _pack_profile(0.305, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))
    _, ident_payload = d.dispatch(d.CMD_IDENT, 1, b"")
    traj_row_size, base_traj_size = struct.unpack_from("<HH", ident_payload, 2)

    emit, frames = _collect_frames()
    status, payload = d.dispatch(d.CMD_INTEGRATE, 1, _pack_integrate_req(1000.0, 100.0, 0.0, 0), emit)
    total, reason = struct.unpack("<Ii", payload)

    checks = [
        ("final status is OK", status == d.STATUS_OK),
        ("total is 11 rows (0..1000 ft step 100)", total == 11),
        ("reason is TARGET_RANGE_REACHED", reason == _TERM_TARGET_RANGE_REACHED),
        ("more than one MORE frame was needed (batch cap < total rows)", len(frames) > 1),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name, {"status": status, "total": total, "reason": reason, "n_frames": len(frames)})

    rows, counted = _decode_more_frames(frames, traj_row_size)
    if counted == total:
        _pass("MORE frames' row_idx/count bookkeeping sums to total ({} rows)".format(total))
    else:
        _fail("row_idx/count bookkeeping", "counted {} != total {}".format(counted, total))

    row0 = struct.unpack_from("<15fi", rows, 0)
    row0_checks = [
        ("row 0 distance_ft == 0", row0[1] == 0.0),
        ("row 0 velocity_fps == muzzle velocity (2750 fps)", abs(row0[2] - 2750.0) < 0.01),
        ("row 0 height_ft == -sight_height_ft (-1.5 ft, bore below the sight line at the muzzle)", abs(row0[4] - (-1.5)) < 0.01),
    ]
    for name, ok in row0_checks:
        if ok:
            _pass(name)
        else:
            _fail(name, row0)
except Exception as ex:
    _fail("INTEGRATE (profile cached)", ex)

try:
    emit, frames = _collect_frames()
    status, payload = d.dispatch(d.CMD_INTEGRATE_FAST, 1, _pack_integrate_req(1000.0, 100.0, 0.0, 0), emit)
    total, reason = struct.unpack("<Ii", payload)
    rows, counted = _decode_more_frames(frames, 16)  # FastTrajData is always 16 B (4 f32 fields)

    checks = [
        ("final status is OK", status == d.STATUS_OK),
        ("total matches INTEGRATE's own total for the same request (11 rows)", total == 11),
        ("row_idx/count bookkeeping sums to total", counted == total),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name, {"status": status, "total": total, "counted": counted})

    row0 = struct.unpack_from("<4f", rows, 0)
    if row0[0] == 0.0 and abs(row0[3] - 2750.0) < 0.01:
        _pass("FastTrajData row 0: distance_ft=0, velocity_fps=muzzle velocity")
    else:
        _fail("FastTrajData row 0", row0)
except Exception as ex:
    _fail("INTEGRATE_FAST (profile cached)", ex)

try:
    # A range_limit well under one batch's worth of rows -- exercises the
    # single-frame path (no mid-stream flush, only the trailing one).
    emit, frames = _collect_frames()
    status, payload = d.dispatch(d.CMD_INTEGRATE, 1, _pack_integrate_req(200.0, 100.0, 0.0, 0), emit)
    total, _reason = struct.unpack("<Ii", payload)
    if status == d.STATUS_OK and total == 3 and len(frames) == 1:
        _pass("a short stream (3 rows) fits in exactly one MORE frame")
    else:
        _fail("short stream single-frame case", {"status": status, "total": total, "n_frames": len(frames)})
except Exception as ex:
    _fail("short stream single-frame case", ex)

# -- LOAD_CONFIG now succeeds, since a profile is cached ----------------------
print("\n--- LOAD_CONFIG after a profile is cached ---")
try:
    cfg = struct.pack("<6fi", 0.5, 0.001, 50.0, -15000.0, -32.17405, -1500.0, 50)
    status, payload = d.dispatch(d.CMD_LOAD_CONFIG, 1, cfg)
    if status == d.STATUS_OK and len(payload) == 4:
        _pass("LOAD_CONFIG with a profile cached -> OK, re-solves the zero")
    else:
        _fail("LOAD_CONFIG with profile cached", (status, payload))
except Exception as ex:
    _fail("LOAD_CONFIG with profile cached", ex)

# -- ABORT / RESET (run last -- RESET wipes all cached state) -----------------
print("\n--- ABORT / RESET ---")

try:
    # No C read/write loop yet (Epic 4), so dispatch() calls run
    # synchronously to completion -- nothing is ever "in flight" for ABORT
    # to preempt here. Still a valid, always-OK command per PROTOCOL.md
    # §4.8's wire contract.
    status, payload = d.dispatch(d.CMD_ABORT, 1, b"")
    if status == d.STATUS_OK and payload == b"":
        _pass("ABORT with nothing running -> OK, empty payload")
    else:
        _fail("ABORT idle case", (status, payload))
except Exception as ex:
    _fail("ABORT idle case", ex)

try:
    # Bump drop_count so RESET clearing it back to 0 is an actual check,
    # not a vacuous one -- force one more bad frame here rather than
    # relying on the round-trip/telemetry sections above having left it
    # nonzero.
    bad = bytearray(f.build_frame(d.CMD_IDENT, 1, 0, b""))
    bad[3] ^= 0xFF
    f.parse_frame(bytes(bad[1:-1]))
    drop_before = f.drop_count()

    # Profile/config/conditions are all still cached from the sections
    # above -- confirm that before RESET, so the after-RESET checks below
    # are testing an actual clear, not a no-op on already-empty state.
    status, payload = d.dispatch(d.CMD_LOAD_CONFIG, 1, cfg)
    profile_was_cached = status == d.STATUS_OK

    status, payload = d.dispatch(d.CMD_RESET, 1, b"")
    checks = [
        ("a profile was actually cached before RESET (precondition)", profile_was_cached),
        ("RESET -> OK, empty payload", status == d.STATUS_OK and payload == b""),
        ("drop_count was nonzero before RESET (precondition)", drop_before > 0),
        ("RESET clears drop_count back to 0", f.drop_count() == 0),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name)
except Exception as ex:
    _fail("RESET", ex)

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONFIG, 1, cfg)
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("LOAD_CONFIG after RESET -> ERR_NOT_LOADED (profile cache cleared)")
    else:
        _fail("LOAD_CONFIG after RESET", (status, payload))
except Exception as ex:
    _fail("LOAD_CONFIG after RESET", ex)

try:
    status, payload = d.dispatch(d.CMD_LOAD_CONDITIONS, 1, _pack_conditions(*_ICAO, winds=[]))
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("LOAD_CONDITIONS after RESET -> ERR_NOT_LOADED (profile cache cleared)")
    else:
        _fail("LOAD_CONDITIONS after RESET", (status, payload))
except Exception as ex:
    _fail("LOAD_CONDITIONS after RESET", ex)

try:
    status, payload = d.dispatch(d.CMD_INTEGRATE_AT, 1, _pack_integrate_at(_KEY_POS_X, 100.0))
    if status == d.STATUS_ERR_NOT_LOADED and payload == b"":
        _pass("INTEGRATE_AT after RESET -> ERR_NOT_LOADED (profile cache cleared)")
    else:
        _fail("INTEGRATE_AT after RESET", (status, payload))
except Exception as ex:
    _fail("INTEGRATE_AT after RESET", ex)

try:
    # A fresh LOAD_PROFILE after RESET must work exactly like on a cold
    # boot -- RESET must not leave any stale internal pointer/count behind
    # that a later LOAD_PROFILE fails to fully overwrite.
    p = _pack_profile(0.305, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, _DRAG_G7, [])
    status, payload = d.dispatch(d.CMD_LOAD_PROFILE, 1, p)
    if status == d.STATUS_OK and len(payload) == 4:
        _pass("LOAD_PROFILE works normally again after RESET")
    else:
        _fail("LOAD_PROFILE after RESET", (status, payload))
except Exception as ex:
    _fail("LOAD_PROFILE after RESET", ex)

print("\n=== done ===")
if _failures:
    print("{} test(s) FAILED".format(_failures))
    sys.exit(_failures)
