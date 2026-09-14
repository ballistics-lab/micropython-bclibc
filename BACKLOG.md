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

- [x] **Resolved — flag name: `BCLIBC_RT`** (mirrors the existing
      `BCLIBC_BUILD_NATMOD` switch in `src/tiny_bclibc_mp.c`).
- [ ] Default: **off** — a plain usermod build for non-coprocessor firmware
      should not carry the extra ROM/RAM footprint.
- [x] **Resolved:** the application lives in `src/`, alongside
      `tiny_bclibc.py`/`tiny_bclibc_mp.c` — no new top-level directory, no
      separate repo. Its `.py` files are only **frozen** into the firmware
      image when `BCLIBC_RT` is set.
- [ ] `BCLIBC_RT` needs plumbing through two independent MicroPython build
      mechanisms that both need to key off the same flag: a CMake/Make
      option controlling whether the C usermod sources are compiled in,
      and a `usermod/manifest.py` conditional (via a `--var` passed to
      `makemanifest.py`) controlling whether the app's `.py` files get
      frozen.

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

- [x] **Resolved:** `len` is **2 bytes** — a `LOAD_PROFILE` payload (Shot
      buffer + winds + drag points) can run up to 2-3 KB, well past what a
      1-byte length field could address.
- [x] **Resolved:** COBS-wrapped framing —
      `<start_byte><cmd:1><len:2><data><crc16>`, the whole thing
      COBS-encoded — chosen over raw start-byte scanning specifically for
      reliability against false sync when payload bytes happen to collide
      with `start_byte`.
- [x] **Resolved:** CRC16, scope = `cmd+len+data`. Exact polynomial not
      fixed yet — pick a well-known table-driven variant (e.g. CRC16-CCITT
      or CRC16/MODBUS) for O(1)-per-byte, RT-safe cost; the specific
      choice matters less than "fast and table-driven."
- [x] **Resolved:** `FIND_APEX` and `FIND_MAX_RANGE` are in the v1 command
      set (both already natively bound).
- [ ] Command enum: `LOAD_PROFILE, INTEGRATE, INTEGRATE_AT,
      FIND_ZERO_ANGLE, FIND_APEX, FIND_MAX_RANGE, RESET, SET_BLE_PASS,
      IDENT, STREAM_START, STREAM_END, ABORT, ACK/NAK/ERROR`.
- [ ] Response frame: same shape, status code distinguishes
      `OK` / `ERR` / `INTERRUPTED`.

## Epic 4 — Transport: USB CDC1

- [x] **Resolved:** no board-level C descriptor change needed — configure
      the second CDC interface at runtime from `boot.py` using
      MicroPython's dynamic USB device API (`usb.device`). CDC0 stays
      REPL/debug/firmware update, unchanged.
- [ ] Verify `usb.device` CDC-composite support/parity across the actual
      MicroPython port versions targeted for RP2040, RP2350, and ESP32-S3
      — confirm per-port before relying on it uniformly across all three.
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
- [ ] **Ack scheme — recommendation pending confirmation.** Plain
      windowed-ack (ack every N rows) is reliable but its throughput cost
      scales with RTT × (rows / window) — expensive over BLE. Plain no-ack
      (per-frame CRC + row count in `STREAM_END` only) is fastest but a
      single dropped/corrupt frame forces restarting the *entire* stream,
      since there's nothing to resume from. Proposed middle ground: every
      `STREAM_DATA` frame carries a monotonically increasing sequence
      number; no ack in the normal case (full throughput); the receiver
      detects a gap (sequence discontinuity or bad CRC) and sends a single
      `RESEND(from_seq)` request; the sender resumes from that row
      (cheap — another `integrate_at`/continued stream, not a full
      restart) instead of re-sending from row 0. This keeps the common
      case ack-free while staying recoverable, unlike plain no-ack. Needs
      sign-off before implementation — and should be the same scheme
      across USB/UART/BLE so all host libraries implement one thing.
- [ ] Wire into `tiny_bclibc_integrate_stream`'s row callback
      (`mp_stream_cb` in `tiny_bclibc_mp.c`) — write a wire frame per row
      instead of accumulating a Python list.

## Epic 6 — Abort / interrupt

