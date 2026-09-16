"""A/B benchmark + step-count harness used to produce the numbers in README.md.

UNWIRED REFERENCE SCRIPT -- not part of micropython-bclibc's build or test suite.
Preserved so the Cash-Karp prototype's speed/step-count numbers can be
re-verified without rebuilding the measurement harness from scratch.

Mirrors py-ballisticcalc's scripts/benchmark.py Trajectory (2000m/100m step, G7)
and Zero (zero angle at 2000m) cases exactly, but additionally:
  - accepts an engine config dict (so cStepMultiplier / Cash-Karp's compile-time
    rtol can be swept without editing py-ballisticcalc itself), and
  - reads tiny_bclibc_cashkarp_get_stats() via ctypes after one fresh trajectory
    call, to report accepted/rejected adaptive step counts (0/0 for a plain RK4
    .so that doesn't export that symbol -- see the try/except below).

Prerequisites (none of this lives in micropython-bclibc; it's the py-ballisticcalc
sibling checkout's own real toolchain):
  1. A local checkout of py-ballisticcalc with its bclibc submodule initialized:
       git submodule update --init py_ballisticcalc.exts/py_ballisticcalc_exts/external/bclibc
  2. tiny_bclibc_cashkarp.h spliced into that submodule's
       tiny_bclibc/include/tiny_bclibc/engine.h
     per the instructions at the top of that file (never commit/push this --
     it's scratch work against a real repo you don't own).
  3. Built .so variants via that submodule's own CMakeLists.txt, e.g.:
       cmake -B /tmp/ck_single -S <submodule>/tiny_bclibc \\
         -DTINY_BCLIBC_BUILD_SHARED=ON -DTINY_BCLIBC_SINGLE_PRECISION=ON \\
         -DCMAKE_BUILD_TYPE=Release \\
         -DCMAKE_C_FLAGS="-DTINY_BCLIBC_USE_CASHKARP -DTINY_BCLIBC_CASHKARP_PERSTAGE_ATMO -DTINY_BCLIBC_CASHKARP_RTOL=1e-6f"
       cmake --build /tmp/ck_single
     (build a plain RK4 .so the same way but omitting the three -D flags, for
     the baseline comparison row.)

Usage:
    PYTHONPATH=<py-ballisticcalc>/examples \\
    PYBALLISTICCALC_TINY_BCLIBC_LIB=<single-precision .so> \\
    PYBALLISTICCALC_TINY_BCLIBC_DP_LIB=<double-precision .so> \\
    uv run --project <py-ballisticcalc> python benchmark_cashkarp.py \\
        "tiny_bclibc:TinyBclibcSingleIntegrationEngine" my_label [cStepMultiplier]

Accuracy (pass/fail) numbers in README.md were produced separately via:
    PYTHONPATH=<py-ballisticcalc>/examples uv run pytest \\
        --engine=tiny_bclibc:TinyBclibcSingleIntegrationEngine   # or ...Double...
run from the py-ballisticcalc repo root with the same PYBALLISTICCALC_TINY_BCLIBC_*
env vars set, against py-ballisticcalc's own real 375-test suite.
"""
import ctypes
import gc
import os
import statistics
import sys
import time

# EDIT THIS to point at your local py-ballisticcalc checkout.
PY_BALLISTICCALC_ROOT = "/home/murphy/pyproj/py-ballisticcalc"

sys.path.insert(0, f"{PY_BALLISTICCALC_ROOT}/examples")
sys.path.insert(0, PY_BALLISTICCALC_ROOT)

from py_ballisticcalc import (
    Calculator, DragModel, TableG7, Ammo, Weapon, Shot, Atmo, TrajFlag,
)
from py_ballisticcalc.unit import Distance, Velocity, Weight, Angular

# Same fixed scenario as py-ballisticcalc's scripts/benchmark.py CASES.
_WEAPON_BASE = dict(sight_height=Distance.Centimeter(4), twist=Distance.Centimeter(30))
_DRAG_MODEL = DragModel(0.22, TableG7, weight=Weight.Gram(10), diameter=Distance.Centimeter(7.62), length=Distance.Centimeter(3.0))
_AMMO = Ammo(dm=_DRAG_MODEL, mv=Velocity.MPS(800))
_ATMO = Atmo.icao()
_RANGE = Distance.Meter(2000)
_RANGE_STEP = Distance.Meter(100)


