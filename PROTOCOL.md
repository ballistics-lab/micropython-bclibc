# BCP wire protocol

> [!WARNING]
> **Draft, work in progress.** This documents the design decisions recorded
> in `BACKLOG.md` (Epics 3 and 8) as a single reference instead of scattered
> backlog bullets. Anything not marked "Resolved" in `BACKLOG.md` is still
> open and may change. The framing layer (COBS + CRC16) is implemented and
> tested in `src/bcp_frame.py` / `tests/test_bcp_frame.py`; the per-command
> dispatch table is not written yet.

All multi-byte integers and floats are **little-endian**. All floats are
**IEEE-754 binary32** (`f32`) on the wire regardless of the on-device build's
own `real_t` (single or double precision) -- the dispatcher converts. `real_t`
size only matters for the trajectory-row fields reported by `IDENT` (see
below), so a host never needs to know the device's build precision to decode
a request/response.

## 1. Framing

Wire bytes: `00 COBS(packet) 00`.

There is no separate start byte and no length field. COBS guarantees the
encoded bytes contain no `0x00`, so the leading/trailing zero alone
delimits a frame; a merged or truncated frame is caught by CRC16 plus a
per-command payload size check (§4), not by a length field. See
`BACKLOG.md` Epic 3 for the full rationale (what a lost frame-start, a lost
delimiter, leading garbage, and an over-long undelimited run each do).

Decoding a chunk of transport bytes:

```
buf = bytearray()
for byte in incoming_bytes:
    if byte == 0:
        if buf:                      # ignore 00 00 (empty segment)
            packet = cobs_decode(buf)          # raises on malformed COBS
            if len(packet) >= 6:                # HEADER_SIZE(4) + CRC_SIZE(2)
                body, crc = packet[:-2], packet[-2:]
                if crc16(body) == u16_le(crc):
                    handle(body)        # header + payload, CRC verified
                # else: silently drop -- seq inside `body` cannot be trusted
        buf = bytearray()
    else:
        buf.append(byte)
        if len(buf) > MAX_FRAME_SIZE:  # bounded RX buffer, no delimiter seen
            buf = bytearray()           # drop, resync on the next 0x00
```

Reference implementation: `bcp_frame.FrameDecoder.feed()`.

Encoding a packet for the wire: `bcp_frame.build_frame(type_, seq, status, payload)`.

## 2. Packet header (4 bytes)

| offset | field | type | meaning |
|---|---|---|---|
| 0 | `type` | `u8` | command id in a request; `cmd \| 0x80` in the matching response |
| 1 | `seq` | `u8` | set by the host, echoed back unchanged in the response |
| 2 | `status` | `u8` | `0` in a request; one of §3 in a response |
| 3 | `rsvd` | `u8` | reserved, `0` |

Followed by the command's payload (§4), followed by a 2-byte CRC16 (§2.1)
over everything from offset 0 through the end of the payload.

Putting the 4-byte header first keeps the payload 4-byte aligned, so a
`uctypes.struct` can be laid directly over the decoded packet body without
a copy.

### 2.1 CRC16

CRC-16/CCITT-FALSE: poly `0x1021`, init `0xFFFF`, no input/output
reflection, xorout `0x0000`. 256-entry table-driven. Check value:
`crc16(b"123456789") == 0x29B1` (the standard catalogue vector for this
variant).

Measured on real hardware (Waveshare RP2040-Zero, RP2040, MicroPython
1.29.0, plain bytecode) at **~12.6 µs/byte** -- 2x faster than a 16-entry
nibble table and 7x faster than a bitwise loop. The table is computed
once at import (not a frozen flash constant), so its cost is **RAM**, not
ROM: stored as `array('H', ...)` rather than a plain `list` (a list of
256 ints is really a 256-pointer object array) -- measured **528 B**
versus **1040 B** for the same 256 values, ~5% slower, noise next to the
table-size choice itself. See `BACKLOG.md` Epic 3 for the full comparison
table. Worst-case framing cost (COBS + CRC16 together, the ~1.4 KB
`LOAD_PROFILE` frame) ≈ 40 ms -- negligible next to how rarely that frame
is sent (once per rifle/ammo setup) and to actual integration compute
time for everything
else.

## 3. Response status codes

| value | name | meaning |
|---|---|---|
| 0 | `OK` | command completed; payload (if any) is valid |
| 1 | `MORE` | one chunk of a streamed response (`INTEGRATE`); more frames follow, terminated by a final `OK` |
| 2 | `INTERRUPTED` | this generation was preempted by a later command before it finished (Epic 6) -- payload (if any) is not meaningful |
| 3 | `ERR_BAD_SIZE` | payload length doesn't match the size computed from its own count field(s) (§4.1) |
| 4 | `ERR_BAD_ARG` | a count field, enum value, or numeric argument is out of range |
| 5 | `ERR_NOT_LOADED` | command needs a cached profile (and/or conditions) that hasn't been loaded yet |
| 6 | `ERR_INTERNAL` | the underlying `tiny_bclibc` call failed (bad bracket, no convergence, etc.) |

