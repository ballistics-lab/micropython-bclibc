# ruff: noqa

"""
tiny_bclibc performance benchmark.
Run with:
    micropython tiny_bclibc_bench.py
"""

import sys
import time
import math
import gc

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.append(_HERE)

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7

# ── Test configuration ──────────────────────────────────────────────────────
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

# Request for 1 km trajectory with fine steps
REQUEST_1KM = Request(
    range_limit_ft=1000.0 * 3.28084,  # 1 km in feet
    range_step_ft=10.0 * 3.28084,  # 10 m steps
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

# Request for 3 km trajectory with coarse steps
REQUEST_3KM = Request(
    range_limit_ft=3000.0 * 3.28084,  # 3 km in feet
    range_step_ft=100.0 * 3.28084,  # 100 m steps
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

# ── Benchmark functions ──────────────────────────────────────────────────────


def bench_integrate(req, iterations=10):
    """Benchmark integrate() function."""
    times = []
    rows_count = 0

    for _ in range(iterations):
        gc.collect()
        start = time.ticks_us()
        rows, reason = bc.integrate(SHOT, req)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))
        rows_count = len(rows)

    avg_us = sum(times) / len(times)
    avg_ms = avg_us / 1000.0

    return {
        "avg_us": avg_us,
        "avg_ms": avg_ms,
        "min_us": min(times),
        "max_us": max(times),
        "iterations": iterations,
        "rows": rows_count,
        "reason": reason,
    }


def bench_integrate_at(iterations=100):
    """Benchmark integrate_at() function."""
    targets = [100.0, 500.0, 1000.0, 1500.0, 2000.0]  # feet

    times = []

    for _ in range(iterations):
        for target in targets:
            gc.collect()
            start = time.ticks_us()
            raw, full = bc.integrate_at(SHOT, bc.INTERP_POS_X, target)
            end = time.ticks_us()
            times.append(time.ticks_diff(end, start))

    avg_us = sum(times) / len(times)
    avg_ms = avg_us / 1000.0

    return {
        "avg_us": avg_us,
        "avg_ms": avg_ms,
        "min_us": min(times),
        "max_us": max(times),
        "iterations": iterations * len(targets),
        "calls_per_sec": 1.0 / (avg_us / 1_000_000) if avg_us > 0 else 0,
    }


def bench_find_zero_angle(iterations=50):
    """Benchmark find_zero_angle() function."""
    zero_dist_ft = 300.0 * 3.28084  # 300 m

    times = []
    results = []

    for _ in range(iterations):
        gc.collect()
        start = time.ticks_us()
        elev = bc.find_zero_angle(SHOT, zero_dist_ft)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))
        results.append(elev)

    avg_us = sum(times) / len(times)
    avg_ms = avg_us / 1000.0

    return {
        "avg_us": avg_us,
        "avg_ms": avg_ms,
        "min_us": min(times),
        "max_us": max(times),
        "iterations": iterations,
        "elev_rad_avg": sum(results) / len(results),
    }


def bench_find_apex(iterations=50):
    """Benchmark find_apex() function."""
    zero_dist_ft = 300.0 * 3.28084
    elev = bc.find_zero_angle(SHOT, zero_dist_ft)

    zeroed = Shot(
        bc=0.310,
        weight_grain=168.0,
        diameter_inch=0.308,
        length_inch=1.2,
        muzzle_velocity_fps=2750.0,
        sight_height_ft=0.125,
        twist_inch=11.0,
        barrel_elevation_rad=elev,
        drag_type=DRAG_G7,
    )

    times = []

    for _ in range(iterations):
        gc.collect()
        start = time.ticks_us()
        apex = bc.find_apex(zeroed)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))

    avg_us = sum(times) / len(times)
    avg_ms = avg_us / 1000.0

    return {
        "avg_us": avg_us,
        "avg_ms": avg_ms,
        "min_us": min(times),
        "max_us": max(times),
        "iterations": iterations,
        "apex_dist_ft": apex[1],
        "apex_height_ft": apex[4],
    }


