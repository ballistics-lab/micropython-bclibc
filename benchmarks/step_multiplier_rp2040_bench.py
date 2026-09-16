# ruff: noqa
"""On-device (RP2040, via the rp2040py emulator -- same one this repo's own CI
uses in .github/workflows/natmod.yml/usermod.yml) cStepMultiplier sweep.
Same shot/request shape as tests/tiny_bclibc_bench.py's REQUEST_1KM, so numbers
are directly comparable to benchmarks/benches.md's RP2040 stock row (353.75 ms
at step_multiplier=0.5, the current TINY_BCLIBC_Config_default()). Few
iterations per multiplier -- the emulator is slower than real silicon (cycle-
accurate, not real-time: this sweep takes tens of seconds of real host time
to report a few hundred ms of simulated device time), though its
step_multiplier=0.5 result (346.77 ms) landed within ~2% of that real 353.75
ms hardware number -- see BACKLOG.md's "RK4 step-size" section (under Epic 2)
for the full sweep results (including real RP2350 hardware numbers) and the
accuracy side (py-ballisticcalc's own pytest suite -- checked against the
clean double-precision baseline, not just single precision, since SP's own
pre-existing failures can mask a real regression). cStepMultiplier=1.0 is
the verified-zero-regression value; 2.0 is faster but a conscious
accuracy/speed tradeoff, not a free win.

Build + run:
    cd natmod && make ARCH=armv6m dist
    cd ..
    echo "placeholder" > _mklittlefs_placeholder.py
    rp2040py mklittlefs -o littlefs.img \
        _mklittlefs_placeholder.py natmod/build/armv6m/tiny_bclibc.mpy
    rp2040py micropython --board pico --image v1.29.0 --littlefs littlefs.img \
        benchmarks/step_multiplier_rp2040_bench.py
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

ITERATIONS = 3

print("=== RP2040 (rp2040py emulator) cStepMultiplier sweep ===")
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
        "multiplier={:4.1f}  avg={:8.2f} ms  min={:8.2f} ms  max={:8.2f} ms  rows={}  reason={}".format(
            mult, avg_ms, min(times) / 1000.0, max(times) / 1000.0, rows_n, reason
        )
    )

print("Done.")
