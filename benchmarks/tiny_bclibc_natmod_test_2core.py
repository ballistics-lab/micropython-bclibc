# ruff: noqa

"""
tiny_bclibc natmod integration test - DUAL CORE VERSION (FIXED).
Runs tests on Core1 with heartbeat on Core0.

Run with:
    micropython test_bclibc_dualcore.py
"""

import sys
import math
import array
import _thread
import gc
import time
from machine import Pin

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.append(_HERE)

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7, DRAG_CUSTOM

# ── Global variables ──────────────────────────────────────────────────────────
test_complete = False
test_results = {}
test_error = None
test_progress = 0
total_tests = 0
tests_run = 0

# ── Custom drag table ────────────────────────────────────────────────────────
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

ZERO_DIST_FT = 300.0 * 3.28084
ZERO_DIST_100M_FT = 100.0 * 3.28084

# ── Heartbeat on Core0 ──────────────────────────────────────────────────────


def heartbeat():
    """LED heartbeat with status indication."""
    led = Pin(25, Pin.OUT)
    state = False
    blink_count = 0
    last_progress = -1
    last_percent = -1

    print("[Core0] ❤️ Heartbeat started")
    print("[Core0] LED patterns:")
    print("  ⚡ Fast blink (5Hz): Tests running")
    print("  🐢 Slow blink (1Hz): Tests complete")
    print("  ✨ 3 quick blinks: Finished\n")

    while not test_complete:
        state = not state
        led.value(state)
        blink_count += 1

        # Show progress
        if total_tests > 0:
            percent = int((test_progress / total_tests) * 100)
            if percent != last_percent:
                last_percent = percent
                print(f"[Core0] Progress: {test_progress}/{total_tests} ({percent}%)")

        if not test_complete:
            time.sleep_ms(100)  # Fast blink
        else:
            time.sleep_ms(500)  # Slow blink

    # Final celebration - 3 quick blinks
    for _ in range(3):
        led.value(1)
        time.sleep_ms(200)
        led.value(0)
        time.sleep_ms(200)

    print(
        f"\n[Core0] ❤️ Heartbeat finished - {test_progress}/{total_tests} tests completed"
    )


# ── Test functions (running on Core1) ─────────────────────────────────────


def _pass(name):
    global test_progress
    test_progress += 1
    print(f"[Core1]   ✅ PASS  {name}")


def _fail(name, msg):
    global test_progress
    test_progress += 1
    print(f"[Core1]   ❌ FAIL  {name} — {msg}")


