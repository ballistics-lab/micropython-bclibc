# ruff: noqa

"""tiny_bclibc_mp_ffi — MicroPython unix FFI backend for tiny_bclibc.

Drop-in replacement for ``tiny_bclibc`` on unix MicroPython (x64 / aarch64).
Calls libtiny_bclibc.so via the built-in ``ffi`` module instead of loading
the native .mpy.  The public API is identical to tiny_bclibc.py.

Usage::

    import tiny_bclibc_mp_ffi as bc            # instead of: import tiny_bclibc as bc
    shot = bc.Shot(bc=0.310, weight_grain=168.0, muzzle_velocity_fps=2750.0)
    req  = bc.Request(range_limit_ft=3000.0, range_step_ft=100.0)
    rows, reason = bc.integrate(shot, req)

The .so path is resolved as (first match wins):
    1. ``TINY_BCLIBC_SO`` environment variable
    2. ``<this file's directory>/../../tiny_bclibc/build-shared/libtiny_bclibc.so``

Precision is selected via the ``TINY_BCLIBC_PRECISION`` environment variable:
    - ``double`` (default) — matches ``-DTINY_BCLIBC_SINGLE_PRECISION`` off
    - ``single``           — matches ``-DTINY_BCLIBC_SINGLE_PRECISION`` on

Requires 64-bit MicroPython unix with ffi + uctypes (standard build).
32-bit MicroPython is not supported (different pointer/struct layout).
"""

import struct
import array
import os

import ffi
import uctypes
from collections import namedtuple as _namedtuple

if struct.calcsize("P") != 8:
    raise ImportError("tiny_bclibc_mp_ffi requires 64-bit MicroPython (x64 / aarch64)")


def _rel(rel_path):
    """Resolve rel_path relative to this file's directory (MicroPython-compatible)."""
    f = __file__
    d = f[: f.rfind("/")] if "/" in f else os.getcwd()
    return d + "/" + rel_path


# ── Precision selection ────────────────────────────────────────────────────────
_SP = os.getenv("TINY_BCLIBC_PRECISION", "double").lower().startswith("s")
_R  = "f" if _SP else "d"   # array / struct real_t type code
_RS = 4   if _SP else 8     # sizeof(real_t)

# ── .so location ──────────────────────────────────────────────────────────────
_SO = os.getenv("TINY_BCLIBC_SO") or _rel("../bclibc/tiny_bclibc/build-shared/libtiny_bclibc.so")
_lib = ffi.open(_SO)

# ── FFI function handles ───────────────────────────────────────────────────────
_f_build    = _lib.func("i", "tiny_bclibc_build_shot_props",  "PPP")
_f_integ    = _lib.func("i", "tiny_bclibc_integrate",         "PPPiPPP")
_f_at       = _lib.func("i", "tiny_bclibc_integrate_at",      "Pi" + _R + "PP")
_f_apex     = _lib.func("i", "tiny_bclibc_find_apex",         "PP")
_f_zero     = _lib.func("i", "tiny_bclibc_find_zero_angle",   "P" + _R + "P")
_f_maxrange = _lib.func("i", "tiny_bclibc_find_max_range",    "P" + _R + _R + "PP")
_f_err      = _lib.func("s", "tiny_bclibc_last_error",        "")

# ── C struct sizes — x64/aarch64, verified with gcc offsetof() ───────────────
# Sizes differ only between sp (real_t=float) and dp (real_t=double).
# 32-bit would also need different layouts (not supported above).
if _SP:
    _SHOT_C_SIZE   = 136   # 11f + pad + 2ptr + i32 + pad + ptr + i32 + 6f + cfg(4f+i32+2f)
    _PROPS_C_SIZE  = 512   # conservative upper bound (actual sp: 216)
    _TRAJ_C_SIZE   = 64    # 15f + i32
    _BASE_C_SIZE   = 32    # 8f
    _REQ_C_SIZE    = 16    # 3f + i32
    _WIND_C_SIZE   = 16    # 4f
    _CURVE_C_SIZE  = 16    # 4f
    # TINY_BCLIBC_Shot field offsets (sp, x64)
    _OFF_MACH_PTR  = 48
    _OFF_CD_PTR    = 56
    _OFF_DSIZ      = 64
    _OFF_WIND_PTR  = 72
    _OFF_WCNT      = 80
    _OFF_ANGLES    = 84    # 6×float: look, barrel_el, barrel_az, cant, lat, az
    _OFF_CFG_SMULT = 108   # Config: step_mult, zero_acc, min_vel, max_drop (4f)
    _OFF_CFG_ITER  = 124   # max_iterations (i32)
    _OFF_CFG_GRAV  = 128   # gravity_constant, minimum_altitude (2f)
