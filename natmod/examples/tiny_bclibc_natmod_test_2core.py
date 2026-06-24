# ruff: noqa
"""
tiny_bclibc 2-core safety test — RP2040 / any MicroPython with _thread.

Thread-safety model:
  - Each Shot owns its _holder buffer (pre-allocated at construction).
  - Two threads using DIFFERENT Shot objects concurrently → safe.
  - Two threads sharing the SAME Shot simultaneously → undefined behaviour.

Run on RP2040:
    import tiny_bclibc_natmod_test_2core
or:
    exec(open("examples/tiny_bclibc_natmod_test_2core.py").read())
"""

import sys
import _thread
import time

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.insert(0, _HERE + "/..")
import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7

# ── Shared results / sync ──────────────────────────────────────────────────────
_lock    = _thread.allocate_lock()
_results = {}
_done    = False

_failures = 0

def _pass(name):
    print("  PASS  " + name)

def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))

# ── Reference shot (single core, used for comparison) ─────────────────────────
REF_SHOT = Shot(
    bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
    muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
    drag_type=DRAG_G7,
)
REF_REQ = Request(range_limit_ft=1500.0, range_step_ft=300.0,
                  filter_flags=bc.TRAJ_FLAG_RANGE)

# ── Worker: runs on core1 ──────────────────────────────────────────────────────
def _core1_worker(shot, req, key):
    rows, reason = bc.integrate(shot, req)
    elev         = bc.find_zero_angle(shot, 300.0 * 3.28084)

    collected = []
    bc.integrate_stream(shot, req, lambda r: collected.append(r[bc.T_DISTANCE]))

    with _lock:
        _results[key] = {
            "rows":      rows,
            "reason":    reason,
            "elev":      elev,
            "stream_n":  len(collected),
        }

# ── Test 1: different Shot objects on each core ────────────────────────────────
print("=== 2-core safety test ===")
print("\n--- test 1: different Shot objects, concurrent integrate ---")

# Core0 shot and core1 shot — independent objects, each has own _holder
shot0 = Shot(
    bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
    muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
    drag_type=DRAG_G7,
)
shot1 = Shot(
    bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
    muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
    drag_type=DRAG_G7,
)
req0 = Request(range_limit_ft=1500.0, range_step_ft=300.0,
               filter_flags=bc.TRAJ_FLAG_RANGE)
req1 = Request(range_limit_ft=1500.0, range_step_ft=300.0,
               filter_flags=bc.TRAJ_FLAG_RANGE)

_results.clear()
_thread.start_new_thread(_core1_worker, (shot1, req1, "core1"))

# Core0 runs in parallel
rows0, reason0 = bc.integrate(shot0, req0)
elev0 = bc.find_zero_angle(shot0, 300.0 * 3.28084)

# Wait for core1
deadline = time.ticks_add(time.ticks_ms(), 5000)
while "core1" not in _results:
    if time.ticks_diff(deadline, time.ticks_ms()) < 0:
        _fail("core1 timeout")
        break
    time.sleep_ms(5)

if "core1" in _results:
    r1 = _results["core1"]
    if len(rows0) == len(r1["rows"]):
        _pass("both cores: same row count ({})".format(len(rows0)))
    else:
        _fail("row count mismatch", "{} vs {}".format(len(rows0), len(r1["rows"])))

    if abs(elev0 - r1["elev"]) < 1e-6:
        _pass("both cores: same find_zero_angle ({:.6f} rad)".format(elev0))
    else:
        _fail("find_zero_angle mismatch", "{} vs {}".format(elev0, r1["elev"]))

    # Verify each row matches reference
    ref_rows, _ = bc.integrate(REF_SHOT, REF_REQ)
    mismatch = 0
    for i, (r0, r1_row, ref) in enumerate(zip(rows0, r1["rows"], ref_rows)):
        for j in range(16):
            if abs(float(r0[j]) - float(ref[j])) > 1e-3:
                mismatch += 1
    if mismatch == 0:
        _pass("core0 rows match reference")
    else:
        _fail("core0 rows differ from reference", "{} fields".format(mismatch))

# ── Test 2: integrate_stream on both cores ─────────────────────────────────────
print("\n--- test 2: integrate_stream concurrent ---")

shot2 = Shot(
    bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
    muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
    drag_type=DRAG_G7,
)
req2 = Request(range_limit_ft=1500.0, range_step_ft=300.0,
               filter_flags=bc.TRAJ_FLAG_RANGE)

_results.clear()
_thread.start_new_thread(_core1_worker, (shot2, req2, "stream"))

collected0 = []
bc.integrate_stream(shot0, req0, lambda r: collected0.append(r[bc.T_DISTANCE]))

deadline = time.ticks_add(time.ticks_ms(), 5000)
while "stream" not in _results:
    if time.ticks_diff(deadline, time.ticks_ms()) < 0:
        _fail("stream core1 timeout")
        break
    time.sleep_ms(5)

if "stream" in _results:
    n1 = _results["stream"]["stream_n"]
    if len(collected0) == n1 == len(rows0):
        _pass("integrate_stream: core0={} core1={} pts".format(len(collected0), n1))
    else:
        _fail("stream count", "core0={} core1={} ref={}".format(
            len(collected0), n1, len(rows0)))

# ── Test 3: sequential reuse of same Shot on both cores ───────────────────────
print("\n--- test 3: sequential reuse (not concurrent) ---")
shared_shot = Shot(
    bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
    muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
    drag_type=DRAG_G7,
)
shared_req = Request(range_limit_ft=1500.0, range_step_ft=300.0,
                     filter_flags=bc.TRAJ_FLAG_RANGE)

# Core0 runs first, then core1 — no overlap
rows_seq0, _ = bc.integrate(shared_shot, shared_req)

_results.clear()
_thread.start_new_thread(_core1_worker, (shared_shot, shared_req, "seq"))

deadline = time.ticks_add(time.ticks_ms(), 5000)
while "seq" not in _results:
    if time.ticks_diff(deadline, time.ticks_ms()) < 0:
        _fail("seq core1 timeout")
        break
    time.sleep_ms(5)

if "seq" in _results:
    rows_seq1 = _results["seq"]["rows"]
    if len(rows_seq0) == len(rows_seq1):
        _pass("sequential reuse same Shot: {} rows each".format(len(rows_seq0)))
    else:
        _fail("sequential reuse", "{} vs {}".format(len(rows_seq0), len(rows_seq1)))

print("\n=== done ===")
if _failures:
    print("{} FAILED".format(_failures))
    sys.exit(_failures)
