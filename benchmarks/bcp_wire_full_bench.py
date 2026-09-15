# ruff: noqa

"""
Host-side wire port of `tests/tiny_bclibc_bench.py` -- drives (as much of)
the exact same benchmark battery (same shot, same requests, same
targets/iteration counts where the wire round trip makes that practical)
over a real BCP CDC1 connection instead of a local Python call on-device,
for a direct wire-vs-local comparison against `benchmarks/benches.md`'s
already-published local-only numbers. Grew out of the investigation in
BACKLOG.md Epic 5's "Real-time feasibility" writeup -- read that first for
the story (why command choice barely matters, why query *distance* is the
real cost driver, and why a naive per-point loop is ~5x slower than one
streamed multi-point request).

Not every local benchmark has a wire equivalent:
  - `integrate()`       -> BCP `INTEGRATE` by default (same underlying
                            computation, full-precision native rows -- matches
                            `tiny_bclibc.integrate()`'s own row shape most
                            closely), or `INTEGRATE_FAST` (thinner 16 B rows)
                            with the `--fast` flag, to compare row-size
                            effects on wire time directly.
  - `integrate_at()`     -> BCP `INTEGRATE_AT`, same 5 targets (100-2000 ft).
  - `find_zero_angle()`  -> **no dedicated wire command** (PROTOCOL.md/
                            BACKLOG.md Epic 8: the zero solve is internal,
                            triggered automatically by `LOAD_PROFILE`/
                            `LOAD_CONDITIONS`, never separately callable) --
                            timed via repeated `LOAD_PROFILE` calls instead,
                            the closest a wire client can get; this measures
                            "reload a profile with a new zero" more than
                            "resolve a zero in isolation."
  - `find_apex()`        -> no BCP wire command at all -- not benchmarked.
  - memory usage         -> a device-local metric; not meaningful from a
                            host-side wire client -- not benchmarked.

Usage:
    python3 benchmarks/bcp_wire_full_bench.py /dev/ttyACM1 [--fast]
"""

import math
import struct
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from bcp_wire_bench import build_frame, FrameReader, STATUS_OK, STATUS_MORE

import serial

CMD_LOAD_PROFILE = 1
CMD_INTEGRATE = 4
CMD_INTEGRATE_FAST = 5
CMD_INTEGRATE_AT = 6
DRAG_G7 = 1
TRAJ_FLAG_RANGE = 8
KEY_POS_X = 2
FT_PER_M = 3.28084


def pack_profile(zero_ft):
    # Same shot as tests/tiny_bclibc_bench.py's SHOT.
    return struct.pack(
        "<8fBBH",
        0.310, 168.0, 0.308, 1.2, 2750.0, 0.125, 11.0,
        zero_ft, DRAG_G7, 0, 0,
    )


def pack_integrate_req(range_limit_ft, range_step_ft, time_step, filter_flags):
    return struct.pack("<3fi", range_limit_ft, range_step_ft, time_step, filter_flags)


def pack_integrate_at(key, target):
    return struct.pack("<B", key) + b"\x00\x00\x00" + struct.pack("<f", target)


def bench_integrate(ser, reader, range_limit_ft, range_step_ft, iterations=10, cmd=CMD_INTEGRATE):
    times = []
    total = reason = 0
    for _ in range(iterations):
        t0 = time.perf_counter()
        ser.write(build_frame(cmd, 1, 0, pack_integrate_req(range_limit_ft, range_step_ft, 0.0, TRAJ_FLAG_RANGE)))
        while True:
            type_, seq, status, payload = reader.next_frame(time.time() + 10)
            if type_ != (cmd | 0x80):
                continue
            if status == STATUS_MORE:
                continue
            assert status == STATUS_OK, (status, payload)
            total, reason = struct.unpack_from("<Ii", payload, 0)
            break
        times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times)
    return dict(avg_ms=avg * 1000, min_ms=min(times) * 1000, max_ms=max(times) * 1000, rows=total, reason=reason, iterations=iterations)


def bench_integrate_at(ser, reader, targets, iterations=20):
    times = []
    for _ in range(iterations):
        for target in targets:
            t0 = time.perf_counter()
            ser.write(build_frame(CMD_INTEGRATE_AT, 1, 0, pack_integrate_at(KEY_POS_X, target)))
            type_, seq, status, payload = reader.next_frame(time.time() + 5)
            assert status == STATUS_OK, (status, payload)
            times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times)
    return dict(
        avg_ms=avg * 1000,
        min_ms=min(times) * 1000,
        max_ms=max(times) * 1000,
        iterations=len(times),
        calls_per_sec=1.0 / avg,
    )


