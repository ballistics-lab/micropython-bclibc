"""tiny_bclibc — MicroPython ballistics library.

Usage:
    import tiny_bclibc as bc

    shot = bc.Shot(bc=0.310, weight_grain=168.0, muzzle_velocity_fps=2750.0)
    req  = bc.Request(range_limit_ft=3000.0, range_step_ft=100.0)
    rows, reason = bc.integrate(shot, req)

    # Streaming (no buffer allocation per row):
    total, reason = bc.integrate_stream(shot, req,
        lambda row: None)   # return truthy to stop early
"""

import time
from collections import namedtuple as _namedtuple

import uctypes
from micropython import const

try:
    import ustruct as _struct  # type: ignore
except ImportError:
    import struct as _struct

try:
    from _tiny_bclibc import (  # noqa: I001 # type: ignore
        # Trajectory filter flags
        TRAJ_FLAG_NONE,
        TRAJ_FLAG_RANGE,
        TRAJ_FLAG_ZERO,
        TRAJ_FLAG_ZERO_UP,
        TRAJ_FLAG_ZERO_DOWN,
        TRAJ_FLAG_MACH,
        TRAJ_FLAG_APEX,
        TRAJ_FLAG_MRT,
        TRAJ_FLAG_ALL,
        # Trajectory column indices
        T_TIME,
        T_DISTANCE,
        T_VELOCITY,
        T_MACH,
        T_HEIGHT,
        T_SLANT_HEIGHT,
        T_DROP_ANGLE,
        T_WINDAGE,
        T_WINDAGE_ANGLE,
        T_SLANT_DISTANCE,
        T_ANGLE,
        T_DENSITY_RATIO,
        T_DRAG,
        T_ENERGY,
        T_OGW,
        T_FLAG,
        # Interpolation keys
        INTERP_TIME,
        INTERP_MACH,
        INTERP_POS_X,
        INTERP_POS_Y,
        INTERP_POS_Z,
        INTERP_VEL_X,
        INTERP_VEL_Y,
        INTERP_VEL_Z,
        # Buffer-sizing constants (kept private -- see below)
        SHOT_HOLDER_SIZE as _SHOT_HOLDER_SIZE,
        TRAJ_DATA_SIZE as _TRAJ_DATA_SIZE,
        # Public passthrough
        version,
        # Low-level native calls, aliased so the wrapper functions of the
        # same name below can call into them
        integrate as _integrate,
        integrate_at as _integrate_at,
        integrate_stream as _integrate_stream,
        find_zero_angle as _find_zero_angle,
        zero_point as _zero_point,
        find_apex as _find_apex,
        find_max_range as _find_max_range,
        build_multibc as _build_multibc,
        bench_lat_dp as _bench_lat_dp,
        bench_lat_sp as _bench_lat_sp,
        bench_thr_dp as _bench_thr_dp,
        bench_thr_sp as _bench_thr_sp,
        bench_peak_dp as _bench_peak_dp,
        bench_peak_sp as _bench_peak_sp,
    )
except ImportError:
    # Merged natmod build (see natmod/Makefile) -- no separate _tiny_bclibc
    # module exists; mpy_init() already populated all of the above as bare
    # globals of *this* module (see docs/develop/natmod.rst "Defining a
    # native module"). TRAJ_FLAG_*/T_*/INTERP_*/version are meant to be
    # public here too, so those need no action either way.
    #
    # SHOT_HOLDER_SIZE/TRAJ_DATA_SIZE are implementation details (only used
    # to size internal buffers below) that the usermod build already keeps
    # private via the `as _X` aliasing above -- del the public names here so
    # this build doesn't leak them onto tiny_bclibc where the usermod build
    # never would.
    #
    # integrate/integrate_at/integrate_stream/find_zero_angle/zero_point/find_apex/
    # find_max_range/build_multibc collide with this file's own wrapper
    # functions of the same name below -- capture each native global under
    # its private alias *before* the matching `def` executes and overwrites
    # it, or the wrapper would end up calling itself instead of the native
    # function.
    _SHOT_HOLDER_SIZE = SHOT_HOLDER_SIZE
    _TRAJ_DATA_SIZE = TRAJ_DATA_SIZE
    _integrate = integrate
    _integrate_at = integrate_at
    _integrate_stream = integrate_stream
    _find_zero_angle = find_zero_angle
    _zero_point = zero_point
    _find_apex = find_apex
    _find_max_range = find_max_range
    _build_multibc = build_multibc
    _bench_lat_dp = bench_lat_dp
    _bench_lat_sp = bench_lat_sp
    _bench_thr_dp = bench_thr_dp
    _bench_thr_sp = bench_thr_sp
    _bench_peak_dp = bench_peak_dp
    _bench_peak_sp = bench_peak_sp
    del (
        SHOT_HOLDER_SIZE,
        TRAJ_DATA_SIZE,
        bench_lat_dp,
        bench_lat_sp,
        bench_thr_dp,
        bench_thr_sp,
        bench_peak_dp,
        bench_peak_sp,
    )