else:
    _SHOT_C_SIZE   = 232   # 11d + 2ptr + i32 + pad + ptr + i32 + pad + 6d + cfg(4d+i32+pad+2d)
    _PROPS_C_SIZE  = 512   # conservative upper bound (actual dp: 376)
    _TRAJ_C_SIZE   = 128   # 15d + i32 + 4pad
    _BASE_C_SIZE   = 64    # 8d
    _REQ_C_SIZE    = 32    # 3d + i32 + 4pad
    _WIND_C_SIZE   = 32    # 4d
    _CURVE_C_SIZE  = 32    # 4d
    _OFF_MACH_PTR  = 88
    _OFF_CD_PTR    = 96
    _OFF_DSIZ      = 104
    _OFF_WIND_PTR  = 112
    _OFF_WCNT      = 120
    _OFF_ANGLES    = 128   # 6×double
    _OFF_CFG_SMULT = 176   # Config: step_mult, zero_acc, min_vel, max_drop (4d)
    _OFF_CFG_ITER  = 208   # max_iterations (i32)  [+4 pad after]
    _OFF_CFG_GRAV  = 216   # gravity_constant, minimum_altitude (2d)


def _ptr(buf):
    return uctypes.addressof(buf)


# ── Built-in drag tables — type matches real_t ────────────────────────────────
_G7_MACH = array.array(_R, [
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.65, 0.70, 0.725, 0.75, 0.775, 0.80, 0.825,
    0.85, 0.875, 0.90, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.075,
    1.10, 1.125, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.50, 1.55,
    1.60, 1.65, 1.70, 1.75, 1.80, 1.85, 1.90, 1.95, 2.00, 2.05,
    2.10, 2.15, 2.20, 2.25, 2.30, 2.35, 2.40, 2.45, 2.50, 2.55,
    2.60, 2.65, 2.70, 2.75, 2.80, 2.90, 3.00, 3.10, 3.20, 3.30,
    3.40, 3.50, 3.60, 3.70, 3.80, 3.90, 4.00, 4.20, 4.40, 4.60,
    4.80, 5.00,
])
_G7_CD = array.array(_R, [
    0.1198, 0.1197, 0.1196, 0.1194, 0.1193, 0.1194, 0.1194, 0.1194,
    0.1193, 0.1193, 0.1194, 0.1193, 0.1194, 0.1197, 0.1202, 0.1207,
    0.1215, 0.1226, 0.1242, 0.1266, 0.1306, 0.1368, 0.1464, 0.1660,
    0.2054, 0.2993, 0.3803, 0.4015, 0.4043, 0.4034, 0.4014, 0.3987,
    0.3955, 0.3884, 0.3810, 0.3732, 0.3657, 0.3580, 0.3440, 0.3376,
    0.3315, 0.3260, 0.3209, 0.3160, 0.3117, 0.3078, 0.3042, 0.3010,
    0.2980, 0.2951, 0.2922, 0.2892, 0.2864, 0.2835, 0.2807, 0.2779,
    0.2752, 0.2725, 0.2697, 0.2670, 0.2643, 0.2615, 0.2588, 0.2561,
    0.2534, 0.2481, 0.2429, 0.2379, 0.2330, 0.2283, 0.2238, 0.2194,
    0.2151, 0.2110, 0.2070, 0.2032, 0.1995, 0.1924, 0.1858, 0.1794,
    0.1732, 0.1672,
])
_G1_MACH = array.array(_R, [
    0.00, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45,
    0.50, 0.55, 0.60, 0.70, 0.725, 0.75, 0.775, 0.80, 0.825, 0.85,
    0.875, 0.90, 0.925, 0.95, 0.975, 1.0, 1.025, 1.05, 1.075, 1.10,
    1.125, 1.15, 1.20, 1.25, 1.30, 1.35, 1.40, 1.45, 1.50, 1.55,
    1.60, 1.65, 1.70, 1.75, 1.80, 1.85, 1.90, 1.95, 2.00, 2.05,
    2.10, 2.15, 2.20, 2.25, 2.30, 2.35, 2.40, 2.45, 2.50, 2.60,
    2.70, 2.80, 2.90, 3.00, 3.10, 3.20, 3.30, 3.40, 3.50, 3.60,
    3.70, 3.80, 3.90, 4.00, 4.20, 4.40, 4.60, 4.80, 5.00,
])
_G1_CD = array.array(_R, [
    0.2629, 0.2558, 0.2487, 0.2413, 0.2344, 0.2278, 0.2214, 0.2155,
    0.2104, 0.2061, 0.2032, 0.2020, 0.2034, 0.2165, 0.2230, 0.2313,
    0.2417, 0.2546, 0.2706, 0.2901, 0.3136, 0.3415, 0.3734, 0.4084,
    0.4448, 0.4805, 0.5136, 0.5427, 0.5677, 0.5883, 0.6053, 0.6191,
    0.6393, 0.6518, 0.6589, 0.6621, 0.6625, 0.6607, 0.6573, 0.6528,
    0.6474, 0.6413, 0.6347, 0.6280, 0.6210, 0.6141, 0.6072, 0.6003,
    0.5934, 0.5867, 0.5804, 0.5743, 0.5685, 0.5630, 0.5577, 0.5527,
    0.5481, 0.5438, 0.5397, 0.5325, 0.5264, 0.5211, 0.5168, 0.5133,
    0.5105, 0.5084, 0.5067, 0.5054, 0.5040, 0.5030, 0.5022, 0.5016,
    0.5010, 0.5006, 0.4998, 0.4995, 0.4992, 0.4990, 0.4988,
])