def _build_shot(for_zero: bool) -> Shot:
    if for_zero:
        weapon = Weapon(**_WEAPON_BASE)
    else:
        weapon = Weapon(**_WEAPON_BASE, zero_elevation=Angular.Mil(60.0))
    return Shot(weapon=weapon, ammo=_AMMO, atmo=_ATMO)


def bench(engine: str, repeats: int, warmup: int, config, kind: str):
    calc = Calculator(engine=engine, config=config)
    shot = _build_shot(kind == "zero")
    for _ in range(warmup):
        if kind == "trajectory":
            calc.fire(shot=shot, trajectory_range=_RANGE, trajectory_step=_RANGE_STEP, flags=TrajFlag.ALL)
        else:
            calc.set_weapon_zero(shot, _RANGE)

    gc.collect()
    was_enabled = gc.isenabled()
    gc.disable()
    timings = []
    try:
        for _ in range(repeats):
            shot_local = _build_shot(kind == "zero")
            start = time.perf_counter()
            if kind == "trajectory":
                calc.fire(shot=shot_local, trajectory_range=_RANGE, trajectory_step=_RANGE_STEP, flags=TrajFlag.ALL)
            else:
                calc.set_weapon_zero(shot_local, _RANGE)
            end = time.perf_counter()
            timings.append((end - start) * 1000.0)
    finally:
        if was_enabled:
            gc.enable()
    mean_ms = statistics.fmean(timings)
    stdev_ms = statistics.pstdev(timings) if len(timings) > 1 else 0.0
    return mean_ms, stdev_ms, min(timings), max(timings)


def step_stats(lib_path: str):
    """Read tiny_bclibc_cashkarp_get_stats() after one fresh trajectory call.

    Returns None (not (0, 0)) for a plain RK4 .so that doesn't export the
    symbol at all -- distinguishes "not a Cash-Karp build" from "0 steps".
    """
    lib = ctypes.CDLL(lib_path)
    try:
        lib.tiny_bclibc_cashkarp_get_stats.argtypes = (
            ctypes.POINTER(ctypes.c_int32), ctypes.POINTER(ctypes.c_int32))
        lib.tiny_bclibc_cashkarp_get_stats.restype = None
    except AttributeError:
        return None
    acc = ctypes.c_int32(0)
    rej = ctypes.c_int32(0)
    lib.tiny_bclibc_cashkarp_get_stats(ctypes.byref(acc), ctypes.byref(rej))
    return acc.value, rej.value


if __name__ == "__main__":
    engine = sys.argv[1]
    label = sys.argv[2]
    step_mult = float(sys.argv[3]) if len(sys.argv) > 3 else None
    config = {"cStepMultiplier": step_mult} if step_mult is not None else None

    for kind, name in (("trajectory", "Trajectory"), ("zero", "Zero")):
        mean_ms, stdev_ms, min_ms, max_ms = bench(engine, repeats=200, warmup=20, config=config, kind=kind)
        print(f"{label},{name},mean_ms={mean_ms:.3f},stdev={stdev_ms:.3f},min={min_ms:.3f},max={max_ms:.3f}")

    sp_lib = os.environ.get("PYBALLISTICCALC_TINY_BCLIBC_LIB")
    dp_lib = os.environ.get("PYBALLISTICCALC_TINY_BCLIBC_DP_LIB")
    calc = Calculator(engine=engine, config=config)
    shot = _build_shot(False)
    calc.fire(shot=shot, trajectory_range=_RANGE, trajectory_step=_RANGE_STEP, flags=TrajFlag.ALL)
    for tag, lib_path in (("sp", sp_lib), ("dp", dp_lib)):
        if lib_path:
            st = step_stats(lib_path)
            if st:
                print(f"{label},steps[{tag}],accepted={st[0]},rejected={st[1]}")
