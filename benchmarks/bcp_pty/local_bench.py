# MicroPython (unix, BCLIBC_BCP=1) — pure in-process dispatch() baseline.
# No stream, no COBS/CRC framing, no syscalls: isolates raw engine + dispatch
# C-call time on this same binary/process, for an apples-to-apples comparison
# against the pty-wire run (same host CPU, only the transport/framing differs).
import struct
import time

import _tiny_bclibc as bc

ZERO_FT = 300.0 * 3.28084
DRAG_G7 = 1
ITERATIONS = 200


def pack_profile():
    return struct.pack(
        "<8fBBH",
        0.310, 168.0, 0.308, 1.2, 2750.0, 0.125, 11.0, ZERO_FT,
        DRAG_G7, 0, 0,
    )


def pack_integrate_1km():
    return struct.pack("<3fi", 1000.0 * 3.28084, 10.0 * 3.28084, 0.0, 8)


status, resp = bc.dispatch(bc.CMD_LOAD_PROFILE, 0, pack_profile())
assert status == bc.STATUS_OK, (status, resp)
print("LOAD_PROFILE OK")

rows_holder = []


def emit(status, payload):
    rows_holder.append(payload)


times = []
for i in range(ITERATIONS):
    rows_holder.clear()
    t0 = time.ticks_us()
    status, resp = bc.dispatch(bc.CMD_INTEGRATE_FAST, i + 1, pack_integrate_1km(), emit)
    dt = time.ticks_diff(time.ticks_us(), t0)
    assert status == bc.STATUS_OK, (status, resp)
    times.append(dt)

avg = sum(times) / len(times)
print()
print("local dispatch() (no wire), 1 km/10 m steps, {} iterations:".format(ITERATIONS))
print("  avg={:.3f} ms  min={:.3f} ms  max={:.3f} ms".format(avg / 1000, min(times) / 1000, max(times) / 1000))
