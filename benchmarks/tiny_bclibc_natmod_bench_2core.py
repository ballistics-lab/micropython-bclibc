# ruff: noqa

"""
tiny_bclibc performance benchmark on Core1 with Heartbeat on Core0.
Run with:
    micropython test_bclibc_bench_dualcore.py
"""

import sys
import time
import math
import gc
import _thread
from machine import Pin

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.append(_HERE)

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7

# ── Global variables for inter-core communication ──────────────────────────
benchmark_result = None
benchmark_done = False
benchmark_error = None

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

REQUEST_1KM = Request(
    range_limit_ft=1000.0 * 3.28084,
    range_step_ft=10.0 * 3.28084,
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

REQUEST_3KM = Request(
    range_limit_ft=3000.0 * 3.28084,
    range_step_ft=100.0 * 3.28084,
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

# ── Heartbeat on Core0 ──────────────────────────────────────────────────────


def heartbeat():
    """Simple LED heartbeat on Core0."""
    led = Pin(25, Pin.OUT)  # Built-in LED on RP2040
    state = False
    blink_count = 0

    print("[Core0] Heartbeat started (LED on GPIO25)")

    while not benchmark_done:
        state = not state
        led.value(state)
        blink_count += 1

        # Different patterns to show status
        if not benchmark_result:  # Benchmark running
            time.sleep_ms(100)  # Fast blink - 5Hz
        else:  # Benchmark done
            time.sleep_ms(500)  # Slow blink - 1Hz

        # Print status every 50 blinks
        if blink_count % 50 == 0:
            status = "RUNNING" if not benchmark_result else "DONE"
            print(f"[Core0] Heartbeat: {status} ({blink_count} blinks)")

    # Final pattern - 3 quick blinks
    for _ in range(3):
        led.value(1)
        time.sleep_ms(200)
        led.value(0)
        time.sleep_ms(200)

    print("[Core0] Heartbeat finished")


# ── Benchmark functions (running on Core1) ────────────────────────────────


def bench_integrate(req, iterations=10):
    """Benchmark integrate() function."""
    times = []
    rows_count = 0

    for i in range(iterations):
        gc.collect()
        start = time.ticks_us()
        rows, reason = bc.integrate(SHOT, req)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))
        rows_count = len(rows)

        # Progress indicator (visible in REPL)
        if (i + 1) % 5 == 0:
            print(f"[Core1] integrate() progress: {i + 1}/{iterations}")

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
    total_calls = 0

    for i in range(iterations):
        for target in targets:
            gc.collect()
            start = time.ticks_us()
            raw, full = bc.integrate_at(SHOT, bc.INTERP_POS_X, target)
            end = time.ticks_us()
            times.append(time.ticks_diff(end, start))
            total_calls += 1

        if (i + 1) % 20 == 0:
            print(f"[Core1] integrate_at() progress: {i + 1}/{iterations}")

    avg_us = sum(times) / len(times)
    avg_ms = avg_us / 1000.0

    return {
        "avg_us": avg_us,
        "avg_ms": avg_ms,
        "min_us": min(times),
        "max_us": max(times),
        "iterations": total_calls,
        "calls_per_sec": 1.0 / (avg_us / 1_000_000) if avg_us > 0 else 0,
    }


def bench_find_zero_angle(iterations=50):
    """Benchmark find_zero_angle() function."""
    zero_dist_ft = 300.0 * 3.28084

    times = []
    results = []

    for i in range(iterations):
        gc.collect()
        start = time.ticks_us()
        elev = bc.find_zero_angle(SHOT, zero_dist_ft)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))
        results.append(elev)

        if (i + 1) % 10 == 0:
            print(f"[Core1] find_zero_angle() progress: {i + 1}/{iterations}")

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

    for i in range(iterations):
        gc.collect()
        start = time.ticks_us()
        apex = bc.find_apex(zeroed)
        end = time.ticks_us()
        times.append(time.ticks_diff(end, start))

        if (i + 1) % 10 == 0:
            print(f"[Core1] find_apex() progress: {i + 1}/{iterations}")

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