# Public API -- marks the re-exported native constants/version as
# intentionally unreferenced within this file (ruff F401 / pyright
# reportUnusedImport both respect __all__), instead of scattering
# per-line suppression comments.
__all__ = [
    "DRAG_CUSTOM",
    "DRAG_G1",
    "DRAG_G7",
    "INTERP_MACH",
    "INTERP_POS_X",
    "INTERP_POS_Y",
    "INTERP_POS_Z",
    "INTERP_TIME",
    "INTERP_VEL_X",
    "INTERP_VEL_Y",
    "INTERP_VEL_Z",
    "TRAJ_FLAG_ALL",
    "TRAJ_FLAG_APEX",
    "TRAJ_FLAG_MACH",
    "TRAJ_FLAG_MRT",
    "TRAJ_FLAG_NONE",
    "TRAJ_FLAG_RANGE",
    "TRAJ_FLAG_ZERO",
    "TRAJ_FLAG_ZERO_DOWN",
    "TRAJ_FLAG_ZERO_UP",
    "T_ANGLE",
    "T_DENSITY_RATIO",
    "T_DISTANCE",
    "T_DRAG",
    "T_DROP_ANGLE",
    "T_ENERGY",
    "T_FLAG",
    "T_HEIGHT",
    "T_MACH",
    "T_OGW",
    "T_SLANT_DISTANCE",
    "T_SLANT_HEIGHT",
    "T_TIME",
    "T_VELOCITY",
    "T_WINDAGE",
    "T_WINDAGE_ANGLE",
    "Config",
    "MultiBC",
    "Request",
    "Shot",
    "Wind",
    "aim",
    "bench",
    "find_apex",
    "find_max_range",
    "find_zero_angle",
    "fire",
    "integrate",
    "integrate_at",
    "integrate_stream",
    "version",
    "zero",
    "zero_point",
]

_NaN = float("nan")
_INF = 1e8  # TINY_BCLIBC_MAX_WIND_DIST_FT

# ── Drag model constants ──────────────────────────────────────────────────────
DRAG_G1 = const(0)
DRAG_G7 = const(1)
DRAG_CUSTOM = const(2)

# ── Buffer sizes ──────────────────────────────────────────────────────────────
# Shot header: 17*4 + 6*4 + 4 + 1 + 1 + 2 = 100 bytes  (<-prefixed, no padding)
_MAX_WINDS = const(16)
_MAX_DRAG_PTS = const(200)
_SHOT_SIZE = const(100)
_WIND_SIZE = const(16)
_DRAG_SIZE = const(8)
_CFG_SIZE = const(28)
_REQ_SIZE = const(16)

# ── Pre-compiled uctypes descriptors ──────────────────────────────────────────
_F32 = uctypes.FLOAT32
_I32 = uctypes.INT32
_U8 = uctypes.UINT8
_U16 = uctypes.UINT16

_REQ_DESC = {
    "range_limit_ft": _F32 | 0,
    "range_step_ft": _F32 | 4,
    "time_step": _F32 | 8,
    "filter_flags": _I32 | 12,
}