def run_tests_on_core1():
    """Run all integration tests on Core1."""
    global test_complete, test_results, test_error, total_tests, test_progress

    print("\n[Core1] ============================================================")
    print("[Core1] Starting integration tests on Core1")
    print("[Core1] ============================================================")
    print(f"[Core1] Version: {bc.version()}")

    test_results = {"passed": 0, "failed": 0, "total": 0, "details": []}
    total_tests = 0
    test_progress = 0

    # Count total tests first
    # Scalar helpers: 3 tests
    # integrate builtin: 1 test
    # integrate custom: 1 test
    # find_zero_angle 300m: 1 test
    # find_zero_angle 100m: 1 test
    # find_apex: 1 test
    # integrate_at: 1 test
    # integrate_stream collect: 1 test
    # integrate_stream early stop: 1 test
    # RAM usage: 1 test
    total_tests = 12
    print(f"[Core1] Total tests: {total_tests}")

    try:
        # ── Scalar helpers ──────────────────────────────────────────────────
        print("\n[Core1] --- scalar helpers ---")

        e = bc.calculate_energy(168.0, 2750.0)
        if abs(e - 2820.83) < 1.0:
            _pass("calculate_energy")
            test_results["passed"] += 1
        else:
            _fail("calculate_energy", e)
            test_results["failed"] += 1

        c = bc.get_correction(300.0, -2.0)
        if abs(c) < 0.1:
            _pass("get_correction (at zero)")
            test_results["passed"] += 1
        else:
            _fail("get_correction", c)
            test_results["failed"] += 1

        ogw = bc.calculate_ogw(168.0, 2750.0)
        if 800 < ogw < 1000:
            _pass("calculate_ogw")
            test_results["passed"] += 1
        else:
            _fail("calculate_ogw", ogw)
            test_results["failed"] += 1

        # ── Integration (built-in G7) ──────────────────────────────────────
        print("\n[Core1] --- integrate (builtin G7, 1500 ft, step 300) ---")
        try:
            rows, reason = bc.integrate(SHOT, REQUEST)
            if len(rows) >= 2:
                _pass(f"integrate — {len(rows)} rows, stop reason {reason}")
                test_results["passed"] += 1
                print(
                    f"[Core1]   {'dist_ft':>8}  {'vel_fps':>8}  {'height_ft':>8}  {'mach':>8}"
                )
                for r in rows:
                    print(
                        f"[Core1]   {r[1]:>8.0f}  {r[2]:>8.1f}  {r[4]:>8.3f}  {r[3]:>8.3f}"
                    )
            else:
                _fail("integrate", f"expected >=2 rows, got {len(rows)}")
                test_results["failed"] += 1
        except Exception as ex:
            _fail("integrate", ex)
            test_results["failed"] += 1

        # ── Integration (custom array drag table) ──────────────────────────
        print("\n[Core1] --- integrate (custom array G7, 1500 ft, step 300) ---")
        try:
            rows2, reason2 = bc.integrate(SHOT_CUSTOM, REQUEST)
            if len(rows2) >= 2:
                _pass(f"integrate custom — {len(rows2)} rows, stop reason {reason2}")
                test_results["passed"] += 1
            else:
                _fail("integrate custom", f"expected >=2 rows, got {len(rows2)}")
                test_results["failed"] += 1
        except Exception as ex:
            _fail("integrate custom", ex)
            test_results["failed"] += 1

        # ── find_zero_angle ──────────────────────────────────────────────────
        print("\n[Core1] --- find_zero_angle (300 m zero) ---")
        elev = None
        try:
            elev = bc.find_zero_angle(SHOT, ZERO_DIST_FT)
            _pass(
                f"find_zero_angle elev_rad={elev:.6f}  ({math.degrees(elev):.4f} deg)"
            )
            test_results["passed"] += 1
        except Exception as ex:
            _fail("find_zero_angle", ex)
            test_results["failed"] += 1

        # ── find_zero_angle at 100 m ────────────────────────────────────────
        print("\n[Core1] --- find_zero_angle (100 m zero) ---")
        try:
            elev_100m = bc.find_zero_angle(SHOT, ZERO_DIST_100M_FT)
            elev_100m_mrad = math.degrees(elev_100m) * math.pi / 180 * 1000
            _pass(
                f"find_zero_angle 100m  elev_rad={elev_100m:.6f}  ({math.degrees(elev_100m):.4f} deg  {elev_100m_mrad:.2f} mrad)"
            )
            test_results["passed"] += 1
            if elev_100m <= 0:
                _fail(
                    "find_zero_angle 100m",
                    f"elevation must be positive, got {elev_100m}",
                )
                test_results["failed"] += 1
        except Exception as ex:
            _fail("find_zero_angle 100m", ex)
            test_results["failed"] += 1

        # ── find_apex ────────────────────────────────────────────────────────
        print("\n[Core1] --- find_apex (zeroed shot) ---")
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
            _pass(f"find_apex dist_ft={apex[1]:.1f}  height_ft={apex[4]:.1f}")
            test_results["passed"] += 1
        except Exception as ex:
            _fail("find_apex", ex)
            test_results["failed"] += 1

        # ── integrate_at ─────────────────────────────────────────────────────
        print("\n[Core1] --- integrate_at (POS_X = 1000 ft) ---")
        try:
            raw, full = bc.integrate_at(SHOT, bc.INTERP_POS_X, 1000.0)
            _pass(f"integrate_at dist_ft={full[1]:.1f}  vel_fps={full[2]:.1f}")
            test_results["passed"] += 1
        except Exception as ex:
            _fail("integrate_at", ex)
            test_results["failed"] += 1

        # ── integrate_stream — collect all points ────────────────────────────
        print("\n[Core1] --- integrate_stream (collect all points) ---")
        try:
            stream_rows = []
            total_s, _ = bc.integrate_stream(
                SHOT, REQUEST, lambda row: stream_rows.append(row)
            )
            rows_ref, _ = bc.integrate(SHOT, REQUEST)
            if len(stream_rows) == len(rows_ref):
                _pass(f"integrate_stream — {len(stream_rows)} points (total={total_s})")
                test_results["passed"] += 1
            else:
                _fail(
                    "integrate_stream",
                    f"stream={len(stream_rows)} vs integrate={len(rows_ref)}",
                )
                test_results["failed"] += 1
        except Exception as ex:
            _fail("integrate_stream", ex)
            test_results["failed"] += 1

        # ── integrate_stream — early stop on energy threshold ────────────────
        # Uses 5 km / 300 m steps so energy actually drops below 1000 ft·lbf
        # (~818 ft·lbf at 900 m for G7 BC=0.310 168gr 2750fps).
        print("\n[Core1] --- integrate_stream (stop when energy < 1000 ft·lbf) ---")
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
            if reason_e == 5 and stopped_at[0] is not None:  # TERM_HANDLER_STOP
                _pass(
                    f"integrate_stream stop — energy<1000 at {stopped_at[0]:.0f} ft after {count_e[0]} pts reason={reason_e}"
                )
                test_results["passed"] += 1
            else:
                _fail(
                    "integrate_stream stop",
                    f"reason={reason_e} stopped_at={stopped_at[0]}",
                )
                test_results["failed"] += 1
        except Exception as ex:
            _fail("integrate_stream stop", ex)
            test_results["failed"] += 1

        # ── RAM usage ────────────────────────────────────────────────────────
        print("\n[Core1] --- RAM: integrate 3 km / 100 m step ---")
        try:
            REQ_3KM = Request(
                range_limit_ft=3000.0 * 3.28084,
                range_step_ft=100.0 * 3.28084,
                filter_flags=bc.TRAJ_FLAG_RANGE,
            )
            gc.collect()
            mem_before = gc.mem_alloc()
            rows_3km, _ = bc.integrate(SHOT, REQ_3KM)
            mem_after = gc.mem_alloc()
            gc.collect()
            mem_after_gc = gc.mem_alloc()
            delta = mem_after - mem_before
            delta_gc = mem_after_gc - mem_before
            _pass(
                f"integrate 3 km — {len(rows_3km)} rows  alloc={delta} B  alloc_after_gc={delta_gc} B"
            )
            test_results["passed"] += 1
            print(
                f"[Core1]   mem_before={mem_before} B  mem_peak={mem_after} B  mem_after_gc={mem_after_gc} B"
            )
        except Exception as ex:
            _fail("RAM integrate 3 km", ex)
            test_results["failed"] += 1

        # ── Summary ──────────────────────────────────────────────────────────
        test_results["total"] = test_results["passed"] + test_results["failed"]

        print("\n[Core1] ============================================================")
        print("[Core1] Test Summary")
        print("[Core1] ============================================================")
        print(f"[Core1]   Total tests:  {test_results['total']}")
        print(f"[Core1]   ✅ Passed:    {test_results['passed']}")
        print(f"[Core1]   ❌ Failed:    {test_results['failed']}")
        if test_results["total"] > 0:
            rate = test_results["passed"] / test_results["total"] * 100
            print(f"[Core1]   Success rate: {rate:.1f}%")
        print("[Core1] ============================================================")

        if test_results["failed"] == 0:
            print("[Core1] 🎉 ALL TESTS PASSED!")
        else:
            print(f"[Core1] ⚠️  {test_results['failed']} test(s) failed")

        print("[Core1] Tests complete!")

    except Exception as e:
        print(f"[Core1] ❌ FATAL ERROR: {e}")
        import sys

        sys.print_exception(e)
        test_error = str(e)

    finally:
        test_complete = True