def run_benchmarks_on_core1():
    """Main benchmark function - runs on Core1."""
    global benchmark_result, benchmark_done, benchmark_error

    print("\n[Core1] ============================================================")
    print("[Core1] Starting benchmarks on Core1")
    print("[Core1] ============================================================")

    results = {}

    try:
        # 1. integrate() benchmark
        print("\n[Core1] --- integrate() (1 km, 10 m steps) ---")
        results["integrate_1km"] = bench_integrate(REQUEST_1KM, iterations=10)
        print(f"[Core1]   Rows: {results['integrate_1km']['rows']}")
        print(f"[Core1]   Avg: {results['integrate_1km']['avg_ms']:.2f} ms")

        # 2. integrate() 3 km benchmark
        print("\n[Core1] --- integrate() (3 km, 100 m steps) ---")
        results["integrate_3km"] = bench_integrate(REQUEST_3KM, iterations=10)
        print(f"[Core1]   Rows: {results['integrate_3km']['rows']}")
        print(f"[Core1]   Avg: {results['integrate_3km']['avg_ms']:.2f} ms")

        # 3. integrate_at() benchmark
        print("\n[Core1] --- integrate_at() (single point interpolation) ---")
        results["integrate_at"] = bench_integrate_at(iterations=100)
        print(f"[Core1]   Avg: {results['integrate_at']['avg_ms']:.3f} ms")
        print(f"[Core1]   ~{results['integrate_at']['calls_per_sec']:.0f} calls/sec")

        # 4. find_zero_angle() benchmark
        print("\n[Core1] --- find_zero_angle() (300 m zero) ---")
        results["find_zero_angle"] = bench_find_zero_angle(iterations=10)
        print(f"[Core1]   Avg: {results['find_zero_angle']['avg_ms']:.3f} ms")
        print(
            f"[Core1]   Elevation: {math.degrees(results['find_zero_angle']['elev_rad_avg']):.4f}°"
        )

        # 5. find_apex() benchmark
        print("\n[Core1] --- find_apex() ---")
        results["find_apex"] = bench_find_apex(iterations=50)
        print(f"[Core1]   Avg: {results['find_apex']['avg_ms']:.3f} ms")
        print(f"[Core1]   Apex: {results['find_apex']['apex_dist_ft']:.1f} ft")

        # 6. Memory usage
        print("\n[Core1] --- Memory usage (3 km trajectory) ---")
        results["memory"] = bench_memory_usage()
        print(f"[Core1]   Peak allocation: {results['memory']['peak_alloc']:,} B")
        print(
            f"[Core1]   Free memory: {results['memory']['mem_free_before']:,} B → {results['memory']['mem_free_after']:,} B"
        )

        # 7. Summary
        print("\n[Core1] " + "=" * 60)
        print("[Core1] Benchmark Summary")
        print("[Core1] " + "=" * 60)

        integrate_time_ms = results["integrate_1km"]["avg_ms"]
        integrate_at_time_ms = results["integrate_at"]["avg_ms"]
        find_zero_time_ms = results["find_zero_angle"]["avg_ms"]

        print(f"[Core1]   Trajectory (1 km): {1000 / integrate_time_ms:.1f} shots/sec")
        print(f"[Core1]   Interpolation: {1000 / integrate_at_time_ms:.1f} calls/sec")
        print(f"[Core1]   Zero finding: {1000 / find_zero_time_ms:.1f} calls/sec")
        print("[Core1] " + "=" * 60)
        print("[Core1] Benchmarks complete!")

        benchmark_result = results
        benchmark_error = None

    except Exception as e:
        print(f"[Core1] ERROR: {e}")
        import sys

        sys.print_exception(e)
        benchmark_error = str(e)

    finally:
        benchmark_done = True


# ── Main entry point ──────────────────────────────────────────────────────


def main():
    global benchmark_done, benchmark_result

    print("=" * 60)
    print("tiny_bclibc Dual-Core Benchmark")
    print("=" * 60)
    print(f"Version: {bc.version()}")
    print("Running on: RP2040 (dual-core)")
    print()
    print("[Main] Starting Core1 benchmark thread...")
    print("[Main] Core0 will run heartbeat (LED blink)")
    print("[Main] Watch the LED for status:")
    print("  - Fast blink (5Hz): Benchmark running")
    print("  - Slow blink (1Hz): Benchmark done")
    print("  - 3 quick blinks: Finished")
    print()

    # Start benchmark on Core1
    try:
        _thread.start_new_thread(run_benchmarks_on_core1, ())
        print("[Main] Core1 thread started successfully")
    except Exception as e:
        print(f"[Main] Failed to start thread: {e}")
        return

    # Run heartbeat on Core0
    heartbeat()

    # Print final results from Core1
    print("\n" + "=" * 60)
    print("Final Results from Core1")
    print("=" * 60)

    if benchmark_error:
        print(f"ERROR: {benchmark_error}")
    elif benchmark_result:
        print("All benchmarks completed successfully!")
        print(f"Results: {len(benchmark_result)} benchmark categories")

        # Print key metrics
        if "integrate_1km" in benchmark_result:
            r = benchmark_result["integrate_1km"]
            print(f"\n  integrate() 1km: {r['avg_ms']:.2f} ms, {r['rows']} rows")

        if "integrate_at" in benchmark_result:
            r = benchmark_result["integrate_at"]
            print(
                f"  integrate_at(): {r['avg_ms']:.3f} ms, ~{r['calls_per_sec']:.0f} calls/sec"
            )

        if "find_zero_angle" in benchmark_result:
            r = benchmark_result["find_zero_angle"]
            print(
                f"  find_zero_angle(): {r['avg_ms']:.3f} ms, {math.degrees(r['elev_rad_avg']):.4f}°"
            )
    else:
        print("No results received")

    print("=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