def bench_memory_usage():
    """Measure memory usage during trajectory calculation."""
    gc.collect()
    mem_before = gc.mem_alloc()
    mem_free_before = gc.mem_free()

    rows, reason = bc.integrate(SHOT, REQUEST_3KM)
    mem_after_integrate = gc.mem_alloc()

    result = len(rows)
    gc.collect()
    mem_after_gc = gc.mem_alloc()
    mem_free_after = gc.mem_free()

    return {
        "mem_before": mem_before,
        "mem_after_integrate": mem_after_integrate,
        "mem_after_gc": mem_after_gc,
        "mem_free_before": mem_free_before,
        "mem_free_after": mem_free_after,
        "rows": result,
        "reason": reason,
        "peak_alloc": mem_after_integrate - mem_before,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("tiny_bclibc Performance Benchmark")
    print("=" * 60)
    print(f"Version: {bc.version()}")
    print()

    print("--- integrate() (1 km, 10 m steps) ---")
    r = bench_integrate(REQUEST_1KM)
    print(f"  Rows: {r['rows']}")
    print(f"  Stop reason: {r['reason']}")
    print(f"  Avg: {r['avg_ms']:.2f} ms  ({r['avg_us']:.0f} µs)")
    print(f"  Min: {r['min_us']} µs  Max: {r['max_us']} µs")
    print(f"  Iterations: {r['iterations']}")

    print()
    print("--- integrate() (3 km, 100 m steps) ---")
    r = bench_integrate(REQUEST_3KM)
    print(f"  Rows: {r['rows']}")
    print(f"  Stop reason: {r['reason']}")
    print(f"  Avg: {r['avg_ms']:.2f} ms  ({r['avg_us']:.0f} µs)")
    print(f"  Min: {r['min_us']} µs  Max: {r['max_us']} µs")
    print(f"  Iterations: {r['iterations']}")

    print()
    print("--- integrate_at() (single point interpolation) ---")
    r = bench_integrate_at()
    print(f"  Avg: {r['avg_ms']:.3f} ms  ({r['avg_us']:.1f} µs)")
    print(f"  Min: {r['min_us']} µs  Max: {r['max_us']} µs")
    print(f"  Calls: {r['iterations']}")
    print(f"  ~{r['calls_per_sec']:.0f} calls/sec")

    print()
    print("--- find_zero_angle() (300 m zero) ---")
    r = bench_find_zero_angle()
    print(f"  Avg: {r['avg_ms']:.3f} ms  ({r['avg_us']:.1f} µs)")
    print(f"  Min: {r['min_us']} µs  Max: {r['max_us']} µs")
    print(f"  Elevation avg: {math.degrees(r['elev_rad_avg']):.4f}°")
    print(f"  Iterations: {r['iterations']}")

    print()
    print("--- find_apex() ---")
    r = bench_find_apex()
    print(f"  Avg: {r['avg_ms']:.3f} ms  ({r['avg_us']:.1f} µs)")
    print(f"  Min: {r['min_us']} µs  Max: {r['max_us']} µs")
    print(f"  Apex: {r['apex_dist_ft']:.1f} ft, {r['apex_height_ft']:.1f} ft")
    print(f"  Iterations: {r['iterations']}")

    print()
    print("--- Memory usage (3 km trajectory) ---")
    r = bench_memory_usage()
    print(f"  Before: {r['mem_before']:,} B")
    print(f"  After integrate: {r['mem_after_integrate']:,} B")
    print(f"  After GC: {r['mem_after_gc']:,} B")
    print(f"  Peak allocation: {r['peak_alloc']:,} B")
    print(f"  Rows: {r['rows']}")
    print(f"  Free memory: {r['mem_free_before']:,} B → {r['mem_free_after']:,} B")

    print()
    print("=" * 60)
    print("Benchmark Summary")
    print("=" * 60)
    r1km = bench_integrate(REQUEST_1KM)
    rat   = bench_integrate_at()
    rzero = bench_find_zero_angle()
    print(f"  Trajectory (1 km, 10 m steps): {1e6 / r1km['avg_us']:.1f} shots/sec")
    print(f"  Interpolation: {rat['calls_per_sec']:.1f} calls/sec")
    print(f"  Zero finding: {1e6 / rzero['avg_us']:.1f} calls/sec")
    print("=" * 60)
    print("Benchmark complete.")
