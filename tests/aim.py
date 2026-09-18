# ruff: noqa
import sys
import time
import gc

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.append(_HERE)
import tiny_bclibc as bc
from tiny_bclibc import Shot, DRAG_G7

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

ZERO_DIST_FT = 100.0 * 3.28084
TARGET_DISTANCES_M = list(range(100, 3100, 100))
TARGET_DISTANCES_FT = [m * 3.28084 for m in TARGET_DISTANCES_M]


def _percentile(times, p):
    s = sorted(times)
    idx = min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1))))
    return s[idx]


def bench_aim_sequence(iterations=20):
    total_batch_times_us = []
    per_point_times_us = []
    last_results = []
    bc.zero(SHOT, ZERO_DIST_FT)
    for _ in range(iterations):
        gc.collect()
        last_results = []
        batch_start = time.ticks_us()
        for dist_ft in TARGET_DISTANCES_FT:
            pt_start = time.ticks_us()
            hold, windage, zero_info = bc.aim(SHOT, dist_ft)
            pt_end = time.ticks_us()

            per_point_times_us.append(time.ticks_diff(pt_end, pt_start))
            last_results.append((dist_ft / 3.28084, hold, windage))

        batch_end = time.ticks_us()
        total_batch_times_us.append(time.ticks_diff(batch_end, batch_start))

    avg_batch_us = sum(total_batch_times_us) / len(total_batch_times_us)
    avg_point_us = sum(per_point_times_us) / len(per_point_times_us)
    return {
        "avg_batch_ms": avg_batch_us / 1000.0,
        "avg_batch_us": avg_batch_us,
        "min_batch_us": min(total_batch_times_us),
        "max_batch_us": max(total_batch_times_us),
        "p95_batch_us": _percentile(total_batch_times_us, 95),
        "avg_point_us": avg_point_us,
        "avg_point_ms": avg_point_us / 1000.0,
        "iterations": iterations,
        "last_results": last_results,
    }


def bench_single_distance_breakdown(iterations=20):
    test_m = [100, 500, 1000, 1500, 2000, 2500, 3000]
    bc.zero(SHOT, ZERO_DIST_FT)
    breakdown = {}
    for m in test_m:
        dist_ft = m * 3.28084
        times = []
        for _ in range(iterations):
            gc.collect()
            st = time.ticks_us()
            bc.aim(SHOT, dist_ft)
            et = time.ticks_us()
            times.append(time.ticks_diff(et, st))
        avg_us = sum(times) / len(times)
        breakdown[m] = avg_us
    return breakdown


if __name__ == "__main__":
    print("=" * 65)
    print("tiny_bclibc aim() Pure Benchmark (100m - 3000m)")
    print("=" * 65)
    print("Version: " + str(bc.version()))
    print("Points: " + str(len(TARGET_DISTANCES_M)) + " distances (100m - 3000m)")
    print("Zero distance: 100 m (set once before loop)")
    print()
    print("--- Running pure aim() for 30 points ---")
    res = bench_aim_sequence(iterations=1)
    print("Full Table (30 points):")
    print(
        "  Avg Total Time:  %.2f ms  (%.0f us)"
        % (res["avg_batch_ms"], res["avg_batch_us"])
    )
    print(
        "  Min: %.0f us  Max: %.0f us  p95: %.0f us"
        % (res["min_batch_us"], res["max_batch_us"], res["p95_batch_us"])
    )
    print("Per-Point Metrics:")
    print(
        "  Avg Time/Point:  %.2f us  (%.3f ms)"
        % (res["avg_point_us"], res["avg_point_ms"])
    )
    if res["avg_point_us"] > 0:
        print(
            "  Throughput:      %.0f aim() calls/sec"
            % (1000000.0 / res["avg_point_us"])
        )
    print("\n--- Detailed breakdown by distance ---")
    print(" Distance | Avg Time (us) | Time (ms)")
    print("-" * 37)
    breakdown = bench_single_distance_breakdown(iterations=1)
    for m in [100, 500, 1000, 1500, 2000, 2500, 3000]:
        us = breakdown[m]
        print(" %4dm   | %12.1f | %8.3f" % (m, us, us / 1000.0))
    print("\n--- Sample output values ---")
    print(" Distance | Hold (rad) | Windage (rad)")
    print("-" * 39)
    for dist_m, hold, windage in res["last_results"]:
        if int(dist_m + 0.5) in (100, 500, 1000, 1500, 2000, 2500, 3000):
            print(" %4dm   | %10.6f | %12.6f" % (int(dist_m + 0.5), hold, windage))
    print("=" * 65)
    print("Benchmark complete.")