A frame that fails CRC never gets a response at all (§1) -- these codes
only cover frames that passed framing but failed at the command layer.

## 4. Commands

| id | name | request payload | response payload |
|---|---|---|---|
| 1 | `LOAD_PROFILE` | §4.2 | `barrel_elevation_rad:f32` |
| 2 | `LOAD_CONDITIONS` | §4.3 | `barrel_elevation_rad:f32` |
| 3 | `INTEGRATE` | `Request` (§4.4) | stream of `MORE` rows (full `TrajectoryData`), then `total:u32, reason:i32` |
| 4 | `INTEGRATE_FAST` | `Request` (§4.4, same struct) | stream of `MORE` rows (compact `FastTrajData`, §4.5a), then `total:u32, reason:i32` |
| 5 | `INTEGRATE_AT` | `key:u8, rsvd:u8[3], target:f32` | `BaseTrajData` + `TrajectoryData` (§4.5) |
| 6 | `FIND_APEX` | *(none)* | one `TrajectoryData` row (§4.5) |
| 7 | `FIND_MAX_RANGE` | `lo:f32, hi:f32` | `range_ft:f32, angle_rad:f32` |
| 8 | `RESET` | *(none)* | `OK` |
| 9 | `IDENT` | *(none)* | §4.6 |
| 10 | `ABORT` | *(none)* | `OK` (see note below) |

Numeric ids above are provisional -- not yet cross-checked against an
actual enum in code; treat the **names** as fixed, the **numbers** as
placeholders until `bcp_frame`/`bclibc_bcp` defines the real enum.

`FIND_ZERO_ANGLE` and `STREAM_START`/`STREAM_END` are **not** wire
commands -- see `BACKLOG.md` Epic 3/8: zero-solving is internal and
auto-triggered by `LOAD_PROFILE`/`LOAD_CONDITIONS` (§4.2/§4.3), and
`INTEGRATE` streams on its own via `MORE` frames.

### 4.1 Array-count rule

Every variable-length part of a payload (a drag table, a wind array, a
version string) is preceded by its own count/length at a fixed position.
The receiver:

1. checks each count against its cap (`drag_count ≤ 128`, `wind_count ≤ 16`);
2. computes the expected payload size from the fixed fields + counts;
3. requires that size to **equal** the payload length carried by the frame.

A count over its cap → `ERR_BAD_ARG`. A size mismatch → `ERR_BAD_SIZE`.
This replaces a length field in the packet header (§1) and also catches a
merged/truncated frame that happened to pass CRC16 (~1/65536 chance).

### 4.2 `LOAD_PROFILE`

Rifle + ammo + solver tuning + the zero **distance** (not a pre-solved
angle -- see below). Cached until the next `LOAD_PROFILE` or `RESET`.

| offset | field | type |
|---|---|---|
| 0 | `bc` | `f32` |
| 4 | `weight_grain` | `f32` |
| 8 | `diameter_inch` | `f32` |
| 12 | `length_inch` | `f32` |
| 16 | `muzzle_velocity_fps` | `f32` |
| 20 | `sight_height_ft` | `f32` |
| 24 | `twist_inch` | `f32` |
| 28 | `zero_distance_ft` | `f32` |
| 32 | `step_multiplier` | `f32` |
| 36 | `zero_finding_accuracy` | `f32` |
| 40 | `minimum_velocity` | `f32` |
| 44 | `maximum_drop` | `f32` |
| 48 | `gravity_constant` | `f32` |
| 52 | `minimum_altitude` | `f32` |
| 56 | `max_iterations` | `i32` |
| 60 | `drag_type` | `u8` (`0`=G1, `1`=G7, `2`=custom) |
| 61 | `rsvd` | `u8` |
| 62 | `drag_count` | `u16` (≤ 128; ignored unless `drag_type`=custom) |
| 64 | `drag_points` | `drag_count × {mach:f32, cd:f32}` |

Fixed part: 64 B. Max payload (128-point custom table): 64 + 128·8 = 1088 B.

