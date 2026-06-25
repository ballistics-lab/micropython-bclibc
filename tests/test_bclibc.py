# ruff: noqa

"""
tiny_bclibc natmod integration test.
Run with:
    micropython test_bclibc.py
or from repo root:
    /path/to/micropython micropython/test_bclibc.py
"""

import sys
import math
import array

_IS_MPY = sys.implementation.name == "micropython"

try:
    _HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
except NameError:
    _HERE = "."
sys.path.append(_HERE)

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, Wind, Config, DRAG_G7, DRAG_CUSTOM

# ── Custom drag table (same values as built-in G7) ────────────────────────
G7_MACH = array.array(
    "f",
    [
        0.00,
        0.05,
        0.10,
        0.15,
        0.20,
        0.25,
        0.30,
        0.35,
        0.40,
        0.45,
        0.50,
        0.55,
        0.60,
        0.65,
        0.70,
        0.725,
        0.75,
        0.775,
        0.80,
        0.825,
        0.85,
        0.875,
        0.90,
        0.925,
        0.95,
        0.975,
        1.0,
        1.025,
        1.05,
        1.075,
        1.10,
        1.125,
        1.15,
        1.20,
        1.25,
        1.30,
        1.35,
        1.40,
        1.50,
        1.55,
        1.60,
        1.65,
        1.70,
        1.75,
        1.80,
        1.85,
        1.90,
        1.95,
        2.00,
        2.05,
        2.10,
        2.15,
        2.20,
        2.25,
        2.30,
        2.35,
        2.40,
        2.45,
        2.50,
        2.55,
        2.60,
        2.65,
        2.70,
        2.75,
        2.80,
        2.90,
        3.00,
        3.10,
        3.20,
        3.30,
        3.40,
        3.50,
        3.60,
        3.70,
        3.80,
        3.90,
        4.00,
        4.20,
        4.40,
        4.60,
        4.80,
        5.00,
    ],
)
G7_CD = array.array(
    "f",
    [
        0.1198,
        0.1197,
        0.1196,
        0.1194,
        0.1193,
        0.1194,
        0.1194,
        0.1194,
        0.1193,
        0.1193,
        0.1194,
        0.1193,
        0.1194,
        0.1197,
        0.1202,
        0.1207,
        0.1215,
        0.1226,
        0.1242,
        0.1266,
        0.1306,
        0.1368,
        0.1464,
        0.1660,
        0.2054,
        0.2993,
        0.3803,
        0.4015,
        0.4043,
        0.4034,
        0.4014,
        0.3987,
        0.3955,
        0.3884,
        0.3810,
        0.3732,
        0.3657,
        0.3580,
        0.3440,
        0.3376,
        0.3315,
        0.3260,
        0.3209,
        0.3160,
        0.3117,
        0.3078,
        0.3042,
        0.3010,
        0.2980,
        0.2951,
        0.2922,
        0.2892,
        0.2864,
        0.2835,
        0.2807,
        0.2779,
        0.2752,
        0.2725,
        0.2697,
        0.2670,
        0.2643,
        0.2615,
        0.2588,
        0.2561,
        0.2534,
        0.2481,
        0.2429,
        0.2379,
        0.2330,
        0.2283,
        0.2238,
        0.2194,
        0.2151,
        0.2110,
        0.2070,
        0.2032,
        0.1995,
        0.1924,
        0.1858,
        0.1794,
        0.1732,
        0.1672,
    ],
)

SHOT = Shot(
    bc=0.310,
    weight_grain=168.0,
    diameter_inch=0.308,
    length_inch=1.2,
    muzzle_velocity_fps=2750.0,
    sight_height_ft=0.125,
    twist_inch=11.0,
    temp_c=15.0,
    pressure_hpa=1013.25,
    altitude_ft=0.0,
    humidity=0.5,
    drag_type=DRAG_G7,
)

SHOT_CUSTOM = Shot(
    bc=0.310,
    weight_grain=168.0,
    diameter_inch=0.308,
    length_inch=1.2,
    muzzle_velocity_fps=2750.0,
    sight_height_ft=0.125,
    twist_inch=11.0,
    drag_type=DRAG_CUSTOM,
    drag_mach=G7_MACH,
    drag_cd=G7_CD,
)