_SHOT_PROPS_DESC = {
    "bc": _F32 | 0,
    "weight_grain": _F32 | 4,
    "diameter_inch": _F32 | 8,
    "length_inch": _F32 | 12,
    "muzzle_velocity_fps": _F32 | 16,
    "sight_height_ft": _F32 | 20,
    "twist_inch": _F32 | 24,
    "temp_c": _F32 | 28,
    "pressure_hpa": _F32 | 32,
    "altitude_ft": _F32 | 36,
    "humidity": _F32 | 40,
    "look_angle_rad": _F32 | 44,
    "barrel_elevation_rad": _F32 | 48,
    "barrel_azimuth_rad": _F32 | 52,
    "cant_angle_rad": _F32 | 56,
    "latitude_deg": _F32 | 60,
    "azimuth_deg": _F32 | 64,
}

_CFG_DESC = {
    "step_multiplier": _F32 | 0,
    "zero_finding_accuracy": _F32 | 4,
    "minimum_velocity": _F32 | 8,
    "maximum_drop": _F32 | 12,
    "gravity_constant": _F32 | 16,
    "minimum_altitude": _F32 | 20,
    "max_iterations": _I32 | 24,
}

_SHOT_DESC = {
    "props": (0, _SHOT_PROPS_DESC),
    "cfg": (68, _CFG_DESC),
    "max_iterations": _I32 | 92,
    "drag_type": _U8 | 96,
    "wind_count": _U8 | 97,
    "drag_count": _U16 | 98,
}

_WIND_DESC = {
    "velocity_fps": _F32 | 0,
    "direction_from_rad": _F32 | 4,
    "until_distance_ft": _F32 | 8,
    "max_distance_ft": _F32 | 12,
}

