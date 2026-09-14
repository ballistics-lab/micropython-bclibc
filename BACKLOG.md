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
- Full BLE pairing/passkey flow — `SET_BLE_PASS` is deferred entirely
  until the BLE transport epic (no stub in v1, see Epic 8).

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
      `build_multibc(drag_type, bc_points_buf, out_mach_buf, out_cd_buf) ->
      count`. **Zero-copy on both ends, matching `integrate()`'s
      `traj_buf` convention** — not the boxed-list shape from the first
      draft of this epic (that would allocate ~2×N Python float objects,
      e.g. 160 for an 80-point G7 table, only to immediately re-serialize
      them into `Shot()`'s buffer). `out_mach_buf`/`out_cd_buf` are
      caller-allocated `bytearray(_MAX_DRAG_PTS * 4)` write targets (reuse
      the existing `_MAX_DRAG_PTS=128` constant, no new size constant
      needed); the function writes packed float32 directly via a new
      `_wrf()` helper (write-side mirror of the existing `_rdf()`) and
      returns only the written count. **Must work against both reference
      tables, selected by `drag_type`** — `DRAG_G1` uses
      `g1_mach`/`g1_cd`/`G1_N` (79 points), `DRAG_G7` uses
      `g7_mach`/`g7_cd`/`G7_N` (82 points), both from `src/drag_tables.h`.
      The two tables are different lengths, so the returned `count` varies
      by `drag_type` — callers must use it, not assume either table's
      size; both fit comfortably under the shared `_MAX_DRAG_PTS=128`
      output-buffer cap regardless. Algorithm: sort BC points by Mach,
      linear-interpolate the BC ratio at each reference-table Mach value
      (clamped at the ends, matching py-ballisticcalc's
      `linear_interpolation`), divide the reference Cd by that ratio.
      `bc` is always fed into `Shot()` as `1.0` for the resulting curve —
      it cancels out of `drag_by_mach`'s `Cd(mach) * K / bc` algebraically,
      so `sectional_density`/weight/diameter do not need to be ported for
      this.
- [ ] Register in both the natmod (`mpy_init`) and usermod
      (`bclibc_module_globals_table`) code paths, matching the existing
      functions' pattern.
- [ ] Python wrapper `MultiBC(bc_points, drag_type=DRAG_G7)` in
      `src/tiny_bclibc.py`: packs `bc_points` into a buffer (unchanged —
      already zero-copy-style on this side), allocates the two output
      buffers, calls the native function, returns
      `(mach_buf, cd_buf, count)` with no slicing/copying.
- [ ] `Shot()`'s drag-table packing needs a fast path: when `drag_mach`/
      `drag_cd` are already `bytes`/`bytearray`/`memoryview` (i.e. what
      `MultiBC()` returns), do a direct byte-range copy into the Shot
      buffer instead of the current per-element `uctypes`-struct write
      loop. Keep the existing per-element path for the case where a
      caller hand-builds a plain Python sequence of floats — don't break
      that usage.
- [ ] Test numerical identity against py-ballisticcalc's
      `DragModelMultiBC`, same spirit as `tiny_bclibc/tests/test_identity.cpp`
      — **cover both `DRAG_G1` and `DRAG_G7` as the reference table**, not
      just one; they have different point counts and different Mach
      breakpoints (e.g. G7 has a 0.65 point G1 doesn't), so a G7-only test
      wouldn't catch a G1-specific indexing/length bug.
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
      FIND_ZERO_ANGLE, FIND_APEX, FIND_MAX_RANGE, RESET, IDENT,
      STREAM_START, STREAM_END, ABORT, ACK/NAK/ERROR`. `SET_BLE_PASS` is
      deferred to the BLE transport epic (see Epic 8) — not part of v1.
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
- [ ] **Ack scheme — still open, latency vs. reliability tradeoff not yet
      resolved.** Three candidates on the table:
  - **(a) Y-modem-style windowed ack** (current lean) — reliable, simple
        mental model, but per-block ack RTT could add up over a
        higher-latency transport; needs real numbers (see below) before
        settling on a window size, not just a gut call.
  - **(b) Plain no-ack** — fastest, but a single dropped/corrupt frame
        forces restarting the *entire* stream (nothing to resume from).
  - **(c) Sequence number + gap-triggered `RESEND(from_seq)`** — no ack in
        the normal case, receiver requests a resend only on a detected gap
        or bad CRC; sender resumes from that row (re-run + filtered emit,
        not a full restart). Needs `RESEND` explicitly exempted from the
        Epic 6 "any new frame preempts" rule, or it would abort the very
        stream it's trying to recover.
  - **Transport-specific nuance worth factoring in:** BLE **Indications**
        (as opposed to Notifications) already carry a per-packet ack at
        the GATT stack level — the peripheral cannot send the next
        indication until the central acks the previous one. If the BLE
        transport uses Indications, app-level per-block acking (a) is
        largely redundant *on that transport specifically* — the latency
        concern may be much smaller there than assumed. USB CDC/UART have
        no such built-in guarantee, so still need an app-level scheme
        regardless of what's chosen for BLE. This reopens option (c) from
        the original list ("different ack strategy per transport") as
        possibly the right shape, rather than forcing one scheme across
        all three transports.
  - Needs actual RTT numbers per transport (USB CDC, UART at target baud,
        BLE connection interval) before picking a window size or deciding
        whether (a)'s latency worry is real in practice. Not blocking
        Epic 2/3/4/6 work — can stay open while those proceed.
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
- [x] **Resolved — mechanism chosen conditionally on core availability,**
      rather than one mechanism everywhere:
  - **Dual-core (the primary path — all three current targets are
        multi-core: RP2040, RP2350, ESP32-S3):** interrupt = **kill and
        relaunch the worker core/task**, not `setjmp`/`longjmp`. The
        entire execution context is discarded rather than partially
        unwound, so there's no unwind-safety question to verify per
        platform — this **demotes** the earlier "verify `longjmp`-from-ISR
        on ESP32-S3" risk, since it's no longer on the primary path for
        any of the three targets in scope.
    - RP2040/RP2350: pico-sdk `multicore_reset_core1()` +
          `multicore_launch_core1()`. **Open:** go through MicroPython's
          `_thread` module (portable across ports, but doesn't expose a
          documented kill/reset call) vs. drop to the raw SDK calls from a
          small helper in `tiny_bclibc_mp.c` for reliable kill semantics.
    - ESP32-S3: FreeRTOS `vTaskDelete()` + `xTaskCreatePinnedToCore()`.
    - ⚠️ **New risk, replacing the longjmp-safety question:** killing the
          worker core/task while it holds a shared lock (MicroPython's
          GIL-equivalent / GC lock on a shared-heap dual-core port) can
          deadlock the other core — FreeRTOS's `vTaskDelete()` does **not**
          release mutexes held by the deleted task, and the same class of
          problem likely applies to RP2040's shared-heap threading model.
          Mitigation: the "killable window" must be exactly the pure-C
          `tiny_bclibc` call (already no-heap/no-lock by design — see
          `ShotHolder`, caller-owned buffers, confirmed earlier) — needs
          verifying per port whether calling a native/usermod C function
          from the worker core already releases the shared interpreter
          lock for the call's duration, or whether that needs doing
          explicitly before the call.
    - The dispatcher (core0) is responsible for emitting the
          `INTERRUPTED` response for whatever generation it just killed —
          the killed worker never gets to respond itself, so core0 must
          track which command generation was in flight and reply on its
          behalf.
  - **Single-core (not needed for any of the three current targets, kept
        as documented fallback for a hypothetical future single-core
        target):** `setjmp`/`longjmp` contained in
        `micropython-bclibc`'s binding layer — wrap each blocking call
        (`find_zero_angle`, `find_apex`, `find_max_range`, `integrate`,
        `integrate_at`) with `setjmp()`, trigger `longjmp()` from the
        CDC1 RX ISR on a preempting frame; single global `jmp_buf` given
        the no-queue rule. Contract: once `setjmp()` returns nonzero, the
        wrapper treats any output buffer as garbage and returns
        `INTERRUPTED` without touching it. (Full detail preserved from
        the earlier draft of this epic — revisit only if a single-core
        target is actually added to scope.)
  - **Unix port** (relevant — it's the "virtual module" deliverable named
        in the original project idea, not just a test convenience): no
        real cores, `_thread` there wraps POSIX pthreads.
        `pthread_cancel()` is **not** a good fit as-is — its default
        deferred cancellation type only fires at cancellation points
        (mostly blocking syscalls), and `tiny_bclibc`'s RK4 loop is pure
        computation with none, so deferred cancel would simply never
        interrupt it without inserted `pthread_testcancel()` checkpoints
        — the same cooperative-checkpoint problem this epic is avoiding
        for the embedded targets, resurfacing here.
        `PTHREAD_CANCEL_ASYNCHRONOUS` avoids that but carries the same
        risk class as killing an embedded worker mid-lock, plus it can
        land mid-libc-call. **Recommended default:** `pthread_kill(tid,
        SIGUSR1)` from the dispatcher thread, worker's signal handler
        calls `siglongjmp` (the async-signal-safe pair — plain
        `setjmp`/`longjmp` is not safe to use from a signal handler) —
        functionally the same shape as the single-core fallback above,
        using the correct POSIX primitives instead of an MCU ISR.
        **Alternative worth checking:** if the unix port's `os` module
        exposes `fork()` (not confirmed), a forked worker process +
        `SIGKILL` sidesteps the shared-lock risk entirely (separate
        address space, no shared MicroPython heap/GIL to corrupt) — at
        the cost of needing IPC (socket/pipe) instead of shared buffers
        for the `Shot`/result data. Bigger change; only worth it if fork
        turns out to be available and the isolation is wanted for other
        reasons too.
- [ ] `INTERRUPTED` response status for whatever got preempted (distinct
      from the normal response to the command that preempted it).
- [ ] `INTEGRATE` (streamed) keeps its independent cooperative hook
      regardless of which mechanism above is used: `mp_stream_cb` returns
      `TINY_BCLIBC_TERM_HANDLER_STOP` when the Python callback returns
      truthy — a cheap early-exit check worth keeping even inside a
      dual-core worker, before falling back to a hard kill.

## Epic 7 — Second core (where supported)

- [x] **Status update:** no longer just a latency optimization — per
      Epic 6, dual-core kill/relaunch is now the *primary* abort
      mechanism for all three current targets (RP2040, RP2350, ESP32-S3
      are all multi-core), so this epic is load-bearing, not optional.
      Sequence it together with Epic 6, not after it.
- [ ] Move command execution (the calls into `tiny_bclibc`) to a second
      core/task. There's existing precedent in-repo to build from:
      `natmod/examples/tiny_bclibc_natmod_test_2core.py` and
      `..._bench_2core.py`.
- [ ] Inter-core channel: core0 tracks the current command generation and
      the worker's handle (core1 launch state on RP2040/RP2350, task
      handle on ESP32-S3) so it can kill + relaunch on a preempting frame
      (Epic 6), plus (for streaming) a ring buffer of completed rows from
      the worker back to core0.
- [ ] Single-core fallback (Epic 6's `setjmp`/`longjmp` model) documented
      but **not currently needed** — no target in the phase-1 list lacks a
      second core. Keep the protocol layer from *requiring* dual-core in
      principle, but don't over-invest in the single-core path until an
      actual single-core target shows up.

## Epic 8 — Commands on top of existing structures (no a7p)

- [ ] `LOAD_PROFILE` — accepts a wire payload that maps directly onto
      `Shot`/`Config` (the same `_SHOT_DESC`-style packed layout already
      used internally), not an a7p blob.
- [ ] `RESET` — needs a definition: clear cached `Shot` state, soft-reset
      the MCU, or both under different codes?
- [x] **Resolved:** `SET_BLE_PASS` is deferred entirely until the BLE
      transport epic — no stub in v1, to avoid dead code in the meantime.
- [ ] `IDENT` — version + capabilities; minimum viable version is just the
      existing `bc.version()` passthrough.