- [x] **Resolved — no command queue.** The coprocessor never queues work:
      receiving any new valid (CRC-passing) command frame implicitly
      **preempts** whatever computation is currently running (matches
      "don't wait for the previous calculation when input just changed").
      Explicit `ABORT` is just the case where nothing replaces the
      interrupted work.
- [ ] **Cancel mechanism — leaning `setjmp`/`longjmp`, contained entirely
      in `micropython-bclibc`'s binding layer, instead of a callback API
      inside `tiny_bclibc` itself.** Rationale: `tiny_bclibc` is
      already no-heap/no-lock with caller-owned buffers only (confirmed —
      see `ShotHolder`, Python-owned, in `tiny_bclibc_mp.c`), which is
      exactly the precondition that makes abandoning a call mid-flight via
      `longjmp` safe — no internal mutable state is left corrupted. This
      avoids the earlier plan's cross-repo dependency (adding a
      progress/cancel callback to every blocking entry point in `bclibc`
      itself) entirely — the whole mechanism stays in
      `src/tiny_bclibc_mp.c`:
  - Wrap each blocking call (`find_zero_angle`, `find_apex`,
        `find_max_range`, `integrate`, `integrate_at`) with `setjmp()`
        right before invoking into `tiny_bclibc`; a single global
        `jmp_buf` is sufficient given the "no queue, one in-flight
        computation" rule above.
  - A preempting event (new valid frame parsed, or explicit `ABORT`)
        triggers `longjmp()` back to that point from an
        interrupt/inter-core-interrupt context.
  - **Needs verification before this is locked in as the approach:**
    - [ ] `longjmp` fired from an ISR back into normal call-stack
          execution — confirm this is sound on RP2040/RP2350
          (bare-metal Cortex-M) *and* ESP32-S3 (Xtensa, typically
          FreeRTOS-hosted in the MicroPython port) — don't assume parity
          across the three targets.
    - [ ] Single-core: the CDC1 RX ISR performs the `longjmp` directly.
    - [ ] Dual-core (Epic 7): if the blocking call runs on core1, core0
          cannot `longjmp` across cores — core0's frame receiver signals
          core1 via an inter-core interrupt/doorbell (e.g. RP2040 SIO FIFO
          IRQ), and **core1's own ISR** performs the `longjmp`.
    - [ ] Binding-layer contract: once `setjmp()` returns nonzero (i.e.
          reached via `longjmp`), the wrapper must treat any
          output buffer/struct as partial garbage and return
          `INTERRUPTED` without touching it (no `traj_to_tuple()` etc. on
          abandoned data).
  - **Fallback:** if `longjmp`-from-ISR proves unsound on a given target
        (most likely risk area: ESP32-S3), fall back to the
        progress-callback-in-`tiny_bclibc` approach for that target only —
        the two approaches aren't mutually exclusive across platforms.
- [ ] `INTERRUPTED` response status for whatever got preempted (distinct
      from the normal response to the command that preempted it).
- [ ] `INTEGRATE` (streamed) already has an additional, independent
      cooperative hook available regardless of the above: `mp_stream_cb`
      returns `TINY_BCLIBC_TERM_HANDLER_STOP` when the Python callback
      returns truthy — useful as a cheap early-exit check on the
      streaming path specifically, on top of whichever general mechanism
      is chosen.

## Epic 7 — Second core (where supported)

- [ ] Move command execution (the calls into `tiny_bclibc`) to a second
      core. There's existing precedent in-repo to build from:
      `natmod/examples/tiny_bclibc_natmod_test_2core.py` and
      `..._bench_2core.py`.
- [ ] Inter-core channel: an inter-core interrupt/doorbell that triggers
      core1's own `longjmp` (Epic 6), plus (for streaming) a ring buffer
      of completed rows from core1 to core0.
- [ ] With Epic 6's "no queue, latest command preempts" model, dual-core is
      the clean way to guarantee core0 stays responsive to new/preempting
      frames while core1 is mid-computation — worth sequencing this epic
      together with Epic 6 rather than strictly after it.
- [ ] Single-core fallback (Epic 6's cooperative/ISR-`longjmp` model) for
      targets without a second core — the protocol layer must not
      *require* dual-core, only benefit from it when present.

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
