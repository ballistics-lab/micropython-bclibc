# ruff: noqa
"""
tiny_bclibc 2-core throughput benchmark — RP2040 / any MicroPython with _thread.

Compares:
  single  — all calls on core0 serially
  2-core  — core0 and core1 each get half the calls, running in parallel

Each core uses its own Shot + Request (own _holder + _traj buffers).

Run on RP2040:
    import tiny_bclibc_natmod_bench_2core
or:
    exec(open("examples/tiny_bclibc_natmod_bench_2core.py").read())
"""

import sys
import _thread
import time
import gc

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.insert(0, _HERE + "/..")
import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7

# ── Shot / Request factories ───────────────────────────────────────────────────
def _make_shot():
    return Shot(
        bc=0.310, weight_grain=168.0, diameter_inch=0.308, length_inch=1.2,
        muzzle_velocity_fps=2750.0, sight_height_ft=0.125, twist_inch=11.0,
        drag_type=DRAG_G7,
    )

def _make_req_1km():
    return Request(range_limit_ft=1000.0 * 3.28084, range_step_ft=10.0 * 3.28084,
                   filter_flags=bc.TRAJ_FLAG_RANGE)

def _make_req_zero():
    return Request(range_limit_ft=1500.0, range_step_ft=300.0,
                   filter_flags=bc.TRAJ_FLAG_RANGE)

# ── Benchmark helpers ──────────────────────────────────────────────────────────
_lock   = _thread.allocate_lock()
_worker_done = False
_worker_us   = 0

def _core1_bench(shot, req, n, fn):
    global _worker_done, _worker_us
    t0 = time.ticks_us()
    for _ in range(n):
        fn(shot, req)
    _worker_us = time.ticks_diff(time.ticks_us(), t0)
    with _lock:
        _worker_done = True

def _wait_worker():
    global _worker_done
    deadline = time.ticks_add(time.ticks_ms(), 30000)
    while not _worker_done:
        if time.ticks_diff(deadline, time.ticks_ms()) < 0:
            print("  ERROR: core1 timeout")
            return False
        time.sleep_ms(1)
    _worker_done = False
    return True

def _bench_single(shot, req, n, fn, label):
    gc.collect()
    times = []
    for _ in range(n):
        t0 = time.ticks_us()
        fn(shot, req)
        times.append(time.ticks_diff(time.ticks_us(), t0))
    us = sum(times)
    print("  single  {:4d} calls  {:6.1f} us/call  min={} max={}  — {}".format(
        n, us / n, min(times), max(times), label))
    return us

def _bench_2core(shot0, req0, shot1, req1, n, fn, label):
    global _worker_done
    _worker_done = False
    gc.collect()

    _thread.start_new_thread(_core1_bench, (shot1, req1, n, fn))

    t0 = time.ticks_us()
    for _ in range(n):
        fn(shot0, req0)
    core0_us = time.ticks_diff(time.ticks_us(), t0)

    if not _wait_worker():
        return None

    wall_us  = max(core0_us, _worker_us)
    total_n  = n * 2
    print("  2-core  {:4d} calls  {:6d} us wall   {:5.1f} us/call  core0={} core1={}  — {}".format(
        total_n, wall_us, wall_us / total_n, core0_us, _worker_us, label))
    return wall_us

def _speedup(single_us, twocore_us, n):
    if twocore_us and twocore_us > 0:
        # single did n calls, 2core did 2n calls in ~same wall time
        eff_single = single_us / n        # us per call single
        eff_2core  = twocore_us / (n * 2) # us per call 2-core
        print("  speedup  {:.2f}x  (throughput: {:.0f} vs {:.0f} calls/s)".format(
            eff_single / eff_2core,
            1e6 / eff_single,
            1e6 / eff_2core))

# ── Main ──────────────────────────────────────────────────────────────────────
print("=" * 60)
print("tiny_bclibc 2-core throughput benchmark")
print("=" * 60)
print("version:", bc.version())
print()

# ── integrate (1 km, 10 m steps) ──────────────────────────────────────────────
print("--- integrate() 1 km / 10 m steps ---")
N_INT = 10
shot_s  = _make_shot();  req_s  = _make_req_1km()
shot_c0 = _make_shot();  req_c0 = _make_req_1km()
shot_c1 = _make_shot();  req_c1 = _make_req_1km()

fn_int = lambda s, r: bc.integrate(s, r)

s_us = _bench_single(shot_s,  req_s,  N_INT, fn_int, "integrate")
t_us = _bench_2core(shot_c0, req_c0, shot_c1, req_c1, N_INT, fn_int, "integrate")
_speedup(s_us, t_us, N_INT)
print()

# ── find_zero_angle ────────────────────────────────────────────────────────────
print("--- find_zero_angle() 300 m ---")
N_ZERO = 20
ZERO_FT = 300.0 * 3.28084
shot_s  = _make_shot();  req_s  = _make_req_zero()
shot_c0 = _make_shot();  req_c0 = _make_req_zero()
shot_c1 = _make_shot();  req_c1 = _make_req_zero()

fn_zero = lambda s, r: bc.find_zero_angle(s, ZERO_FT)

s_us = _bench_single(shot_s,  req_s,  N_ZERO, fn_zero, "find_zero_angle")
t_us = _bench_2core(shot_c0, req_c0, shot_c1, req_c1, N_ZERO, fn_zero, "find_zero_angle")
_speedup(s_us, t_us, N_ZERO)
print()

# ── integrate_stream (1 km, 10 m steps) ───────────────────────────────────────
print("--- integrate_stream() 1 km / 10 m steps ---")
N_STR = 10
shot_s  = _make_shot();  req_s  = _make_req_1km()
shot_c0 = _make_shot();  req_c0 = _make_req_1km()
shot_c1 = _make_shot();  req_c1 = _make_req_1km()

fn_stream = lambda s, r: bc.integrate_stream(s, r, lambda _: None)

s_us = _bench_single(shot_s,  req_s,  N_STR, fn_stream, "integrate_stream")
t_us = _bench_2core(shot_c0, req_c0, shot_c1, req_c1, N_STR, fn_stream, "integrate_stream")
_speedup(s_us, t_us, N_STR)
print()

# ── Memory ────────────────────────────────────────────────────────────────────
print("--- memory per Shot + Request ---")
gc.collect()
b0 = gc.mem_alloc()
s = _make_shot(); r = _make_req_1km()
b1 = gc.mem_alloc()
print("  Shot+Request  {} B  (pre-allocated, reused across all calls)".format(b1 - b0))
del s, r; gc.collect()

print("=" * 60)
print("Done!")
