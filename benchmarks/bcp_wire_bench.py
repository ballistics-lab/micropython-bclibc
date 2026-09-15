# ruff: noqa

"""
BCP wire-round-trip benchmark: `INTEGRATE_FAST` over a real USB CDC1
connection to a board running `bclibc_bcp.start(cdc1)` (see BACKLOG.md
Epic 4's "Status at a glance" writeup for how the loop itself is built and
verified). Host-side only -- run with a normal desktop Python 3 + pyserial,
against a real flashed board, not on the device itself.

Same shot/request shape as `benchmarks/tiny_bclibc_natmod_bench_2core.py`'s
`REQUEST_1KM` (G7, bc=0.310/168gr/.308"/2750fps, 1 km/10 m steps), so the
result is directly comparable to `benchmarks/benches.md`'s on-device-only
(no wire) numbers for the same board -- see `benchmarks/README.md`'s own
BCP wire section for the numbers this script produced.

Minimal from-scratch COBS+CRC16/CCITT-FALSE host client: `src/bcp_frame.py`
(the project's own earlier pure-Python reference) was deliberately removed
once the C port (`src/bcp/bcp_frame_mp.h`) landed and PROTOCOL.md settled
(see BACKLOG.md Epic 3's "actually deleted, not just left inert" bullet) --
this file is not that reference coming back, just enough wire codec to
drive a benchmark from a machine that doesn't have `_tiny_bclibc` at all.

Usage:
    1. Flash a board with a BCLIBC_BCP=1 build (see BACKLOG.md's
       "Building/testing, concretely" section) and start the dispatch
       loop, e.g. from the REPL:
           import usb.device
           from usb.device.cdc import CDCInterface
           import bclibc_bcp
           cdc1 = CDCInterface()
           cdc1.init(timeout=0)
           usb.device.get().init(cdc1, builtin_driver=True)
           bclibc_bcp.start(cdc1)
       (this call does not return -- run it via `mpremote ... run` in the
       background, or on a second core/thread once Epic 7 lands)
    2. From the host: `python3 benchmarks/bcp_wire_bench.py /dev/ttyACM1 10`
       (port = the CDC1 device that appeared, not the REPL's CDC0)

A real, hard-learned gotcha this script exists to not repeat: pyserial's
`Serial.read(N)` blocks for the *entire* configured timeout if fewer than
N bytes ever arrive, instead of returning as soon as *some* data is ready
-- asking for a fixed size larger than a short response (e.g. `read(256)`
for a ~130 B frame) silently inflates every measurement by however long
`timeout=` was set to, with nothing to do with the device, USB, or the
protocol at all. `FrameReader.next_frame()` below only ever reads
`ser.in_waiting or 1` bytes at a time for exactly this reason -- fixing
this dropped a real measurement of "RP2350 CDC1 wire vs local" from
~244 ms to ~43 ms with *zero* device-side change.
"""

import struct
import sys
import time

import serial

CRC_POLY = 0x1021


def _crc_table():
    table = []
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            crc = ((crc << 1) ^ CRC_POLY) if (crc & 0x8000) else (crc << 1)
        table.append(crc & 0xFFFF)
    return table


_TABLE = _crc_table()


def crc16(data, crc=0xFFFF):
    for b in data:
        crc = ((crc << 8) ^ _TABLE[((crc >> 8) ^ b) & 0xFF]) & 0xFFFF
    return crc


def cobs_encode(data):
    out = bytearray()
    idx = 0
    while True:
        next_zero = data.find(b"\x00", idx)
        chunk_end = next_zero if next_zero != -1 else len(data)
        chunk = data[idx:chunk_end]
        pos = 0
        while True:
            block = chunk[pos : pos + 254]
            out.append(len(block) + 1)
            out += block
            pos += len(block)
            if pos >= len(chunk):
                break
        idx = chunk_end + 1
        if next_zero == -1:
            break
    return bytes(out)


def cobs_decode(data):
    out = bytearray()
    i = 0
    while i < len(data):
        code = data[i]
        if code == 0:
            raise ValueError("zero in COBS stream")
        i += 1
        block = data[i : i + code - 1]
        out += block
        i += code - 1
        if code < 0xFF and i < len(data):
            out.append(0)
    return bytes(out)


def build_frame(type_, seq, status, payload=b""):
    packet = bytes([type_, seq, status, 0]) + payload
    crc = crc16(packet)
    packet += struct.pack("<H", crc)
    return b"\x00" + cobs_encode(packet) + b"\x00"


