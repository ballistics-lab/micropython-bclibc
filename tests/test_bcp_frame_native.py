# ruff: noqa

"""
_bcp_frame native (C) module test -- BCLIBC_BCP=1 usermod builds only.
Run with:
    micropython test_bcp_frame_native.py
or from repo root:
    /path/to/micropython test_bcp_frame_native.py

Mirrors tests/test_bcp_frame.py's known-answer vectors and failure
scenarios against the real on-device C module instead of the pure-Python
design-iteration reference (see BACKLOG.md Epic 3: "implementation
language is C, not Python" / "bcp_frame.py is not kept on as a permanent
oracle"). `_bcp_frame.parse_frame()` takes one already delimiter-split
COBS segment rather than accumulating a byte stream itself -- that
accumulation is expected to live in the C dispatch loop (not yet written),
so this test does the 0x00-splitting itself, same as that loop eventually
will.
"""

import sys

try:
    import _bcp_frame as f
except ImportError as ex:
    print("SKIP: _bcp_frame not built into this firmware (BCLIBC_BCP=1 required):", ex)
    sys.exit(0)

_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


def _eq(a, b):
    return bytes(a) == bytes(b)


def _split_frames(stream):
    """Split raw wire bytes on 0x00 into candidate COBS segments, dropping
    empty ones -- the same job bcp_frame.FrameDecoder.feed() does, done
    here in the test script since _bcp_frame.parse_frame() takes one
    segment at a time."""
    return [seg for seg in stream.split(b"\x00") if seg]


print("=== _bcp_frame native module test ===")

# -- CRC16/CCITT-FALSE known-answer vector ------------------------------------
print("\n--- CRC16 ---")
try:
    got = f.crc16(b"123456789")
    if got == 0x29B1:
        _pass("crc16('123456789') == 0x29B1")
    else:
        _fail("crc16('123456789')", "got 0x{:04X}".format(got))
except Exception as ex:
    _fail("crc16 known-answer", ex)

try:
    got = f.crc16(b"\x01\x02\x03", 0x1234)
    _pass("crc16 with explicit seed runs — 0x{:04X}".format(got))
except Exception as ex:
    _fail("crc16 explicit seed", ex)

# -- COBS known vectors --------------------------------------------------------
print("\n--- COBS known vectors ---")
_COBS_VECTORS = [
    (b"\x00", b"\x01\x01"),
    (b"\x00\x00", b"\x01\x01\x01"),
    (b"\x00\x11\x00", b"\x01\x02\x11\x01"),
    (b"\x11\x22\x00\x33", b"\x03\x11\x22\x02\x33"),
    (b"\x11\x22\x33\x44", b"\x05\x11\x22\x33\x44"),
    (b"\x11\x00\x00\x00", b"\x02\x11\x01\x01\x01"),
]
for raw, expected in _COBS_VECTORS:
    name = "cobs_encode({})".format(raw)
    try:
        got = f.cobs_encode(raw)
        if _eq(got, expected):
            _pass(name)
        else:
            _fail(name, "got {} expected {}".format(got, expected))
    except Exception as ex:
        _fail(name, ex)

for raw, expected in _COBS_VECTORS:
    name = "cobs_decode({})".format(expected)
    try:
        got = f.cobs_decode(expected)
        if _eq(got, raw):
            _pass(name)
        else:
            _fail(name, "got {} expected {}".format(got, raw))
    except Exception as ex:
        _fail(name, ex)

# -- COBS round-trip property tests -------------------------------------------
print("\n--- COBS round-trip ---")
try:
    ok = True
    for n in (0, 1, 2, 3, 16, 253, 254, 255, 256, 509, 510, 511, 1024, 1650):
        data = bytes((i * 7 + 1) & 0xFF for i in range(n))  # includes zero bytes
        encoded = f.cobs_encode(data)
        if 0 in encoded:
            ok = False
            _fail("cobs round-trip n={} (zero in encoded output)".format(n))
            continue
        decoded = f.cobs_decode(encoded)
        if not _eq(decoded, data):
            ok = False
            _fail("cobs round-trip n={}".format(n), "mismatch after decode")
    if ok:
        _pass("cobs round-trip over varying lengths incl. 254/255 boundary and >1.6 KB")
except Exception as ex:
    _fail("cobs round-trip", ex)

