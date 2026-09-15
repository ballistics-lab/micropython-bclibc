# ruff: noqa

"""
_bcp_dispatch native (C) module test -- BCLIBC_BCP=1 usermod builds only.
Run with:
    micropython test_bcp_dispatch_native.py
or from repo root:
    /path/to/micropython test_bcp_dispatch_native.py

Only IDENT is implemented so far (see BACKLOG.md Epic 3/8) -- this test
covers IDENT itself, the drop_count telemetry it reports (from
_bcp_frame.parse_frame's own failure counter), the unknown-command
NotImplementedError, and one full parse_frame -> dispatch -> build_frame
round trip tying _bcp_frame and _bcp_dispatch together.
"""

import struct
import sys

try:
    import _bcp_dispatch as d
    import _bcp_frame as f
except ImportError as ex:
    print("SKIP: _bcp_dispatch/_bcp_frame not built into this firmware (BCLIBC_BCP=1 required):", ex)
    sys.exit(0)

_failures = 0


def _pass(name):
    print("  PASS  " + name)


def _fail(name, msg=""):
    global _failures
    _failures += 1
    print("  FAIL  " + name + (" — " + str(msg) if msg else ""))


print("=== _bcp_dispatch native module test ===")

# -- IDENT ---------------------------------------------------------------------
print("\n--- IDENT ---")
try:
    status, payload = d.dispatch(d.CMD_IDENT, 1, b"")
    if status != d.STATUS_OK:
        _fail("IDENT status", "got {}".format(status))
    else:
        _pass("IDENT status == STATUS_OK")
except Exception as ex:
    _fail("IDENT dispatch", ex)
    status, payload = None, b""

try:
    (
        proto_ver,
        real_size,
        traj_row_size,
        base_traj_size,
        max_winds,
        max_drag_pts,
        max_bc_points,
        drop_count,
        version_len,
    ) = struct.unpack_from("<BBHHBHBIB", payload, 0)
    version = payload[15 : 15 + version_len]

    checks = [
        ("proto_ver == 1", proto_ver == 1),
        ("real_size in (4, 8)", real_size in (4, 8)),
        ("traj_row_size matches real_size (64 sp / 124 dp)", traj_row_size == (64 if real_size == 4 else 124)),
        ("base_traj_size matches real_size (32 sp / 64 dp)", base_traj_size == (32 if real_size == 4 else 64)),
        ("max_winds == 5 (BCP cap, PROTOCOL.md §4.1)", max_winds == 5),
        ("max_drag_pts == 200 (BCP cap)", max_drag_pts == 200),
        ("max_bc_points == 5 (BCP cap)", max_bc_points == 5),
        ("version_len matches payload length", len(payload) == 15 + version_len),
        ("version is non-empty", len(version) > 0),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name)
    print("  (informational) version={!r} drop_count={}".format(version, drop_count))
except Exception as ex:
    _fail("IDENT payload decode", ex)

# -- unknown command -------------------------------------------------------------
print("\n--- unknown command ---")
try:
    d.dispatch(99, 1, b"")
    _fail("unknown command", "expected NotImplementedError, got a result")
except NotImplementedError:
    _pass("unknown command raises NotImplementedError")
except Exception as ex:
    _fail("unknown command", "wrong exception type: " + str(ex))

# -- drop_count telemetry --------------------------------------------------------
print("\n--- drop_count telemetry ---")
try:
    before = f.drop_count()
    bad = bytearray(f.build_frame(1, 1, 0, b"x"))
    bad[3] ^= 0xFF  # corrupt CRC
    result = f.parse_frame(bytes(bad[1:-1]))
    after = f.drop_count()
    if result is None and after == before + 1:
        _pass("parse_frame drops a bad-CRC frame and bumps drop_count by 1")
    else:
        _fail("drop_count bump", "result={} before={} after={}".format(result, before, after))

    _, payload2 = d.dispatch(d.CMD_IDENT, 1, b"")
    reported = struct.unpack_from("<I", payload2, 10)[0]
    if reported == after:
        _pass("IDENT reports the live drop_count")
    else:
        _fail("IDENT drop_count", "reported={} actual={}".format(reported, after))
except Exception as ex:
    _fail("drop_count telemetry", ex)

# -- full parse_frame -> dispatch -> build_frame round trip ---------------------
print("\n--- full round trip ---")
try:
    req_frame = f.build_frame(d.CMD_IDENT, 42, 0, b"")
    type_, seq, req_status, req_payload = f.parse_frame(req_frame[1:-1])
    resp_status, resp_payload = d.dispatch(type_, seq, req_payload)
    resp_frame = f.build_frame(type_ | 0x80, seq, resp_status, resp_payload)
    type2, seq2, status2, payload2 = f.parse_frame(resp_frame[1:-1])

    checks = [
        ("request type/seq/status parsed correctly", (type_, seq, req_status) == (d.CMD_IDENT, 42, 0)),
        ("response type has the 0x80 response bit set", type2 == (d.CMD_IDENT | 0x80)),
        ("response seq echoes the request's seq", seq2 == 42),
        ("response status is OK", status2 == d.STATUS_OK),
        ("response payload matches what dispatch() returned", payload2 == resp_payload),
    ]
    for name, ok in checks:
        if ok:
            _pass(name)
        else:
            _fail(name)
except Exception as ex:
    _fail("full round trip", ex)

print("\n=== done ===")
if _failures:
    print("{} test(s) FAILED".format(_failures))
    sys.exit(_failures)
