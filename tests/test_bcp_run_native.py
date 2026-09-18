# ruff: noqa

"""
BCP read/decode/dispatch/write loop (`_tiny_bclibc.run()`) native (C) test --
BCLIBC_BCP=1 usermod builds only. See src/bcp/bcp_dispatch_mp.h's own
`run(stream)` doc comment (BACKLOG.md Epic 1's "Entry point" bullet, Epic
3's "implementation language is C" resolution) for the design this
exercises: a C loop that owns the whole
read -> parse_frame -> dispatch -> build_frame -> write cycle, driven off
any object satisfying MicroPython's stream protocol -- never a per-frame
trip back into Python bytecode.

Run with:
    micropython test_bcp_run_native.py
or from repo root:
    /path/to/micropython test_bcp_run_native.py

No real transport (CDC1/UART) needed: `run()` only requires an
`io.IOBase` with `readinto`/`write`/`ioctl` (the same contract
`usb.device.cdc.CDCInterface` and `machine.UART` satisfy), so this drives
it against MockStream below -- a scripted mock that feeds pre-built
request frames in and captures whatever `run()` writes back. `run()`
never returns under normal operation (it is meant to run forever on its
own core/thread, per Epic 4/7); the test ends it deterministically by
having the mock's `readinto()` raise once its script is exhausted, which
propagates straight out of `run()`'s C frame as a normal Python exception
(see `py/modio.c`'s `iobase_read_write()`: a raised exception from the
Python-level `readinto()`/`write()` call is never swallowed at the C
boundary, only a `None` return -- "would block" -- is).
"""

import io
import struct
import sys

try:
    import _tiny_bclibc as d
except ImportError as ex:
    print("SKIP: _tiny_bclibc not built into this firmware:", ex)
    sys.exit(0)
if not hasattr(d, "run"):
    print("SKIP: _tiny_bclibc built without BCLIBC_BCP=1 (no BCP run())")
    sys.exit(0)

_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


class _MockDone(Exception):
    """Raised by MockStream.readinto() once its script is exhausted --
    the only way to end run()'s otherwise-infinite loop for this test."""


