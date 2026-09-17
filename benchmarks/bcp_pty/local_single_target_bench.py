"""BCP local single-target solve benchmark for RK4/RK45 firmware comparison.

Runs directly on the MicroPython board with BCLIBC_BCP enabled.  It measures
BCP dispatch plus the solver, but excludes COBS framing, USB/UART transport,
and host I/O.  `range_limit == range_step == target` makes INTEGRATE_FAST
return the initial and requested target rows; this is the same request shape
as the wire single-target benchmark.

Run: mpremote connect /dev/ttyACM0 run benchmarks/bcp_pty/local_single_target_bench.py
"""

import struct
import time

import _tiny_bclibc as bc


FT_PER_M = 3.28084
TARGETS_M = (300, 500, 1000, 2000, 3000)
ITERATIONS = 100


def pack_profile():
    return struct.pack(
        "<8fBBH",
        0.310, 168.0, 0.308, 1.2, 2750.0, 0.125, 11.0,
        100.0 * FT_PER_M,  # zero distance
        1,  # G7
        0,
        0,
    )


def pack_single_target(target_m):
    target_ft = target_m * FT_PER_M
    return struct.pack("<3fi", target_ft, target_ft, 0.0, 8)  # TRAJ_FLAG_RANGE


def emit(status, payload):
    # Exercise BCP's batching path without accumulating Python-side output.
    pass


status, response = bc.dispatch(bc.CMD_LOAD_PROFILE, 0, pack_profile())
assert status == bc.STATUS_OK, (status, response)

print("target,local BCP avg ms,solve req/s")
for target_m in TARGETS_M:
    samples_us = []
    payload = pack_single_target(target_m)
    for sequence in range(ITERATIONS):
        t0 = time.ticks_us()
        status, response = bc.dispatch(
            bc.CMD_INTEGRATE_FAST, sequence, payload, emit
        )
        elapsed_us = time.ticks_diff(time.ticks_us(), t0)
        assert status == bc.STATUS_OK, (status, response)
        samples_us.append(elapsed_us)
    avg_us = sum(samples_us) / len(samples_us)
    print("{},{:.3f},{:.1f}".format(
        target_m, avg_us / 1000, 1000000 / avg_us
    ))