# ── Drag model constants ──────────────────────────────────────────────────────
DRAG_G1 = 0
DRAG_G7 = 1
DRAG_CUSTOM = 2

# ── Trajectory filter flags ───────────────────────────────────────────────────
TRAJ_FLAG_NONE     = 0
TRAJ_FLAG_ZERO_UP  = 1
TRAJ_FLAG_ZERO_DOWN = 2
TRAJ_FLAG_ZERO     = 3
TRAJ_FLAG_MACH     = 4
TRAJ_FLAG_RANGE    = 8
TRAJ_FLAG_APEX     = 16
TRAJ_FLAG_MRT      = 32
TRAJ_FLAG_ALL      = 31

# ── Trajectory column indices ─────────────────────────────────────────────────
T_TIME          = 0
T_DISTANCE      = 1
T_VELOCITY      = 2
T_MACH          = 3
T_HEIGHT        = 4
T_SLANT_HEIGHT  = 5
T_DROP_ANGLE    = 6
T_WINDAGE       = 7
T_WINDAGE_ANGLE = 8
T_SLANT_DISTANCE = 9
T_ANGLE         = 10
T_DENSITY_RATIO = 11
T_DRAG          = 12
T_ENERGY        = 13
T_OGW           = 14
T_FLAG          = 15

# ── Interpolation keys ────────────────────────────────────────────────────────
INTERP_TIME  = 0
INTERP_MACH  = 1
INTERP_POS_X = 2
INTERP_POS_Y = 3
INTERP_POS_Z = 4
INTERP_VEL_X = 5
INTERP_VEL_Y = 6
INTERP_VEL_Z = 7