class MockStream(io.IOBase):
    """Scripted stream: readinto() serves `chunks` one at a time (None
    means "would block", matching CDCInterface's own read(-1)/readinto()
    contract on a timeout=0 non-blocking read -- see py/modio.c's
    iobase_read_write()). write() just appends to `written` uninterpreted;
    tests below split it back into frames themselves via 0x00, same as
    PROTOCOL.md's own reference decode loop."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.written = bytearray()

    def readinto(self, buf):
        if not self._chunks:
            raise _MockDone()
        chunk = self._chunks.pop(0)
        if chunk is None:
            return None
        n = len(chunk)
        buf[0:n] = chunk
        return n

    def write(self, buf):
        self.written += bytes(buf)
        return len(buf)

    def ioctl(self, req, arg):
        return 0


def _split_frames(data):
    """Mirrors PROTOCOL.md §1's reference decode loop: split on 0x00,
    dropping empty (00 00) segments -- returns a list of still-COBS-encoded
    segments, one per frame `run()` wrote."""
    segments = []
    buf = bytearray()
    for byte in data:
        if byte == 0:
            if buf:
                segments.append(bytes(buf))
            buf = bytearray()
        else:
            buf.append(byte)
    return segments


def _run_until_done(stream):
    try:
        d.run(stream)
        _fail("run() returned", "expected _MockDone once the script ran out")
    except _MockDone:
        pass
    except Exception as ex:
        _fail("run() raised unexpectedly", ex)


print("=== BCP run() native (_tiny_bclibc) test ===")

# -- one IDENT request, delivered in a single readinto() chunk -----------------
print("\n--- single-chunk IDENT round trip ---")
req = d.build_frame(d.CMD_IDENT, 1, 0, b"")
stream = MockStream([req])
_run_until_done(stream)

frames = _split_frames(stream.written)
if len(frames) != 1:
    _fail("one response frame written", "got {}".format(len(frames)))
else:
    parsed = d.parse_frame(frames[0])
    if parsed is None:
        _fail("IDENT response parses", "parse_frame returned None")
    else:
        type_, seq, status, payload = parsed
        checks = [
            ("response type == CMD_IDENT | 0x80", type_ == (d.CMD_IDENT | 0x80)),
            ("response seq == request seq", seq == 1),
            ("response status == STATUS_OK", status == d.STATUS_OK),
            ("payload proto_ver == 1", struct.unpack_from("<B", payload, 0)[0] == 1),
        ]
        for name, ok in checks:
            _pass(name) if ok else _fail(name)

# -- same request, but delivered split across multiple readinto() calls,
# -- interleaved with "would block" (None) -- exercises frame_buf
# -- accumulation across chunks and the mp_is_nonblocking_error() retry path.
print("\n--- multi-chunk IDENT round trip (with EAGAIN gaps) ---")
req2 = d.build_frame(d.CMD_IDENT, 7, 0, b"")
mid = len(req2) // 2
stream = MockStream([req2[:mid], None, None, req2[mid:]])
_run_until_done(stream)

frames = _split_frames(stream.written)
if len(frames) != 1:
    _fail("one response frame written (multi-chunk)", "got {}".format(len(frames)))
else:
    parsed = d.parse_frame(frames[0])
    if parsed is None:
        _fail("multi-chunk IDENT response parses", "parse_frame returned None")
    else:
        type_, seq, status, payload = parsed
        checks = [
            ("multi-chunk response type == CMD_IDENT | 0x80", type_ == (d.CMD_IDENT | 0x80)),
            ("multi-chunk response seq == request seq", seq == 7),
            ("multi-chunk response status == STATUS_OK", status == d.STATUS_OK),
        ]
        for name, ok in checks:
            _pass(name) if ok else _fail(name)

# -- a corrupted frame (bad CRC) must be silently dropped -- no response
# -- written at all, matching parse_frame()'s own silently-drop contract
# -- (PROTOCOL.md §1) -- followed by a valid frame to confirm run() keeps
# -- working afterwards rather than getting stuck.
print("\n--- corrupt-CRC frame is dropped, loop keeps going ---")
good = d.build_frame(d.CMD_IDENT, 2, 0, b"")
corrupt = bytearray(d.build_frame(d.CMD_IDENT, 3, 0, b""))
corrupt[-2] ^= 0xFF  # flip a byte inside the trailing COBS-encoded CRC
drops_before = d.drop_count()
stream = MockStream([bytes(corrupt), good])
_run_until_done(stream)

frames = _split_frames(stream.written)
if len(frames) != 1:
    _fail("exactly one response for one corrupt + one good frame", "got {}".format(len(frames)))
else:
    parsed = d.parse_frame(frames[0])
    ok = parsed is not None and parsed[1] == 2 and parsed[2] == d.STATUS_OK
    _pass("only the good (seq=2) frame got a response") if ok else _fail(
        "only the good (seq=2) frame got a response", parsed
    )
_pass("drop_count increased") if d.drop_count() > drops_before else _fail(
    "drop_count increased", (drops_before, d.drop_count())
)

# -- an unrecognized command type must not kill the loop -- dispatch()'s
# -- dev-time NotImplementedError is caught and turned into an
# -- ERR_INTERNAL response frame instead (see bcp_run_handle_segment()'s
# -- own doc comment), and a subsequent valid frame still gets served.
print("\n--- unrecognized command -> ERR_INTERNAL, loop keeps going ---")
bad_cmd = d.build_frame(99, 4, 0, b"")
good2 = d.build_frame(d.CMD_IDENT, 5, 0, b"")
stream = MockStream([bad_cmd, good2])
_run_until_done(stream)

frames = _split_frames(stream.written)
if len(frames) != 2:
    _fail("two response frames (ERR_INTERNAL + IDENT)", "got {}".format(len(frames)))
else:
    p1 = d.parse_frame(frames[0])
    p2 = d.parse_frame(frames[1])
    ok1 = p1 is not None and p1[1] == 4 and p1[2] == d.STATUS_ERR_INTERNAL
    ok2 = p2 is not None and p2[1] == 5 and p2[2] == d.STATUS_OK
    _pass("unrecognized command answers ERR_INTERNAL") if ok1 else _fail(
        "unrecognized command answers ERR_INTERNAL", p1
    )
    _pass("next (valid) frame still served") if ok2 else _fail("next (valid) frame still served", p2)

# -- INTEGRATE_FAST -- exercises the streaming path (bcp_run_emit), the
# -- one code path this file adds beyond what mp_bcp_dispatch() already
# -- covers on its own: MORE frames written mid-dispatch via the C-native
# -- emit callback, not just the single final response every other command
# -- returns. Same G7 profile/request shape test_bcp_dispatch_native.py's
# -- own INTEGRATE_FAST section uses.
print("\n--- INTEGRATE_FAST streams MORE frames through run() ---")


def _pack_profile(bc, wg, dia, length, mv, sh, twist, zero_ft, drag_type, points):
    hdr = struct.pack("<8fBBH", bc, wg, dia, length, mv, sh, twist, zero_ft, drag_type, 0, len(points))
    pts = b"".join(struct.pack("<ff", a, b) for a, b in points)
    return hdr + pts


def _pack_integrate_req(range_limit_ft, range_step_ft, time_step, filter_flags):
    return struct.pack("<3fi", range_limit_ft, range_step_ft, time_step, filter_flags)


_ZERO_FT = 300.0 * 3.28084  # 300 m in feet
load_profile_req = d.build_frame(
    d.CMD_LOAD_PROFILE, 1, 0, _pack_profile(0.305, 168.0, 0.308, 1.2, 2750.0, 1.5, 10.0, _ZERO_FT, 1, [])
)
integrate_req = d.build_frame(d.CMD_INTEGRATE_FAST, 2, 0, _pack_integrate_req(1000.0, 100.0, 0.0, 0))
stream = MockStream([load_profile_req, integrate_req])
_run_until_done(stream)

frames = _split_frames(stream.written)
parsed = [d.parse_frame(fr) for fr in frames]
if any(p is None for p in parsed):
    _fail("all frames parse", parsed)
else:
    load_resp = parsed[0]
    more_frames = [p for p in parsed[1:] if p[2] == d.STATUS_MORE]
    final = parsed[-1]

    _pass("LOAD_PROFILE -> OK") if load_resp[2] == d.STATUS_OK else _fail("LOAD_PROFILE -> OK", load_resp)
    _pass("at least one MORE frame streamed") if len(more_frames) >= 1 else _fail(
        "at least one MORE frame streamed", len(parsed)
    )
    for p in more_frames:
        ok = p[0] == (d.CMD_INTEGRATE_FAST | 0x80) and p[1] == 2
        if not ok:
            _fail("MORE frame has response type/seq", p)
    else:
        _pass("every MORE frame has response type/seq")
    ok_final = final[0] == (d.CMD_INTEGRATE_FAST | 0x80) and final[1] == 2 and final[2] == d.STATUS_OK
    _pass("final frame is the OK/total summary") if ok_final else _fail("final frame is the OK/total summary", final)
    if ok_final:
        total, reason = struct.unpack_from("<Ii", final[3], 0)
        _pass("final total matches row count across MORE frames") if total == sum(
            fr[3][2] for fr in more_frames
        ) else _fail("final total matches row count", (total, [fr[3][2] for fr in more_frames]))

print()
if _failures:
    print("FAILED: {} check(s)".format(_failures))
    sys.exit(1)
else:
    print("All checks passed.")
