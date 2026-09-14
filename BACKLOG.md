# Ballistic Coprocessor — Implementation Backlog

Working backlog for turning `micropython-bclibc` into a standalone "ballistic
coprocessor" firmware application: a stateless-except-cached-profile module
that answers `LOAD_PROFILE` / `INTEGRATE` / `INTEGRATE_AT` / `FIND_ZERO_ANGLE`
/ etc. requests over a framed command protocol, instead of being used purely
as a library from Python application code.

## Target platforms (phase 1)

- RP2040
- RP2350
- ESP32-S3

## Explicit non-goals (this phase)

- a7p profile parsing/loading — `LOAD_PROFILE` builds directly on the
  existing `Shot`/`Wind`/`Config` wrappers (`tiny_bclibc.py`), not an a7p
  blob. a7p integration is a later phase.
- UART and BLE (Nordic UART Service) transports — phase 1 targets USB
  CDC1 only. UART/BLE are a later transport epic reusing the same frame
  parser.
- Full BLE pairing/passkey flow — `SET_BLE_PASS` may be stubbed but the
  actual BLE stack work is out of scope until the BLE transport epic.

---

## Epic 1 — Build: usermod gated behind a flag

- [ ] Introduce a build flag (e.g. `BCLIBC_APP_ENABLE`, mirroring the
      existing `BCLIBC_BUILD_NATMOD` switch in `src/tiny_bclibc_mp.c`) that
      gates whether `usermod/micropython.cmake` / `micropython.mk` pull the
      tiny_bclibc usermod sources into the firmware build at all.
- [ ] Default: **off** — a plain usermod build for non-coprocessor firmware
      should not carry the extra ROM/RAM footprint.
- [ ] **Open question:** where does the coprocessor "application" (its own
      `main.py`/`boot.py`, protocol dispatcher, command handlers) live —
      a new top-level directory in this repo (e.g. `app/`, alongside the
      existing `natmod/`/`usermod/`/`ffimod/` build modes), or a separate
      repository that vendors/submodules `micropython-bclibc`? Affects the
      layout of every epic below.

## Epic 2 — Multi-BC native binding

