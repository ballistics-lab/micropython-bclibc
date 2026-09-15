# ruff: noqa

"""
bcp_frame codec test -- pure Python, no native module, no hardware.
Run with:
    python3 test_bcp_frame.py
or:
    micropython test_bcp_frame.py
"""

import sys

try:
    _HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
except NameError:
    _HERE = "."
sys.path.append(_HERE)
sys.path.append(_HERE + "/../src")

import bcp_frame as bf

_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


def _eq(a, b):
    return bytes(a) == bytes(b)


print("=== bcp_frame codec test ===")

# -- CRC16/CCITT-FALSE known-answer vector ------------------------------------
print("\n--- CRC16 ---")
try:
    got = bf.crc16(b"123456789")
    if got == 0x29B1:
        _pass("crc16('123456789') == 0x29B1")
    else:
        _fail("crc16('123456789')", "got 0x{:04X}".format(got))
except Exception as ex:
    _fail("crc16 known-answer", ex)

# -- COBS known vectors (small cases from the COBS reference paper) ----------
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
    name = "cobs_encode({})".format(raw.hex())
    try:
        got = bf.cobs_encode(raw)
        if _eq(got, expected):
            _pass(name)
        else:
            _fail(name, "got {} expected {}".format(got.hex(), expected.hex()))
    except Exception as ex:
        _fail(name, ex)

for raw, expected in _COBS_VECTORS:
    name = "cobs_decode({})".format(expected.hex())
    try:
        got = bf.cobs_decode(expected)
        if _eq(got, raw):
            _pass(name)
        else:
            _fail(name, "got {} expected {}".format(got.hex(), raw.hex()))
    except Exception as ex:
        _fail(name, ex)

# -- COBS round-trip property tests -------------------------------------------
print("\n--- COBS round-trip ---")
try:
    ok = True
    for n in (0, 1, 2, 3, 16, 253, 254, 255, 256, 509, 510, 511, 1024):
        data = bytes((i * 7 + 1) & 0xFF for i in range(n))  # includes zero bytes
        encoded = bf.cobs_encode(data)
        if 0 in encoded:
            ok = False
            _fail("cobs round-trip n={} (zero in encoded output)".format(n))
            continue
        decoded = bf.cobs_decode(encoded)
        if not _eq(decoded, data):
            ok = False
            _fail("cobs round-trip n={}".format(n), "mismatch after decode")
    if ok:
        _pass("cobs round-trip over varying lengths incl. 254/255 boundary")
except Exception as ex:
    _fail("cobs round-trip", ex)

# -- COBS malformed input ------------------------------------------------------
print("\n--- COBS malformed input ---")
_BAD_INPUTS = [
    b"",  # empty is not a valid COBS-encoded packet (build_frame always emits >=1 byte)
    b"\x00",  # zero byte inside encoded data is never valid
    b"\x05\x11\x22",  # code claims more bytes than are present (truncated)
]
for bad in _BAD_INPUTS:
    name = "cobs_decode(bad={})".format(bad.hex())
    try:
        bf.cobs_decode(bad)
        _fail(name, "expected ValueError, got a result")
    except ValueError:
        _pass(name)
    except Exception as ex:
        _fail(name, "wrong exception type: " + str(ex))

# -- build_frame / FrameDecoder round-trip ------------------------------------
print("\n--- build_frame / FrameDecoder round-trip ---")
try:
    frame = bf.build_frame(1, 42, 0, b"hello")
    if frame[0] == 0 and frame[-1] == 0:
        _pass("build_frame delimited with leading/trailing 0x00")
    else:
        _fail("build_frame delimiters", frame.hex())

    dec = bf.FrameDecoder()
    got = dec.feed(frame)
    if len(got) == 1 and got[0] == (1, 42, 0, b"hello"):
        _pass("FrameDecoder decodes a single well-formed frame")
    else:
        _fail("FrameDecoder single frame", got)