# ── Python-side buffer layout (float32 packed) — mirrors tiny_bclibc.py ──────
_NaN  = float("nan")
_INF  = 1e8
_MAX_WINDS    = 16
_MAX_DRAG_PTS = 128
_SHOT_SIZE    = 100
_WIND_SIZE    = 16
_DRAG_SIZE    = 8
_CFG_SIZE     = 28
_REQ_SIZE     = 16
_SHOT_HOLDER_SIZE = 1       # not used; kept for API compatibility
_TRAJ_DATA_SIZE   = _TRAJ_C_SIZE  # rows in req.traj match C struct size

# ── uctypes descriptors (float32, little-endian) — same as tiny_bclibc.py ────
_F32 = uctypes.FLOAT32
_I32 = uctypes.INT32
_U8  = uctypes.UINT8
_U16 = uctypes.UINT16

_REQ_DESC = {
    "range_limit_ft": _F32 | 0,
    "range_step_ft":  _F32 | 4,
    "time_step":      _F32 | 8,
    "filter_flags":   _I32 | 12,
}
_SHOT_PROPS_DESC = {
    "bc":                   _F32 | 0,
    "weight_grain":         _F32 | 4,
    "diameter_inch":        _F32 | 8,
    "length_inch":          _F32 | 12,
    "muzzle_velocity_fps":  _F32 | 16,
    "sight_height_ft":      _F32 | 20,
    "twist_inch":           _F32 | 24,
    "temp_c":               _F32 | 28,
    "pressure_hpa":         _F32 | 32,
    "altitude_ft":          _F32 | 36,
    "humidity":             _F32 | 40,
    "look_angle_rad":       _F32 | 44,
    "barrel_elevation_rad": _F32 | 48,
    "barrel_azimuth_rad":   _F32 | 52,
    "cant_angle_rad":       _F32 | 56,
    "latitude_deg":         _F32 | 60,
    "azimuth_deg":          _F32 | 64,
}
_CFG_DESC = {
    "step_multiplier":        _F32 | 0,
    "zero_finding_accuracy":  _F32 | 4,
    "minimum_velocity":       _F32 | 8,
    "maximum_drop":           _F32 | 12,
    "gravity_constant":       _F32 | 16,
    "minimum_altitude":       _F32 | 20,
    "max_iterations":         _I32 | 24,
}
_SHOT_DESC = {
    "props":          (0,  _SHOT_PROPS_DESC),
    "cfg":            (68, _CFG_DESC),
    "max_iterations": _I32 | 92,
    "drag_type":      _U8  | 96,
    "wind_count":     _U8  | 97,
    "drag_count":     _U16 | 98,
}
_WIND_DESC = {
    "velocity_fps":       _F32 | 0,
    "direction_from_rad": _F32 | 4,
    "until_distance_ft":  _F32 | 8,
    "max_distance_ft":    _F32 | 12,
}
_DRAG_DESC = {
    "mach": _F32 | 0,
    "cd":   _F32 | 4,
}

# ── Wind ──────────────────────────────────────────────────────────────────────
_Wind = _namedtuple("Wind", ("buf", "s"))


def Wind(
    velocity_fps=0.0,
    direction_from_rad=0.0,
    until_distance_ft=_INF,
    max_distance_ft=_INF,
):
    buf = bytearray(_WIND_SIZE)
    s = uctypes.struct(uctypes.addressof(buf), _WIND_DESC, uctypes.LITTLE_ENDIAN)
    s.velocity_fps = velocity_fps
    s.direction_from_rad = direction_from_rad
    s.until_distance_ft = until_distance_ft
    s.max_distance_ft = max_distance_ft
    return _Wind(buf, s)


# ── Config ────────────────────────────────────────────────────────────────────
_Config = _namedtuple("Config", ("buf", "s"))


def Config(
    step_multiplier=0.5,
    zero_finding_accuracy=0.001,
    minimum_velocity=50.0,
    maximum_drop=-15000.0,
    max_iterations=50,
    gravity_constant=-32.17405,
    minimum_altitude=-1500.0,
):
    buf = bytearray(_CFG_SIZE)
    s = uctypes.struct(uctypes.addressof(buf), _CFG_DESC, uctypes.LITTLE_ENDIAN)
    s.step_multiplier = step_multiplier
    s.zero_finding_accuracy = zero_finding_accuracy
    s.minimum_velocity = minimum_velocity
    s.maximum_drop = maximum_drop
    s.gravity_constant = gravity_constant
    s.minimum_altitude = minimum_altitude
    s.max_iterations = int(max_iterations)
    return _Config(buf, s)