_DRAG_DESC = {
    "mach": _F32 | 0,
    "cd": _F32 | 4,
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


# ── Shot: zero-copy factory ───────────────────────────────────────────────────
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
    drag_count=None,
    winds=None,
    config=None,
):
    cfg = config if config is not None else Config()
    winds = winds or []
    wc = min(len(winds), _MAX_WINDS)
    dc = 0
    # "packed" drag input is a raw bytes-like buffer of interleaved-free,
    # parallel float32 arrays (what MultiBC() returns) -- copied by byte
    # range below instead of unpacked element-by-element through uctypes,
    # so no intermediate Python float is ever boxed for these values.
    # Plain Python sequences (hand-built custom curves) keep the original
    # per-element path unchanged.
    packed = False
    if drag_type == DRAG_CUSTOM and drag_mach and drag_cd:
        packed = isinstance(drag_mach, (bytes, bytearray, memoryview))
        if drag_count is not None:
            dc = min(drag_count, _MAX_DRAG_PTS)
        elif packed:
            dc = min(len(drag_mach) // 4, len(drag_cd) // 4, _MAX_DRAG_PTS)
        else:
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

    if packed:
        for i in range(dc):
            o = off + i * _DRAG_SIZE
            buf[o : o + 4] = drag_mach[i * 4 : i * 4 + 4]
            buf[o + 4 : o + 8] = drag_cd[i * 4 : i * 4 + 4]
        off += dc * _DRAG_SIZE
    else:
        for i in range(dc):
            sd = uctypes.struct(base + off, _DRAG_DESC, uctypes.LITTLE_ENDIAN)
            sd.mach = drag_mach[i]
            sd.cd = drag_cd[i]
            off += _DRAG_SIZE

    return _Shot(buf, s, bytearray(_SHOT_HOLDER_SIZE))


# ── Request: zero-copy factory ────────────────────────────────────────────────
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


# ── API wrappers ──────────────────────────────────────────────────────────────


def integrate(shot, req):
    return _integrate(shot.buf, shot.holder, req.buf, req.traj)


def integrate_at(shot, interp, val):
    return _integrate_at(shot.buf, shot.holder, interp, val)


def integrate_stream(shot, req, cb):
    return _integrate_stream(shot.buf, shot.holder, req.buf, cb)


def find_zero_angle(shot, dist_ft):
    return _find_zero_angle(shot.buf, shot.holder, dist_ft)


def zero_point(shot, dist_ft):
    """Return the solver's (zero angle, terminal trajectory point)."""
    return _zero_point(shot.buf, shot.holder, dist_ft)


def zero(shot, dist_ft):
    """Set ``shot``'s barrel elevation for dist_ft and return it in radians."""
    angle, _point = zero_point(shot, dist_ft)
    shot.s.props.barrel_elevation_rad = angle
    return angle


def aim(shot, dist_ft):
    """Return (vertical_hold_rad, windage_rad, point) for a target distance.

    ``point`` is retained by the zero solver; no second trajectory pass is
    made.  The vertical hold is relative to the barrel elevation currently
    stored in ``shot`` (normally set by :func:`zero`).
    """
    angle, point = zero_point(shot, dist_ft)
    return angle - shot.s.props.barrel_elevation_rad, point[T_WINDAGE_ANGLE], point


def fire(shot, req):
    """Calculate and return ``(trajectory_rows, stop_reason)``."""
    return integrate(shot, req)


def find_apex(shot):
    return _find_apex(shot.buf, shot.holder)


def find_max_range(shot, lo, hi):
    return _find_max_range(shot.buf, shot.holder, lo, hi)


def MultiBC(bc_points, drag_type=DRAG_G7):
    """Fold multiple (mach, bc) points into a single custom drag curve.

    bc_points: iterable of (mach, bc) pairs, any order -- sorted internally.
    drag_type: DRAG_G1 or DRAG_G7, selects the reference table to scale.

    Returns (mach_buf, cd_buf, count): two packed float32 buffers and the
    number of valid entries in each (the two reference tables have
    different lengths, so always use `count`, never assume a fixed size).
    Feed the result straight into
        Shot(bc=1.0, drag_type=DRAG_CUSTOM,
             drag_mach=mach_buf, drag_cd=cd_buf, drag_count=count)
    -- bc=1.0 is correct regardless of the actual bullet's BC: the
    constant cancels out of the drag-factor formula algebraically once
    the curve itself already carries the BC-ratio scaling.
    """
    pts = list(bc_points)
    pts_buf = bytearray(len(pts) * 8)
    for i, (mach, bc_val) in enumerate(pts):
        _struct.pack_into("<ff", pts_buf, i * 8, mach, bc_val)
    mach_buf = bytearray(_MAX_DRAG_PTS * 4)
    cd_buf = bytearray(_MAX_DRAG_PTS * 4)
    count = _build_multibc(drag_type, pts_buf, mach_buf, cd_buf)
    return mach_buf, cd_buf, count


# ── bench: native FPU FLOPS micro-benchmark ────────────────────────────────

_BENCH_N_LAT = const(500_000)  # x4 ops/iter
_BENCH_N_THR = const(100_000)  # x16 ops/iter


def _bench_run(label, fn, n, ops):
    fn(n // 10)  # warmup
    t0 = time.ticks_us()
    fn(n)
    dt = time.ticks_diff(time.ticks_us(), t0) / 1e6
    mflops = n * ops / dt / 1e6
    print("  {:8s}: {:9.2f} MFLOPS   dt={:.3f}s".format(label, mflops, dt))


def bench():
    """Print a native-C FPU latency/throughput/peak micro-benchmark (MFLOPS).

    Runs the lat_dp/lat_sp/thr_dp/thr_sp/peak_dp/peak_sp loops built into
    this module (see src/bench_mp.h) -- no separate .mpy to build or deploy:

        from tiny_bclibc import bench
        bench()
    """
    print("=" * 52)
    print("tiny_bclibc FPU FLOPS Benchmark")
    print("=" * 52)
    print("\nLatency-bound (volatile, sequential chain):")
    _bench_run("DP", _bench_lat_dp, _BENCH_N_LAT, 4)
    _bench_run("SP", _bench_lat_sp, _BENCH_N_LAT, 4)
    print("\nThroughput (8 independent accumulators, volatile operands):")
    _bench_run("DP", _bench_thr_dp, _BENCH_N_THR, 16)
    _bench_run("SP", _bench_thr_sp, _BENCH_N_THR, 16)
    print("\nPeak (8 independent accumulators, register-resident, add-only):")
    _bench_run("DP", _bench_peak_dp, _BENCH_N_THR, 8)
    _bench_run("SP", _bench_peak_sp, _BENCH_N_THR, 8)
    print("=" * 52)