REQUEST = Request(
    range_limit_ft=1500.0,
    range_step_ft=300.0,
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

ZERO_DIST_FT = 300.0 * 3.28084  # 300 m in feet
ZERO_DIST_100M_FT = 100.0 * 3.28084  # 100 m in feet


_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


# ── Tests ──────────────────────────────────────────────────────────────────────

print("=== bclibc natmod test ===")
print("version:", bc.version())

# -- Wind / Config namedtuple ---------------------------------------------------
print("\n--- Wind / Config namedtuple ---")
try:
    w = Wind(10.0, 1.5)
    if w.s.velocity_fps == 10.0 and w.s.until_distance_ft == 1e8:
        _pass("Wind (buf,s) — field access + defaults")
    else:
        _fail("Wind (buf,s)", (w.s.velocity_fps, w.s.until_distance_ft))
    cfg = Config(max_iterations=100)
    if cfg.s.max_iterations == 100 and cfg.s.step_multiplier == 0.5:
        _pass("Config (buf,s) — kwarg + defaults")
    else:
        _fail("Config (buf,s)", (cfg.s.max_iterations, cfg.s.step_multiplier))
    if _IS_MPY:
        import gc

        gc.collect()
        bw = gc.mem_alloc()
        winds = [Wind(float(i), 0.0) for i in range(100)]
        aw = gc.mem_alloc()
        del winds
        gc.collect()
        bc2 = gc.mem_alloc()
        cfgs = [Config() for _ in range(100)]
        ac = gc.mem_alloc()
        del cfgs
        gc.collect()
        _pass(
            "Wind RAM={} B/inst  Config RAM={} B/inst".format(
                (aw - bw) // 100, (ac - bc2) // 100
            )
        )
    else:
        import tracemalloc

        tracemalloc.start()
        winds = [Wind(float(i), 0.0) for i in range(100)]
        _, wpeak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        tracemalloc.start()
        cfgs = [Config() for _ in range(100)]
        _, cpeak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        del winds, cfgs
        _pass(
            "Wind RAM~{} B/inst  Config RAM~{} B/inst".format(
                wpeak // 100, cpeak // 100
            )
        )
except Exception as ex:
    _fail("Wind/Config namedtuple", ex)

# -- Integration (built-in G7) -------------------------------------------------
print("\n--- integrate (builtin G7, 1500 ft, step 300) ---")
try:
    rows, reason = bc.integrate(SHOT, REQUEST)
    if len(rows) >= 2:
        _pass("integrate — {} rows, stop reason {}".format(len(rows), reason))
    else:
        _fail("integrate", "expected >=2 rows, got " + str(len(rows)))
    print(
        "  {:>8s}  {:>8s}  {:>8s}  {:>8s}".format(
            "dist_ft", "vel_fps", "height_ft", "mach"
        )
    )
    for r in rows:
        print("  {:>8.0f}  {:>8.1f}  {:>8.3f}  {:>8.3f}".format(r[1], r[2], r[4], r[3]))
except Exception as ex:
    _fail("integrate", ex)

# -- Integration (custom array drag table) ------------------------------------
print("\n--- integrate (custom array G7, 1500 ft, step 300) ---")
try:
    rows2, reason2 = bc.integrate(SHOT_CUSTOM, REQUEST)
    if len(rows2) >= 2:
        _pass("integrate custom — {} rows, stop reason {}".format(len(rows2), reason2))
    else:
        _fail("integrate custom", "expected >=2 rows, got " + str(len(rows2)))
except Exception as ex:
    _fail("integrate custom", ex)

# -- find_zero_angle -----------------------------------------------------------
# Reference: py-ballisticcalc (G7 BC=0.310, 168gr, 2750fps, sight 1.5in, 300m zero)
#   0.002502148750322508 rad = 0.1434°
# Tolerance 1e-4 rad (0.006°) — tight enough to catch premature-convergence bugs
#   (e.g. FAST_ZERO_FIND with acc misused as angle tolerance returned 0.001362 rad, off by 0.0014)
_ZERO_300M_REF = 0.002502
_ZERO_300M_TOL = 1e-4
print("\n--- find_zero_angle (300 m zero) ---")
elev = None
try:
    elev = bc.find_zero_angle(SHOT, ZERO_DIST_FT)
    _pass(
        "find_zero_angle elev_rad={:.6f}  ({:.4f} deg)".format(elev, math.degrees(elev))
    )
    if abs(elev - _ZERO_300M_REF) > _ZERO_300M_TOL:
        _fail(
            "find_zero_angle value",
            "expected ~{:.6f} rad, got {:.6f} rad (diff={:.2e})".format(
                _ZERO_300M_REF, elev, abs(elev - _ZERO_300M_REF)
            ),
        )
except Exception as ex:
    _fail("find_zero_angle", ex)

# -- find_zero_angle at 100 m -------------------------------------------------
print("\n--- find_zero_angle (100 m zero) ---")
try:
    elev_100m = bc.find_zero_angle(SHOT, ZERO_DIST_100M_FT)
    elev_100m_mrad = math.degrees(elev_100m) * math.pi / 180 * 1000  # rad → mrad
    _pass(
        "find_zero_angle 100m  elev_rad={:.6f}  ({:.4f} deg  {:.2f} mrad)".format(
            elev_100m, math.degrees(elev_100m), elev_100m_mrad
        )
    )
    # At 100 m the barrel must be tilted slightly upward
    if elev_100m <= 0:
        _fail(
            "find_zero_angle 100m",
            "elevation must be positive, got {}".format(elev_100m),
        )
except Exception as ex:
    _fail("find_zero_angle 100m", ex)

# -- find_apex (needs non-zero barrel elevation) ------------------------------
print("\n--- find_apex (zeroed shot) ---")
try:
    _elev = elev if elev is not None else 0.002442
    zeroed = Shot(
        bc=0.310,
        weight_grain=168.0,
        diameter_inch=0.308,
        length_inch=1.2,
        muzzle_velocity_fps=2750.0,
        sight_height_ft=0.125,
        twist_inch=11.0,
        barrel_elevation_rad=_elev,
        drag_type=DRAG_G7,
    )
    apex = bc.find_apex(zeroed)
    _pass("find_apex dist_ft={:.1f}  height_ft={:.1f}".format(apex[1], apex[4]))
except Exception as ex:
    _fail("find_apex", ex)

# -- integrate_at --------------------------------------------------------------
print("\n--- integrate_at (POS_X = 1000 ft) ---")
try:
    raw, full = bc.integrate_at(SHOT, bc.INTERP_POS_X, 1000.0)
    _pass("integrate_at dist_ft={:.1f}  vel_fps={:.1f}".format(full[1], full[2]))
except Exception as ex:
    _fail("integrate_at", ex)


# -- integrate_stream ----------------------------------------------------------
print("\n--- integrate_stream (collect all points) ---")
try:
    collected = []
    total_s, reason_s = bc.integrate_stream(
        SHOT, REQUEST, lambda row: collected.append(row)
    )
    rows_ref, _ = bc.integrate(SHOT, REQUEST)
    if len(collected) == len(rows_ref):
        _pass("integrate_stream — {} points (total={})".format(len(collected), total_s))
    else:
        _fail(
            "integrate_stream",
            "stream={} vs integrate={}".format(len(collected), len(rows_ref)),
        )
except Exception as ex:
    _fail("integrate_stream", ex)

print("\n--- integrate_stream (stop when energy < 1000 ft·lbf, 5 km range) ---")
try:
    REQ_5KM = Request(
        range_limit_ft=5000.0 * 3.28084,
        range_step_ft=300.0 * 3.28084,
        filter_flags=bc.TRAJ_FLAG_RANGE,
    )
    T_ENERGY = bc.T_ENERGY
    stopped_at = [None]
    count_e = [0]

    def _cb_energy(row):
        count_e[0] += 1
        if row[T_ENERGY] < 1000.0:
            stopped_at[0] = row[bc.T_DISTANCE]
            return True

    _, reason_e = bc.integrate_stream(SHOT, REQ_5KM, _cb_energy)
    if reason_e == 5 and stopped_at[0] is not None:
        _pass(
            "integrate_stream stop — energy<1000 at {:.0f} ft after {} pts".format(
                stopped_at[0], count_e[0]
            )
        )
    else:
        _fail(
            "integrate_stream stop",
            "reason={} stopped_at={}".format(reason_e, stopped_at[0]),
        )
except Exception as ex:
    _fail("integrate_stream stop", ex)

# -- RAM usage during 3 km trajectory (100 m step) ----------------------------
print("\n--- RAM: integrate 3 km / 100 m step ---")
try:
    REQ_3KM = Request(
        range_limit_ft=3000.0 * 3.28084,
        range_step_ft=100.0 * 3.28084,
        filter_flags=bc.TRAJ_FLAG_RANGE,
    )
    if _IS_MPY:
        import gc

        gc.collect()
        mem_before = gc.mem_alloc()
        rows_3km, _ = bc.integrate(SHOT, REQ_3KM)
        mem_after = gc.mem_alloc()
        gc.collect()
        mem_after_gc = gc.mem_alloc()
        _pass(
            "integrate 3 km — {} rows  alloc={} B  alloc_after_gc={} B".format(
                len(rows_3km), mem_after - mem_before, mem_after_gc - mem_before
            )
        )
        print(
            "  mem_before={} B  mem_peak={} B  mem_after_gc={} B".format(
                mem_before, mem_after, mem_after_gc
            )
        )
    else:
        import tracemalloc

        tracemalloc.start()
        rows_3km, _ = bc.integrate(SHOT, REQ_3KM)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        _pass("integrate 3 km — {} rows  peak~{} B".format(len(rows_3km), peak))
except Exception as ex:
    _fail("RAM integrate 3 km", ex)

print("\n=== done ===")
if _failures:
    print("{} test(s) FAILED".format(_failures))
    sys.exit(_failures)