# ── Main entry point ──────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("tiny_bclibc Integration Test - DUAL CORE")
    print("=" * 60)
    print()
    print("Configuration:")
    print(f"  Version: {bc.version()}")
    print("  Platform: RP2040 (dual-core)")
    print("  Zero distance: 300 m")
    print(f"  Custom drag: G7 table ({len(G7_MACH)} points)")
    print()
    print("[Main] Starting Core1 test thread...")
    print("[Main] Core0 will run heartbeat (LED)")

    # Start tests on Core1
    try:
        _thread.start_new_thread(run_tests_on_core1, ())
        print("[Main] ✅ Core1 thread started")
    except Exception as e:
        print(f"[Main] ❌ Failed to start thread: {e}")
        return

    # Run heartbeat on Core0
    heartbeat()

    # Print final results
    print("\n" + "=" * 60)
    print("Final Results")
    print("=" * 60)

    if test_error:
        print(f"❌ ERROR: {test_error}")
    elif test_results:
        print(f"  ✅ Passed: {test_results.get('passed', 0)}")
        print(f"  ❌ Failed: {test_results.get('failed', 0)}")
        print(f"  📊 Total:  {test_results.get('total', 0)}")
        if test_results.get("total", 0) > 0:
            rate = test_results["passed"] / test_results["total"] * 100
            print(f"  📈 Rate:   {rate:.1f}%")
            if rate == 100:
                print("\n🎉 ALL TESTS PASSED!")
            else:
                print(f"\n⚠️  {test_results['failed']} test(s) failed")
    else:
        print("No results received")

    print("=" * 60)
    print("Done!")


if __name__ == "__main__":
    main()