**Zero handling (resolved, see `BACKLOG.md` Epic 8):** the client supplies
a *distance*, not an angle -- the elevation needed to hit that distance
depends on the current atmosphere, so it can't be supplied once and cached
verbatim. The dispatcher internally solves for `barrel_elevation_rad`
against whatever conditions are cached (or the §4.3 defaults, if
`LOAD_CONDITIONS` hasn't arrived yet) and stores it before replying. A
zero-solve failure (no bracket, no convergence) is reported as
`ERR_INTERNAL` on **this** response -- there is no separate
`FIND_ZERO_ANGLE` response to carry it.

Response payload: `barrel_elevation_rad:f32` -- the solved zero, echoed
back as telemetry so the host doesn't need a separate query round-trip.

### 4.3 `LOAD_CONDITIONS`

Atmosphere + shot geometry + wind. Expected to change every few shots.

| offset | field | type |
|---|---|---|
| 0 | `temp_c` | `f32` |
| 4 | `pressure_hpa` | `f32` |
| 8 | `altitude_ft` | `f32` |
| 12 | `humidity` | `f32` |
| 16 | `look_angle_rad` | `f32` |
| 20 | `barrel_azimuth_rad` | `f32` |
| 24 | `cant_angle_rad` | `f32` |
| 28 | `latitude_deg` | `f32` |
| 32 | `azimuth_deg` | `f32` |
| 36 | `wind_count` | `u8` (≤ 16) |
| 37 | `rsvd` | `u8[3]` |
| 40 | `winds` | `wind_count × {velocity_fps:f32, direction_from_rad:f32, until_distance_ft:f32, max_distance_ft:f32}` |

Fixed part: 40 B. Max payload (16 winds): 40 + 16·16 = 296 B.

**If no `LOAD_CONDITIONS` has been sent yet**, `INTEGRATE`/`FIND_*`/the
`LOAD_PROFILE` zero-solve above fall back to `Shot()`'s existing
Python-side defaults: ICAO standard atmosphere, no wind, zero cant/look
angle -- same defaults, just applied on-device.

Response payload: `barrel_elevation_rad:f32` -- `LOAD_CONDITIONS`
re-solves the cached profile's zero against the new conditions (§4.2), so
it echoes the same field. `ERR_NOT_LOADED` if no profile is cached yet
(there is no `zero_distance_ft` to solve against). `ERR_INTERNAL` on a
zero-solve failure.

### 4.4 `INTEGRATE`

Request (`Request`, 16 B, unchanged by the profile/conditions split --
it already carried only per-call parameters):

| offset | field | type |
|---|---|---|
| 0 | `range_limit_ft` | `f32` |
| 4 | `range_step_ft` | `f32` |
| 8 | `time_step` | `f32` |
| 12 | `filter_flags` | `i32` |

`ERR_NOT_LOADED` if no profile is cached.

Response: zero or more `status=MORE` frames, each:

| offset | field | type |
|---|---|---|
| 0 | `row_idx` | `u16` |
| 2 | `count` | `u8` |
| 3 | `rsvd` | `u8` |
| 4 | `rows` | `count × TrajectoryData` (§4.5), size `traj_row_size` from `IDENT` |

followed by a final `status=OK` frame:

| offset | field | type |
|---|---|---|
| 0 | `total` | `u32` |
| 4 | `reason` | `i32` (`tiny_bclibc_integrate`'s stop reason) |

### 4.4a `INTEGRATE_FAST`

Same request struct and semantics as `INTEGRATE` (§4.4) -- same
`Request`, same `filter_flags`, same stream/final-frame shape, same
`ERR_NOT_LOADED` rule. The only difference is the row struct carried by
each `MORE` frame: `FastTrajData` (§4.5a) instead of the full
`TrajectoryData`.

**Why a second command instead of a flag on `INTEGRATE`:** most callers
only need a handful of fields per row (holdover angles for a
scope/reticle), and **per-point latency, not just total bandwidth, is
the point** -- this matters most on the UART transport planned for a
later epic (out of phase-1 scope per the non-goals above, but the frame
layer is designed transport-agnostic from the start, §0). On a serial
link, unlike USB CDC, *byte transmission time itself* is the bottleneck,
not CPU-side COBS/CRC cost -- at a common 115200 baud (8N1, 10 bits/byte
≈ 86.8 µs/byte), sending one full-precision double-build row (124 B)
takes **~10.8 ms** versus **~1.4 ms** for the 16 B fast row; even at
921600 baud that's ~1.35 ms vs ~0.17 ms. Both are well above the ~12.6
µs/byte CRC16 cost measured in §2.1 -- on UART the wire itself, not the
framing math, sets the pace, so shrinking the row is the only lever that
actually shortens the delay before the next point lands. Both commands
run the exact same underlying `tiny_bclibc_integrate_stream()` call;
`INTEGRATE_FAST` is purely a thinner wire projection of the same computed
rows, not a cheaper computation -- no engine-level change needed, and it
costs nothing extra on USB CDC1 either.

Response `MORE` frame:

| offset | field | type |
|---|---|---|
| 0 | `row_idx` | `u16` |
| 2 | `count` | `u8` |
| 3 | `rsvd` | `u8` |
| 4 | `rows` | `count × FastTrajData` (§4.5a, fixed 16 B each) |

Final frame identical to `INTEGRATE`'s (`total:u32, reason:i32`).

### 4.5a `FastTrajData` (compact row, `INTEGRATE_FAST` only)

| offset | field | type |
|---|---|---|
| 0 | `distance_ft` | `f32` |
| 4 | `drop_angle_rad` | `f32` |
| 8 | `windage_angle_rad` | `f32` |
| 12 | `velocity_fps` | `f32` |

Angles rather than raw `height_ft`/`windage_ft`, since these map directly
to a scope/reticle's holdover and windage clicks without the host needing
`sight_height_ft`/range to convert; `velocity_fps` alongside them for
energy/stability context at that range.

Always **16 B on the wire, on every build** -- unlike `TrajectoryData`
below, `FastTrajData`'s size does not depend on the device's `real_t`
precision (all wire floats are `f32` regardless of build, §0; this
struct just happens to have no double-precision-only internal fields to
worry about). A host does not need `IDENT`'s `real_size` to decode it.

### 4.5 Trajectory row structs

`TrajectoryData` (full row -- `FIND_APEX`, `INTEGRATE_AT`, `INTEGRATE`'s
`MORE` frames), 15 `real_t` fields + 1 `i32`, in this order: `time,
distance_ft, velocity_fps, mach, height_ft, slant_height_ft,
drop_angle_rad, windage_ft, windage_angle_rad, slant_distance_ft,
angle_rad, density_ratio, drag, energy_ft_lb, ogw_lb, flag`. Size is
**64 B on a single-precision build, 124 B on double precision** --
report both this size and which build is running via `real_size` in
`IDENT` (§4.6); a host must not assume one without checking.

`BaseTrajData` (`INTEGRATE_AT`'s raw interpolated point, paired with a
full `TrajectoryData`), 8 `real_t` fields: `time, px, py, pz, vx, vy, vz,
mach`. Size 32 B (sp) / 64 B (dp).

`INTEGRATE_AT`'s `key:u8` selects which field of `BaseTrajData` the
`target:f32` is interpolated against (`0`=time, `1`=mach, `2..4`=pos
x/y/z, `5..7`=vel x/y/z -- `TINY_BCLIBC_KEY_*` in
`bclibc/tiny_bclibc/include/tiny_bclibc/traj_data.h`).

### 4.6 `IDENT`

No request payload. Response (fixed part, `struct` format `<BBHHBHIB`):

| offset | field | type | meaning |
|---|---|---|---|
| 0 | `proto_ver` | `u8` | this protocol's version |
| 1 | `real_size` | `u8` | `4` (single) or `8` (double precision build) |
| 2 | `traj_row_size` | `u16` | `TrajectoryData` size in bytes (64 or 124) |
| 4 | `base_traj_size` | `u16` | `BaseTrajData` size in bytes (32 or 64) |
| 6 | `max_winds` | `u8` | cap for `LOAD_CONDITIONS`'s wind array (16) |
| 7 | `max_drag_pts` | `u16` | cap for `LOAD_PROFILE`'s custom drag table (128) |
| 9 | `drop_count` | `u32` | frames dropped for bad CRC/size since boot (optional telemetry, §1) |
| 13 | `version_len` | `u8` | length of the version string that follows |
| 14 | `version` | `bytes[version_len]` | `tiny_bclibc.version()` passthrough, e.g. `"0.x.y-sp"` |

### 4.7 `RESET`

No request/response payload beyond `OK`. Per `BACKLOG.md` Epic 8: an
**application soft-reset**, not a targeted data-clearer (every
`LOAD_PROFILE`/`LOAD_CONDITIONS` already fully overwrites, so that's
redundant) and not an MCU reboot (out of scope -- that's a CDC0
REPL/firmware-update concern). Clears cached profile, cached
conditions/zero, and dispatcher bookkeeping (command generation/seq
tracking, stream state, drop counters). Implies the same preemption
`ABORT` does: if something is running, kill/relaunch the worker first
(Epic 6), then clear state.

### 4.8 `ABORT`

No payload. Per the no-queue preemption rule (Epic 6), any new valid
frame already preempts whatever is running -- `ABORT` is just the case
where nothing replaces it. **Two responses may be in flight for two
different `seq` values:** the killed command's original request gets a
`status=INTERRUPTED` response (under *its own* `seq`), and the `ABORT`
command itself gets a plain `status=OK` response (under `ABORT`'s `seq`).