def parse_frame(encoded):
    packet = cobs_decode(encoded)
    if len(packet) < 6:
        return None
    body, crc_bytes = packet[:-2], packet[-2:]
    if crc16(body) != struct.unpack("<H", crc_bytes)[0]:
        return None
    return body[0], body[1], body[2], body[4:]


# ── PROTOCOL.md §4 command ids, and this bench's fixed shot/request ────────

CMD_LOAD_PROFILE = 1
CMD_INTEGRATE_FAST = 5
STATUS_OK = 0
STATUS_MORE = 1

_ZERO_FT = 300.0 * 3.28084  # 300 m, matches tests/test_bcp_dispatch_native.py
DRAG_G7 = 1


def pack_profile():
    # Same shot as benchmarks/tiny_bclibc_natmod_bench_2core.py's SHOT.
    return struct.pack(
        "<8fBBH",
        0.310,  # bc
        168.0,  # weight_grain
        0.308,  # diameter_inch
        1.2,  # length_inch
        2750.0,  # muzzle_velocity_fps
        0.125,  # sight_height_ft
        11.0,  # twist_inch
        _ZERO_FT,  # zero_distance_ft
        DRAG_G7,
        0,  # rsvd
        0,  # drag_count (0 -- static G7 table)
    )


def pack_integrate_1km():
    # Same request as benchmarks/tiny_bclibc_natmod_bench_2core.py's
    # REQUEST_1KM: 1 km range, 10 m steps, TRAJ_FLAG_RANGE (=8).
    return struct.pack(
        "<3fi",
        1000.0 * 3.28084,  # range_limit_ft
        10.0 * 3.28084,  # range_step_ft
        0.0,  # time_step (auto)
        8,  # TRAJ_FLAG_RANGE
    )


class FrameReader:
    """Accumulates transport bytes and yields parsed (type, seq, status,
    payload) frames, splitting on 0x00 per PROTOCOL.md §1. See this
    module's own docstring for why `read()` is never called with a fixed
    size larger than what's actually pending."""

    def __init__(self, ser):
        self.ser = ser
        self.buf = bytearray()

    def next_frame(self, deadline):
        while True:
            idx = self.buf.find(b"\x00")
            if idx != -1:
                end = self.buf.find(b"\x00", idx + 1)
                if end != -1:
                    seg = bytes(self.buf[idx + 1 : end])
                    del self.buf[: end + 1]
                    if seg:
                        parsed = parse_frame(seg)
                        if parsed is not None:
                            return parsed
                    continue
            if time.time() > deadline:
                raise TimeoutError("no frame in time")
            chunk = self.ser.read(self.ser.in_waiting or 1)
            if chunk:
                self.buf += chunk


def run_once(ser, reader):
    t0 = time.perf_counter()
    ser.write(build_frame(CMD_INTEGRATE_FAST, 1, 0, pack_integrate_1km()))
    while True:
        type_, seq, status, payload = reader.next_frame(time.time() + 5.0)
        if type_ != (CMD_INTEGRATE_FAST | 0x80):
            continue
        if status == STATUS_OK:
            total, reason = struct.unpack_from("<Ii", payload, 0)
            return (time.perf_counter() - t0), total, reason
        elif status != STATUS_MORE:
            raise RuntimeError(f"unexpected status {status}")


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM1"
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    ser = serial.Serial(port, 115200, timeout=0.2)
    time.sleep(0.3)
    reader = FrameReader(ser)

    ser.write(build_frame(CMD_LOAD_PROFILE, 0, 0, pack_profile()))
    type_, seq, status, payload = reader.next_frame(time.time() + 5.0)
    assert type_ == (CMD_LOAD_PROFILE | 0x80) and status == STATUS_OK, (type_, status, payload)
    print("LOAD_PROFILE OK")

    times = []
    for i in range(iterations):
        dt, total, reason = run_once(ser, reader)
        times.append(dt)
        print(f"  run {i}: {dt * 1000:.2f} ms, rows={total}, reason={reason}")

    avg = sum(times) / len(times)
    print()
    print(f"INTEGRATE_FAST over real CDC1, 1 km/10 m steps, {iterations} iterations:")
    print(f"  avg={avg * 1000:.2f} ms  min={min(times) * 1000:.2f} ms  max={max(times) * 1000:.2f} ms")


if __name__ == "__main__":
    main()
