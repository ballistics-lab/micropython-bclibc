# ruff: noqa
"""On-device (real RP2350/Pico2 hardware, over mpremote) cStepMultiplier sweep.
Same shot/request shape as tests/tiny_bclibc_bench.py's REQUEST_1KM, directly
comparable to benchmarks/benches.md's RP2350 hardware-FPU row (15.99 ms at
step_multiplier=0.5, the current TINY_BCLIBC_Config_default()). See
BACKLOG.md's "RK4 step-size" section (under Epic 2) for the full sweep
results (x64 pytest-suite accuracy check -- against the clean
double-precision baseline, not just single precision -- RP2040 emulator,
and this real RP2350 measurement). cStepMultiplier=1.0 is the
verified-zero-regression value (~1.37x real speedup, 14.92 ms -> 10.91 ms);
2.0 is faster still (~1.67x, 14.92 ms -> 8.93 ms) but introduces one small,
real MACH-crossing-distance regression -- a conscious tradeoff, not a free
win.

Requires the armv7emsp natmod already loaded on the board as `tiny_bclibc`
(see natmod/README or `make ARCH=armv7emsp RP2350=1 dist`).

Run:
    mpremote run benchmarks/step_multiplier_rp2350_bench.py
"""
import time
import gc

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, Config, DRAG_G7

REQUEST_1KM = Request(
    range_limit_ft=1000.0 * 3.28084,
    range_step_ft=10.0 * 3.28084,
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

ITERATIONS = 20

print("=== RP2350 (real hardware) cStepMultiplier sweep ===")
print("Version:", bc.version())

for mult in (0.5, 1.0, 2.0, 4.0):
    shot = Shot(
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
        config=Config(step_multiplier=mult),
    )
    times = []
    rows_n = 0
    reason = None
    for _ in range(ITERATIONS):
        gc.collect()
        t0 = time.ticks_us()
        rows, reason = bc.integrate(shot, REQUEST_1KM)
        t1 = time.ticks_us()
        times.append(time.ticks_diff(t1, t0))
        rows_n = len(rows)
    avg_ms = (sum(times) / len(times)) / 1000.0
    print(
        "multiplier={:4.1f}  avg={:8.3f} ms  min={:8.3f} ms  max={:8.3f} ms  rows={}  reason={}".format(
            mult, avg_ms, min(times) / 1000.0, max(times) / 1000.0, rows_n, reason
        )
    )

print("Done.")