except Exception as ex:
    _fail("build_frame/FrameDecoder round-trip", ex)

# -- FrameDecoder fed byte-by-byte, multiple frames in one feed ---------------
print("\n--- FrameDecoder: multiple frames, arbitrary chunking ---")
try:
    f1 = bf.build_frame(2, 1, 0, b"")
    f2 = bf.build_frame(3, 2, bf.STATUS_OK, b"\x01\x02\x03\x04")
    stream = f1 + f2
    dec = bf.FrameDecoder()
    got = []
    for i in range(len(stream)):  # feed one byte at a time
        got.extend(dec.feed(stream[i : i + 1]))
    expected = [(2, 1, 0, b""), (3, 2, bf.STATUS_OK, b"\x01\x02\x03\x04")]
    if got == expected:
        _pass("two frames decoded correctly when fed one byte at a time")
    else:
        _fail("byte-at-a-time multi-frame", got)
except Exception as ex:
    _fail("multi-frame byte-at-a-time", ex)

# -- Failure scenarios discussed in BACKLOG.md Epic 3 -------------------------
print("\n--- framing failure scenarios ---")

try:
    # Lost frame start: garbage before the first real frame's payload, no
    # leading 0x00 -- the decoder still recovers cleanly at the next 0x00.
    good = bf.build_frame(5, 9, 0, b"ok")
    garbage = b"\x01\x02\x03" + good  # no leading zero on the garbage itself
    dec = bf.FrameDecoder()
    got = dec.feed(garbage)
    if got == [(5, 9, 0, b"ok")]:
        _pass("garbage before first frame does not corrupt the next frame")
    else:
        _fail("lost frame start", got)
except Exception as ex:
    _fail("lost frame start", ex)

try:
    # Lost delimiter between two frames: one of the two zeros between them
    # is dropped, the other still separates the frames.
    f1 = bf.build_frame(1, 1, 0, b"aaa")
    f2 = bf.build_frame(2, 2, 0, b"bbb")
    assert f1[-1:] == b"\x00" and f2[:1] == b"\x00"
    merged = f1[:-1] + f2  # drop f1's trailing zero, keep f2's leading zero
    dec = bf.FrameDecoder()
    got = dec.feed(merged)
    if got == [(1, 1, 0, b"aaa"), (2, 2, 0, b"bbb")]:
        _pass("losing one of the two delimiters between frames still separates them")
    else:
        _fail("lost delimiter", got)
except Exception as ex:
    _fail("lost delimiter", ex)

try:
    # Corrupted frame (bad CRC): dropped silently, next good frame unaffected.
    good1 = bytearray(bf.build_frame(1, 1, 0, b"first"))
    good1[3] ^= 0xFF  # flip a byte inside the COBS-encoded body -> bad CRC
    good2 = bf.build_frame(1, 2, 0, b"second")
    dec = bf.FrameDecoder()
    got = dec.feed(bytes(good1) + good2)
    if got == [(1, 2, 0, b"second")]:
        _pass("frame with corrupted CRC is dropped, next frame still decodes")
    else:
        _fail("bad CRC frame", got)
except Exception as ex:
    _fail("bad CRC frame", ex)

try:
    # Oversized frame with no delimiter: bounded buffer, resyncs on next 0x00.
    dec = bf.FrameDecoder(max_frame_size=16)
    dec.feed(b"\x01" * 100)  # no zero anywhere -- must not grow unbounded
    good = bf.build_frame(7, 7, 0, b"tiny")
    got = dec.feed(good)
    if got == [(7, 7, 0, b"tiny")] and len(dec._buf) == 0:
        _pass("oversized undelimited data is dropped, decoder resyncs")
    else:
        _fail("oversized frame", got)
except Exception as ex:
    _fail("oversized frame", ex)

print("\n=== done ===")
if _failures:
    print("{} test(s) FAILED".format(_failures))
    sys.exit(_failures)