- [ ] `mp_bclibc_build_multibc()` in `src/tiny_bclibc_mp.c`:
      `build_multibc(drag_type, bc_points_buf) -> (mach_list, cd_list)`.
      Reuses the already-resident `g1_mach`/`g1_cd`/`G1_N` and
      `g7_mach`/`g7_cd`/`G7_N` tables from `src/drag_tables.h`.
      Algorithm: sort BC points by Mach, linear-interpolate the BC ratio at
      each reference-table Mach value (clamped at the ends, matching
      py-ballisticcalc's `linear_interpolation`), divide the reference Cd
      by that ratio. `bc` is always fed into `Shot()` as `1.0` for the
      resulting curve — it cancels out of `drag_by_mach`'s
      `Cd(mach) * K / bc` algebraically, so `sectional_density`/
      weight/diameter do not need to be ported for this.
- [ ] Register in both the natmod (`mpy_init`) and usermod
      (`bclibc_module_globals_table`) code paths, matching the existing
      functions' pattern.
- [ ] Python wrapper `MultiBC(bc_points, drag_type=DRAG_G7)` in
      `src/tiny_bclibc.py`, packing points into a buffer and feeding the
      result straight into `Shot(drag_type=DRAG_CUSTOM, drag_mach=...,
      drag_cd=...)`.
- [ ] Test numerical identity against py-ballisticcalc's
      `DragModelMultiBC`, same spirit as `tiny_bclibc/tests/test_identity.cpp`.
- [ ] **Scope decision:** v1 reference table is G1/G7 only (what's already
      in ROM). py-ballisticcalc's `DragModelMultiBC` accepts an arbitrary
      reference `drag_table`; not porting that for now — flag if a
      custom-reference base turns out to be needed.

## Epic 3 — Command/response frame

- [ ] Frame shape: `<start_byte><cmd:1><len><data><crc>`
  - **Open:** `len` as 1 or 2 bytes — a single trajectory row (16×float32 =
        64 bytes) fits in 1 byte, but a `LOAD_PROFILE` payload (Shot buffer
        + winds + drag points) may exceed 255 bytes — needs sizing against
        the actual max `Shot` buffer.
  - **Open:** CRC width/scope (CRC16 vs. lighter; computed over
        `cmd+len+data` only, or `start_byte` included too).
  - **Open — resync strategy:** earlier discussion assumed COBS+CRC16
        byte-stuffed framing (per the original project idea). This
        `start_byte+len+crc` shape as specified has no escaping, so if
        `start_byte`'s value ever occurs inside arbitrary payload bytes
        (floats, binary profile data), a receiver mid-stream could
        false-sync. Needs one of: (a) escape/byte-stuffing for
        `start_byte` inside `data`, (b) keep a COBS wrapper around this
        frame, or (c) rely purely on CRC validation + rescan-for-next-
        `start_byte` on mismatch. Pick one deliberately.
- [ ] Command enum: `LOAD_PROFILE, INTEGRATE, INTEGRATE_AT,
      FIND_ZERO_ANGLE, RESET, SET_BLE_PASS, IDENT, STREAM_START,
      STREAM_END, ABORT, ACK/NAK/ERROR`.
  - **Open:** whether `FIND_APEX`/`FIND_MAX_RANGE` (already bound natively)
        belong in the v1 protocol surface.
- [ ] Response frame: same shape, status code distinguishes
      `OK` / `ERR` / `INTERRUPTED`.

## Epic 4 — Transport: USB CDC1

- [ ] Dual-CDC USB descriptor in firmware (CDC0 stays REPL/debug/firmware
      update, unchanged; CDC1 becomes the command channel). This is a
      MicroPython board-config change (RP2040/RP2350/ESP32-S3 ports), not a
      `tiny_bclibc` change.
- [ ] Non-blocking read of CDC1 into the frame dispatcher, so CDC1 traffic
      never blocks the CDC0 REPL.
- [ ] UART and BLE NUS transports: explicitly deferred to a later epic
      (same frame parser, different byte source).

## Epic 5 — Streaming (Y-modem-like)

- [ ] `STREAM_START(cmd, filter_flags, range/step, ...)` → server replies
      with a sequence of `STREAM_DATA` frames — full trajectories are never
      returned as one packet.
- [ ] `STREAM_END` — final frame carrying the `stop_reason` code already
      produced by `tiny_bclibc_integrate_stream`.
- [ ] **Open — ack scheme:** true per-block Y-modem acking (designed for
      slow modems) would ack every row; at BLE RTTs of tens of ms that
      kills throughput for 30-100+ row trajectories. Options: (a)
      sender-paced with a windowed ack every N rows, (b) no ack at all —
      per-frame CRC plus a row count in `STREAM_END` for host-side
      integrity check, (c) real per-block ack only over USB/UART (low
      RTT), a different scheme over BLE. Needs one chosen model so all
      host libraries implement the same thing.
- [ ] Wire into `tiny_bclibc_integrate_stream`'s row callback
      (`mp_stream_cb` in `tiny_bclibc_mp.c`) — write a wire frame per row
      instead of accumulating a Python list.

## Epic 6 — Abort / interrupt

- [ ] `ABORT` command + `INTERRUPTED` response status.
- [ ] For `INTEGRATE` (streamed): already has the hook needed —
      `mp_stream_cb` returns `TINY_BCLIBC_TERM_HANDLER_STOP` when the
      Python callback returns truthy. Checking an "abort requested" flag
      per row works even single-core, as long as CDC1 is read via
      interrupt into a ring buffer independent of what the main loop is
      doing.
- [ ] ⚠️ **Known gap:** `tiny_bclibc_find_zero_angle` and
      `tiny_bclibc_integrate_at` are opaque C loops with **no** progress
      callback exposed today — they cannot be cooperatively interrupted at
      all as currently written (zero-angle can be up to ~40 iterations,
      each a full integration). Options: (a) add a cancel/progress
      callback to `tiny_bclibc` itself (a `bclibc` repo change, not just
      this repo), or (b) rely on Epic 7 (second core) — core0 just
      discards a stale core1 result when a newer request supersedes it,
      rather than truly interrupting the computation. Needs a decision on
      whether current call latencies (single-digit to tens of ms per the
      project's own numbers) make this acceptable without a real cancel
      hook.

## Epic 7 — Second core (where supported)

- [ ] Move command execution (the calls into `tiny_bclibc`) to a second
      core. There's existing precedent in-repo to build from:
      `natmod/examples/tiny_bclibc_natmod_test_2core.py` and
      `..._bench_2core.py`.
- [ ] Inter-core channel: an abort flag, plus (for streaming) a ring
      buffer of completed rows from core1 to core0.
- [ ] Single-core fallback (Epic 6's cooperative model) for targets without
      a second core — the protocol layer must not *require* dual-core,
      only benefit from it when present.

## Epic 8 — Commands on top of existing structures (no a7p)

- [ ] `LOAD_PROFILE` — accepts a wire payload that maps directly onto
      `Shot`/`Config` (the same `_SHOT_DESC`-style packed layout already
      used internally), not an a7p blob.
- [ ] `RESET` — needs a definition: clear cached `Shot` state, soft-reset
      the MCU, or both under different codes?
- [ ] `SET_BLE_PASS` — the BLE transport itself is out of scope for this
      phase (Epic 4). **Open:** stub this command now as a placeholder, or
      hold it until the BLE epic so there's no dead code in the meantime.
- [ ] `IDENT` — version + capabilities; minimum viable version is just the
      existing `bc.version()` passthrough.