# -- COBS malformed input ------------------------------------------------------
print("\n--- COBS malformed input ---")
_BAD_INPUTS = [
    b"",
    b"\x00",
    b"\x05\x11\x22",
]
for bad in _BAD_INPUTS:
    name = "cobs_decode(bad={})".format(bad)
    try:
        f.cobs_decode(bad)
        _fail(name, "expected ValueError, got a result")
    except ValueError:
        _pass(name)
    except Exception as ex:
        _fail(name, "wrong exception type: " + str(ex))

# -- build_frame / parse_frame round-trip -------------------------------------
print("\n--- build_frame / parse_frame round-trip ---")
try:
    frame = f.build_frame(1, 42, 0, b"hello")
    if frame[0] == 0 and frame[-1] == 0:
        _pass("build_frame delimited with leading/trailing 0x00")
    else:
        _fail("build_frame delimiters", frame)

    got = f.parse_frame(frame[1:-1])
    if got == (1, 42, 0, b"hello"):
        _pass("parse_frame decodes a single well-formed frame")
    else:
        _fail("parse_frame single frame", got)
except Exception as ex:
    _fail("build_frame/parse_frame round-trip", ex)

try:
    frame_empty = f.build_frame(2, 1, 0)  # payload defaults to b""
    got = f.parse_frame(frame_empty[1:-1])
    if got == (2, 1, 0, b""):
        _pass("build_frame with default (empty) payload")
    else:
        _fail("build_frame default payload", got)
except Exception as ex:
    _fail("build_frame default payload", ex)

# -- multiple frames, arbitrary chunking (splitting done in this script) -----
print("\n--- multiple frames via 0x00-splitting ---")
try:
    f1 = f.build_frame(2, 1, 0, b"")
    f2 = f.build_frame(3, 2, f.STATUS_OK, b"\x01\x02\x03\x04")
    stream = f1 + f2
    segs = _split_frames(stream)
    got = [f.parse_frame(seg) for seg in segs]
    expected = [(2, 1, 0, b""), (3, 2, f.STATUS_OK, b"\x01\x02\x03\x04")]
    if got == expected:
        _pass("two frames decoded correctly after splitting on 0x00")
    else:
        _fail("multi-frame split", got)
except Exception as ex:
    _fail("multi-frame split", ex)

# -- Failure scenarios discussed in BACKLOG.md Epic 3 -------------------------
print("\n--- framing failure scenarios ---")

try:
    good = f.build_frame(5, 9, 0, b"ok")
    garbage = b"\x01\x02\x03" + good
    segs = _split_frames(garbage)
    got = [r for r in (f.parse_frame(s) for s in segs) if r is not None]
    if got == [(5, 9, 0, b"ok")]:
        _pass("garbage before first frame does not corrupt the next frame")
    else:
        _fail("lost frame start", got)
except Exception as ex:
    _fail("lost frame start", ex)

try:
    f1 = f.build_frame(1, 1, 0, b"aaa")
    f2 = f.build_frame(2, 2, 0, b"bbb")
    merged = f1[:-1] + f2  # drop f1's trailing zero, keep f2's leading zero
    segs = _split_frames(merged)
    got = [r for r in (f.parse_frame(s) for s in segs) if r is not None]
    if got == [(1, 1, 0, b"aaa"), (2, 2, 0, b"bbb")]:
        _pass("losing one of the two delimiters between frames still separates them")
    else:
        _fail("lost delimiter", got)
except Exception as ex:
    _fail("lost delimiter", ex)

try:
    good1 = bytearray(f.build_frame(1, 1, 0, b"first"))
    good1[3] ^= 0xFF  # flip a byte inside the COBS-encoded body -> bad CRC
    good2 = f.build_frame(1, 2, 0, b"second")
    segs = _split_frames(bytes(good1) + good2)
    got = [r for r in (f.parse_frame(s) for s in segs) if r is not None]
    if got == [(1, 2, 0, b"second")]:
        _pass("frame with corrupted CRC is dropped (parse_frame returns None), next decodes")
    else:
        _fail("bad CRC frame", got)
except Exception as ex:
    _fail("bad CRC frame", ex)

print("\n=== done ===")
if _failures:
    print("{} test(s) FAILED".format(_failures))
    sys.exit(_failures)