# ── Shot ──────────────────────────────────────────────────────────────────────
_Shot = _namedtuple("Shot", ("buf", "s", "holder"))


def Shot(
    bc=0.0,
    weight_grain=0.0,
    diameter_inch=0.0,
    length_inch=0.0,
    muzzle_velocity_fps=0.0,
    sight_height_ft=0.0,
    twist_inch=0.0,
    temp_c=15.0,
    pressure_hpa=1013.25,
    altitude_ft=0.0,
    humidity=0.5,
    look_angle_rad=0.0,
    barrel_elevation_rad=0.0,
    barrel_azimuth_rad=0.0,
    cant_angle_rad=0.0,
    latitude_deg=_NaN,
    azimuth_deg=_NaN,
    drag_type=DRAG_G7,
    drag_mach=None,
    drag_cd=None,
    winds=None,
    config=None,
):
    cfg = config if config is not None else Config()
    winds = winds or []
    wc = min(len(winds), _MAX_WINDS)
    dc = 0
    if drag_type == DRAG_CUSTOM and drag_mach and drag_cd:
        dc = min(len(drag_mach), len(drag_cd), _MAX_DRAG_PTS)

    buf = bytearray(_SHOT_SIZE + wc * _WIND_SIZE + dc * _DRAG_SIZE)
    base = uctypes.addressof(buf)
    s = uctypes.struct(base, _SHOT_DESC, uctypes.LITTLE_ENDIAN)
    p = s.props
    p.bc = bc
    p.weight_grain = weight_grain
    p.diameter_inch = diameter_inch
    p.length_inch = length_inch
    p.muzzle_velocity_fps = muzzle_velocity_fps
    p.sight_height_ft = sight_height_ft
    p.twist_inch = twist_inch
    p.temp_c = temp_c
    p.pressure_hpa = pressure_hpa
    p.altitude_ft = altitude_ft
    p.humidity = humidity
    p.look_angle_rad = look_angle_rad
    p.barrel_elevation_rad = barrel_elevation_rad
    p.barrel_azimuth_rad = barrel_azimuth_rad
    p.cant_angle_rad = cant_angle_rad
    p.latitude_deg = latitude_deg
    p.azimuth_deg = azimuth_deg
    buf[68 : 68 + _CFG_SIZE] = cfg.buf
    s.drag_type = drag_type
    s.wind_count = wc
    s.drag_count = dc

    off = _SHOT_SIZE
    for i in range(wc):
        buf[off : off + _WIND_SIZE] = winds[i].buf
        off += _WIND_SIZE

    for i in range(dc):
        sd = uctypes.struct(base + off, _DRAG_DESC, uctypes.LITTLE_ENDIAN)
        sd.mach = drag_mach[i]
        sd.cd = drag_cd[i]
        off += _DRAG_SIZE

    return _Shot(buf, s, bytearray(_SHOT_HOLDER_SIZE))


# ── Request ───────────────────────────────────────────────────────────────────
_Request = _namedtuple("Request", ("buf", "s", "traj"))