def bench_load_profile_zero(ser, reader, zero_ft, iterations=20):
    times = []
    elevs = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        ser.write(build_frame(CMD_LOAD_PROFILE, 1, 0, pack_profile(zero_ft)))
        type_, seq, status, payload = reader.next_frame(time.time() + 5)
        assert status == STATUS_OK, (status, payload)
        elevs.append(struct.unpack("<f", payload)[0])
        times.append(time.perf_counter() - t0)
    avg = sum(times) / len(times)
    return dict(
        avg_ms=avg * 1000,
        min_ms=min(times) * 1000,
        max_ms=max(times) * 1000,
        iterations=iterations,
        elev_rad_avg=sum(elevs) / len(elevs),
    )


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM1"
    fast = "--fast" in sys.argv[2:]
    cmd = CMD_INTEGRATE_FAST if fast else CMD_INTEGRATE
    ser = serial.Serial(port, 115200, timeout=0.2)
    time.sleep(0.3)
    reader = FrameReader(ser)

    print("=" * 60)
    print(f"BCP wire benchmark (mirrors tests/tiny_bclibc_bench.py, over real CDC1, {'INTEGRATE_FAST' if fast else 'INTEGRATE'})")
    print("=" * 60)

    # Not timed -- INTEGRATE/INTEGRATE_AT need a cached profile first
    # (ERR_NOT_LOADED otherwise); 300 m zero, matching bench_find_zero_angle's
    # own zero distance below.
    ser.write(build_frame(CMD_LOAD_PROFILE, 0, 0, pack_profile(300.0 * FT_PER_M)))
    type_, seq, status, payload = reader.next_frame(time.time() + 5)
    assert status == STATUS_OK, (status, payload)

    label = "INTEGRATE_FAST" if fast else "INTEGRATE"
    print(f"\n--- {label} (1 km, 10 m steps) over CDC1 ---")
    r = bench_integrate(ser, reader, 1000.0 * FT_PER_M, 10.0 * FT_PER_M, cmd=cmd)
    print(f"  Rows: {r['rows']}  Stop reason: {r['reason']}")
    print(f"  Avg: {r['avg_ms']:.2f} ms  Min: {r['min_ms']:.2f} ms  Max: {r['max_ms']:.2f} ms")
    print(f"  Iterations: {r['iterations']}")

    print(f"\n--- {label} (3 km, 100 m steps) over CDC1 ---")
    r = bench_integrate(ser, reader, 3000.0 * FT_PER_M, 100.0 * FT_PER_M, cmd=cmd)
    print(f"  Rows: {r['rows']}  Stop reason: {r['reason']}")
    print(f"  Avg: {r['avg_ms']:.2f} ms  Min: {r['min_ms']:.2f} ms  Max: {r['max_ms']:.2f} ms")
    print(f"  Iterations: {r['iterations']}")

    print("\n--- INTEGRATE_AT (single point interpolation, 100-2000 ft) over CDC1 ---")
    r = bench_integrate_at(ser, reader, [100.0, 500.0, 1000.0, 1500.0, 2000.0])
    print(f"  Avg: {r['avg_ms']:.3f} ms  Min: {r['min_ms']:.3f} ms  Max: {r['max_ms']:.3f} ms")
    print(f"  Calls: {r['iterations']}")
    print(f"  ~{r['calls_per_sec']:.0f} calls/sec")

    print("\n--- LOAD_PROFILE zero-solve (300 m zero) over CDC1 [no dedicated wire cmd, see docstring] ---")
    r = bench_load_profile_zero(ser, reader, 300.0 * FT_PER_M)
    print(f"  Avg: {r['avg_ms']:.3f} ms  Min: {r['min_ms']:.3f} ms  Max: {r['max_ms']:.3f} ms")
    print(f"  Elevation avg: {math.degrees(r['elev_rad_avg']):.4f}°")
    print(f"  Iterations: {r['iterations']}")

    print()
    print("=" * 60)
    print("(find_apex() and on-device memory usage have no BCP wire equivalent -- not benchmarked)")
    print("=" * 60)


if __name__ == "__main__":
    main()