def Request(
    range_limit_ft=3000.0,
    range_step_ft=100.0,
    time_step=0.0,
    filter_flags=TRAJ_FLAG_RANGE,
):
    buf = bytearray(_REQ_SIZE)
    s = uctypes.struct(uctypes.addressof(buf), _REQ_DESC, uctypes.LITTLE_ENDIAN)
    s.range_limit_ft = range_limit_ft
    s.range_step_ft = range_step_ft
    s.time_step = time_step
    s.filter_flags = filter_flags
    cap = int(range_limit_ft / range_step_ft) + 64
    traj = bytearray(cap * _TRAJ_DATA_SIZE)
    return _Request(buf, s, traj)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_props(shot_buf):
    """Build TINY_BCLIBC_ShotProps from shot._buf (float32 packed).

    Converts Python-side float32 buffer to the C-side struct (sp or dp).
    Returns (props_c, holder) — holder keeps pointer targets alive.
    """
    buf = shot_buf

    s = struct.unpack_from("<17f", buf, 0)
    bc, wt, dia, length, mv, sh, tw, tc, phpa, alt, hum, la, be, baz, cant, lat, az = s

    step_mult, zero_acc, min_vel, max_drop, gravity, min_alt, max_iter = (
        struct.unpack_from("<6fi", buf, 68)
    )

    drag_type  = buf[96]
    wind_count = buf[97]
    drag_count = struct.unpack_from("<H", buf, 98)[0]

    if drag_type == DRAG_G1:
        mach_d, cd_d = _G1_MACH, _G1_CD
    elif drag_type == DRAG_CUSTOM:
        wn_ = min(wind_count, 16)
        drag_off = 100 + wn_ * 16
        n = min(drag_count, 128)
        mach_d = array.array(_R)
        cd_d   = array.array(_R)
        for i in range(n):
            m, c = struct.unpack_from("<ff", buf, drag_off + i * 8)
            mach_d.append(float(m))
            cd_d.append(float(c))
    else:
        mach_d, cd_d = _G7_MACH, _G7_CD
    n_drag = len(mach_d)

    wn = min(wind_count, 16)
    winds_c = bytearray(max(wn, 1) * _WIND_C_SIZE)
    for i in range(wn):
        wf = struct.unpack_from("<4f", buf, 100 + i * 16)
        struct.pack_into(
            "<4" + _R, winds_c, i * _WIND_C_SIZE,
            float(wf[0]), float(wf[1]), float(wf[2]), float(wf[3]),
        )

    shot_c = bytearray(_SHOT_C_SIZE)
    struct.pack_into(
        "<11" + _R, shot_c, 0,
        float(bc), float(wt), float(dia), float(length),
        float(mv), float(sh), float(tw), float(tc),
        float(phpa), float(alt), float(hum),
    )
    struct.pack_into("<Q", shot_c, _OFF_MACH_PTR, _ptr(mach_d))
    struct.pack_into("<Q", shot_c, _OFF_CD_PTR,   _ptr(cd_d))
    struct.pack_into("<i", shot_c, _OFF_DSIZ,     n_drag)
    struct.pack_into("<Q", shot_c, _OFF_WIND_PTR, _ptr(winds_c) if wn > 0 else 0)
    struct.pack_into("<i", shot_c, _OFF_WCNT,     wn)
    struct.pack_into(
        "<6" + _R, shot_c, _OFF_ANGLES,
        float(la), float(be), float(baz), float(cant), float(lat), float(az),
    )
    struct.pack_into(
        "<4" + _R, shot_c, _OFF_CFG_SMULT,
        float(step_mult), float(zero_acc), float(min_vel), float(max_drop),
    )
    struct.pack_into("<i", shot_c, _OFF_CFG_ITER, int(max_iter))
    struct.pack_into("<2" + _R, shot_c, _OFF_CFG_GRAV, float(gravity), float(min_alt))

    curve_c  = bytearray(n_drag * _CURVE_C_SIZE)
    props_c  = bytearray(_PROPS_C_SIZE)

    rc = _f_build(shot_c, curve_c, props_c)
    if rc != 0:
        raise ValueError("build_shot_props rc={}: {}".format(rc, _f_err()))

    return props_c, (shot_c, curve_c, mach_d, cd_d, winds_c)


def _pack_req_c(req):
    """Convert Request (float32 buf) → TINY_BCLIBC_TrajectoryRequest C struct."""
    limit, step, tstep = struct.unpack_from("<3f", req.buf, 0)
    flags = struct.unpack_from("<i", req.buf, 12)[0]
    req_c = bytearray(_REQ_C_SIZE)
    struct.pack_into("<3" + _R, req_c, 0, float(limit), float(step), float(tstep))
    struct.pack_into("<i", req_c, 3 * _RS, flags)
    return req_c


def _parse_traj(buf, idx=0):
    """Parse TINY_BCLIBC_TrajectoryData at slot idx → 16-tuple."""
    off = idx * _TRAJ_C_SIZE
    v = struct.unpack_from("<15" + _R, buf, off)
    flag = struct.unpack_from("<i", buf, off + 15 * _RS)[0]
    return (v[0], v[1], v[2], v[3], v[4], v[5], v[6], v[7],
            v[8], v[9], v[10], v[11], v[12], v[13], v[14], flag)


def _parse_base(buf):
    """Parse TINY_BCLIBC_BaseTrajData → 8-tuple."""
    return struct.unpack_from("<8" + _R, buf, 0)


# ── Public API — mirrors tiny_bclibc.py ──────────────────────────────────────

def version():
    return "ffi-sp" if _SP else "ffi-dp"


def integrate(shot, req):
    props_c, _alive = _build_props(shot.buf)
    req_c = _pack_req_c(req)
    cap   = len(req.traj) // _TRAJ_C_SIZE
    out_w = bytearray(4)
    out_t = bytearray(4)
    out_r = bytearray(4)
    rc = _f_integ(props_c, req_c, req.traj, cap, out_w, out_t, out_r)
    if rc == 6:  # ERR_BUF_TOO_SMALL
        total = struct.unpack("<i", out_t)[0]
        tmp = bytearray(total * _TRAJ_C_SIZE)
        rc = _f_integ(props_c, req_c, tmp, total, out_w, out_t, out_r)
        if rc != 0:
            raise ValueError("integrate rc={}: {}".format(rc, _f_err()))
        written = struct.unpack("<i", out_w)[0]
        reason  = struct.unpack("<i", out_r)[0]
        return [_parse_traj(tmp, i) for i in range(written)], reason
    if rc != 0:
        raise ValueError("integrate rc={}: {}".format(rc, _f_err()))
    written = struct.unpack("<i", out_w)[0]
    reason  = struct.unpack("<i", out_r)[0]
    return [_parse_traj(req.traj, i) for i in range(written)], reason


def integrate_at(shot, interp, val):
    props_c, _alive = _build_props(shot.buf)
    raw_c  = bytearray(_BASE_C_SIZE)
    full_c = bytearray(_TRAJ_C_SIZE)
    rc = _f_at(props_c, int(interp), float(val), raw_c, full_c)
    if rc != 0:
        raise ValueError("integrate_at rc={}: {}".format(rc, _f_err()))
    return _parse_base(raw_c), _parse_traj(full_c)


def integrate_stream(shot, req, cb):
    rows, reason = integrate(shot, req)
    for i, row in enumerate(rows):
        if cb(row):
            return i + 1, 5  # 5 = TINY_BCLIBC_TERM_CALLBACK
    return len(rows), reason


def find_zero_angle(shot, dist_ft):
    props_c, _alive = _build_props(shot.buf)
    out = bytearray(_RS)
    rc = _f_zero(props_c, float(dist_ft), out)
    if rc != 0:
        raise ValueError("find_zero_angle rc={}: {}".format(rc, _f_err()))
    return struct.unpack_from("<" + _R, out)[0]


def find_apex(shot):
    props_c, _alive = _build_props(shot.buf)
    out = bytearray(_TRAJ_C_SIZE)
    rc = _f_apex(props_c, out)
    if rc != 0:
        raise ValueError("find_apex rc={}: {}".format(rc, _f_err()))
    return _parse_traj(out)


def find_max_range(shot, lo, hi):
    props_c, _alive = _build_props(shot.buf)
    out_range = bytearray(_RS)
    out_angle = bytearray(_RS)
    rc = _f_maxrange(props_c, float(lo), float(hi), out_range, out_angle)
    if rc != 0:
        raise ValueError("find_max_range rc={}: {}".format(rc, _f_err()))
    return struct.unpack_from("<" + _R, out_range)[0], struct.unpack_from("<" + _R, out_angle)[0]
