# Ballistic Co-Processor (BCP) — Implementation Backlog

Working backlog for turning `micropython-bclibc` into a standalone "ballistic
co-processor" (BCP) firmware application: a stateless-except-cached-profile
module that answers `LOAD_PROFILE` / `LOAD_CONDITIONS` / `INTEGRATE` /
`INTEGRATE_AT` / etc. requests over a framed command protocol, instead of
being used purely as a library from Python application code.

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

- [x] **Resolved — name: BCP (Ballistic Co-Processor), flag
      `BCLIBC_BCP`** (mirrors the existing `BCLIBC_BUILD_NATMOD` switch in
      `src/tiny_bclibc_mp.c`). Renamed from the earlier `BCLIBC_RT`: "RT"
      was meant as "runtime", but in embedded it reads as real-time (this
      backlog itself says "real-time-safe" in Epic 3), and "runtime" in
      MicroPython already means the interpreter (`py/runtime.c`). "Co-
      processor" is the established term for exactly this shape — a
      separate MCU serving a host over a framed protocol, as with
      OpenThread/Zigbee's NCP/RCP. BCE/BPE were rejected because "engine"
      already means the integrator in py-ballisticcalc
      (`RK4IntegrationEngine` etc.), BCM because it is Broadcom's chip
      prefix (Raspberry Pi SoCs).
- [x] Default: **off** — a plain usermod build for non-BCP firmware carries
      neither the C marker nor the frozen application.
- [x] **Resolved:** the application lives in `src/`, alongside
      `tiny_bclibc.py`/`tiny_bclibc_mp.c` — no new top-level directory, no
      separate repo. Its `.py` files are only **frozen** into the firmware
      image when `BCLIBC_BCP=1`. Placeholder `src/bclibc_bcp.py` for now
      (imports the C marker, nothing else).
- [x] **Implemented — one environment variable, `BCLIBC_BCP=1`, keys both
      halves.** `make BCLIBC_BCP=1 ...` or `BCLIBC_BCP=1` in the
      environment:
    - **Frozen `.py`:** `usermod/manifest.py` reads
          `os.environ["BCLIBC_BCP"]` and conditionally
          `freeze()`s `bclibc_bcp.py`. Not a `--var` as first planned:
          `makemanifest.py`'s `-v` variables are path substitutions only, a
          manifest cannot branch on one. GNU make exports command-line
          variables to recipe environments itself, so `make BCLIBC_BCP=1`
          reaches `makemanifest.py` with no extra plumbing.
    - **C:** `usermod/micropython.mk` adds `-DBCLIBC_BCP=1` to
          `CFLAGS_USERMOD`; `usermod/micropython.cmake` reads
          `$ENV{BCLIBC_BCP}` and adds it as an INTERFACE definition **and**
          to `MICROPY_CPP_DEF_EXTRA` — `py/mkrules.cmake`'s QSTR
          preprocessing does not see usermod INTERFACE definitions, so
          without the second line any qstr under `#ifdef BCLIBC_BCP` is
          undeclared (live-caught on RPI_PICO2: `MP_QSTR_RT undeclared`).
    - **Marker:** `_tiny_bclibc.BCP = True` (usermod table only, under
          `#ifdef BCLIBC_BCP`); `bclibc_bcp.py` imports it, so a firmware
          with the `.py` half but not the C half fails at import instead of
          running half-built.
    - **Rejected alternative:** a separate `manifest_bcp.py` pulling in the
          C half via `c_module()`. Works on CMake, but on Make ports
          `py/manifest.mk` (v1.29.0) merges `c_module()` paths with a plain
          `USER_C_MODULES := ...`, which GNU make ignores whenever
          `USER_C_MODULES` is on the command line — as README documents and
          cibuildmp invokes it — so the C half was silently dropped.
    - **Switching the flag needs a fresh build directory:** Make does not
          rebuild objects on a `CFLAGS` change, CMake reads the environment
          at configure time only. A stale Make object is exactly what the
          marker import caught during bring-up.
    - **Verified:** unix (Make) with and without the flag —
          `_tiny_bclibc.BCP`/`import bclibc_bcp` present only with it,
          `tests/test_bclibc.py` 18/18 PASS both ways; rp2 RPI_PICO2 (CMake)
          with the flag both from the environment and from the make command
          line — `BCLIBC_BCP=1` in `flags.make`, `MP_QSTR_BCP` generated,
          `bclibc_bcp` in `frozen_content.c`.
- [x] **cibuildmp (v0.7.3):** no generic environment passthrough into its
      Docker containers, but `extra-make-args` rides the make command line
      for every usermod port (rp2/esp32 included), so
      `CIBMP_EXTRA_MAKE_ARGS="BCLIBC_BCP=1"` works with no cibuildmp change.
      Verified in Docker: `v1.29.0-qemu-MPS2_AN385` —
      `bclibc_module_globals_table` 360 B (352 without the `BCP` entry) and
      `bclibc_bcp` frozen; `v1.29.0-rp2-RPI_PICO2` — `bclibc_bcp` frozen
      (no symbols in a `.uf2` to check the C half; same make-command-line
      path as the local rp2 check above).
- [ ] CI job for BCP builds (`usermod.yml`) — **deferred until Epic 3/4
      lands real code** (the frame parser is testable on unix). With only a
      placeholder app there is nothing meaningful to run, and the flag
      plumbing has no reason to break before then. When adding it: the
      environment form `CIBMP_EXTRA_MAKE_ARGS` **replaces** the config's
      `extra-make-args` including `[override]`s (armhf would lose
      `LDFLAGS_EXTRA=-static`), and a BCP build has the same identifier
      and `mpyhouse/` file name as the plain one — separate job, distinct
      artifact name. Whether a multi-token `CIBMP_EXTRA_MAKE_ARGS` is split
      correctly is not verified yet.
- [ ] Entry point: a frozen `main.py` does auto-run on rp2/esp32
      (`pyexec_file_if_exists()` checks frozen modules first), but it then
      **shadows** any filesystem `main.py`, and the REPL only starts after
      `main.py` returns — so it must start the dispatcher in the background
      and return (Epic 4's "CDC1 never blocks the CDC0 REPL"). Plan: keep
      the app importable (`bclibc_bcp`) and add a thin frozen
      `main.py` (`import bclibc_bcp; bclibc_bcp.start()`) under the same
      flag once Epic 4 has something to start.

## Epic 2 — Multi-BC native binding

- [x] **Implemented and verified.** `mp_bclibc_build_multibc()`,
      `MultiBC()` wrapper, `Shot()` fast byte-copy path, and G1/G7 identity
      + interpolation + end-to-end tests are on this branch
      (`src/tiny_bclibc_mp.c`, `src/tiny_bclibc.py`, `tests/test_bclibc.py`).
      **Actually built and run this session** (installed
      `gcc-arm-none-eabi` + `pyelftools`/`ar` via apt/pip, cloned
      `micropython`, built `mpy-cross` and the unix port from source):
    - **x64 (unix):** natmod compiled, linked, and `tests/test_bclibc.py`
          **executed for real** against it — all tests pass, including
          all 6 new `MultiBC` cases. The interpolation test's hand-computed
          expected value (`0.3803 / 1.2 = 0.31692`) matched the actual
          runtime output exactly; G1/G7 counts matched (79/84 — see the
          G7 table correction below).
    - **RP2040 (armv6m) / RP2350 (armv7emsp):** natmod compiles and links
          into a valid `.mpy` (confirmed via real cross-builds, not just
          reasoning) — see the size numbers below — but **not executed**
          (no RP2040/RP2350 hardware or Cortex-M QEMU available in this
          session).
    - **ESP32-S3 (xtensawin):** not attempted — no `xtensa-esp32s3-elf-`
          toolchain available via apt; would need Espressif's own
          toolchain release.
    - **Measured ROM/RAM impact** (baseline `main` vs this branch, real
          `size`/file-size diffs, not estimates):

      | Target | native `.text` | full `.mpy` | RAM |
      |---|---|---|---|
      | RP2040 (armv6m) | 28132 → 28836 (**+704 B**) | 33142 → 34321 (**+1179 B**) | +0 (bss unchanged) |
      | RP2350 (armv7emsp) | 22340 → 22988 (**+648 B**) | 27345 → 28468 (**+1123 B**) | +0 (bss unchanged) |
      | ESP32-S3 | not measured — expect same order of magnitude | | |
- [x] `mp_bclibc_build_multibc()` in `src/tiny_bclibc_mp.c`:
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
      `g7_mach`/`g7_cd`/`G7_N` (84 points — see the table correction
      below), both from `src/drag_tables.h`. The two tables are different
      lengths, so the returned `count` varies by `drag_type` — callers
      must use it, not assume either table's size; both fit comfortably
      under the shared `_MAX_DRAG_PTS=128` output-buffer cap regardless.
      Algorithm: sort BC points by Mach, linear-interpolate the BC ratio
      at each reference-table Mach value (clamped at the ends, matching
      py-ballisticcalc's `linear_interpolation`), divide the reference Cd
      by that ratio. `bc` is always fed into `Shot()` as `1.0` for the
      resulting curve — it cancels out of `drag_by_mach`'s
      `Cd(mach) * K / bc` algebraically, so `sectional_density`/weight/
      diameter do not need to be ported for this.
- [x] Register in both the natmod (`mpy_init`) and usermod
      (`bclibc_module_globals_table`) code paths, matching the existing
      functions' pattern.
- [x] Python wrapper `MultiBC(bc_points, drag_type=DRAG_G7)` in
      `src/tiny_bclibc.py`: packs `bc_points` into a buffer (unchanged —
      already zero-copy-style on this side), allocates the two output
      buffers, calls the native function, returns
      `(mach_buf, cd_buf, count)` with no slicing/copying.
- [x] `Shot()`'s drag-table packing needs a fast path: when `drag_mach`/
      `drag_cd` are already `bytes`/`bytearray`/`memoryview` (i.e. what
      `MultiBC()` returns), do a direct byte-range copy into the Shot
      buffer instead of the current per-element `uctypes`-struct write
      loop. Keep the existing per-element path for the case where a
      caller hand-builds a plain Python sequence of floats — don't break
      that usage.
- [x] **Done — real cross-implementation check against py-ballisticcalc's
      actual `DragModelMultiBC()`, not just the hand-verified substitute.**
      Ran py-ballisticcalc itself against a real multi-point BC profile
      (`examples/hor_375ct_390_atip.py`, 375 CheyTac, multiple BC/Mach
      breakpoints) to get `DragModelMultiBC()`'s real output curve, then
      diffed it point-by-point against `build_multibc()`'s output for the
      same input, mirroring what `tiny_bclibc/tests/test_identity.cpp`
      does for the rest of the engine.
      **This caught a genuine, previously-unknown bug**, not just
      validated the interpolation math: the built-in G7 table in
      `src/drag_tables.h` was missing two supersonic-tail breakpoints
      (Mach 2.85, 2.95 — 82 points instead of 84) and had drifted CD
      values for every point from Mach 2.80 through 5.00, up to +0.0065
      absolute (~3.7% relative error at Mach=4.60) versus
      `py_ballisticcalc.drag_tables.TableG7`. This affected **every**
      G7-based calculation in the library, not just multi-BC — it was
      only surfaced here because multi-BC output is sensitive to the
      full table shape at high Mach. G1 was independently verified exact
      against `TableG1` (79/79 points, zero diff) and was left unchanged.
      Fixed `src/drag_tables.h`'s G7 tail wholesale from
      `TableG7` (commit `45cef094564f063f78ff2ea8d9b925ab86c5c5b9`) and
      updated `tests/test_bclibc.py`'s own stale hardcoded G7 arrays to
      match. Reran both checks after the fix: **exact match** against
      py-ballisticcalc (max relative error 1.2e-7, x64 unix build), and
      the full `test_bclibc.py` suite passes with **0 failures**.
- [x] **Scope decision:** v1 reference table is G1/G7 only (what's already
      in ROM). py-ballisticcalc's `DragModelMultiBC` accepts an arbitrary
      reference `drag_table`; not porting that for now — flag if a
      custom-reference base turns out to be needed.

## Epic 3 — Command/response frame

- [x] **Resolved — wire format `00 COBS(packet) 00`, no `start_byte`, no
      `len`** (supersedes the earlier `<start_byte><cmd:1><len:2>...`
      draft). COBS guarantees no `0x00` inside the encoded bytes, so the
      delimiter alone is the frame boundary — a `start_byte` inside the
      COBS payload adds nothing, and the frame length is known once the
      closing `0x00` arrives. Failure cases:
    - **Lost frame start:** the decoder collects the tail up to the next
          `0x00`, CRC fails, the frame is dropped; the next frame starts
          right after that `0x00` and arrives intact. Same loss as with a
          `start_byte`, without its false-sync risk.
    - **Lost delimiter:** the leading **and** trailing `0x00` put two
          zeros between consecutive frames, so losing one still separates
          them. An empty frame (`00 00`) is ignored.
    - **Garbage before the first frame** (host connects mid-stream, line
          noise): the leading `0x00` resets the decoder.
    - **No `0x00` within the max frame size:** discard, wait for the next
          `0x00` — the RX buffer stays bounded.
    - **What `len` would have caught** (merged/truncated frame passing
          CRC16, ~1/65536): covered by a **per-command payload size check**
          instead — fixed sizes for `FIND_*`/`INTEGRATE_AT`, exactly
          the count-derived size for `LOAD_PROFILE`, plus min packet size and
          known `type` (see the array-count rule below).
    - On USB CDC byte loss is practically limited to host buffer overflow
          or reconnect (bulk transfers have their own CRC + retry); these
          cases matter mostly for the later UART/BLE transports.
- [ ] **Proposed, not confirmed — packet header (4 B, keeps the payload
      4-aligned for `uctypes.struct` over the RX buffer):**
      `type:u8 | seq:u8 | status:u8 | rsvd:u8 | payload | crc16:u16`,
      little-endian. `type` = command, `cmd | 0x80` in a response; `seq`
      set by the host and echoed back (response matching, Epic 6
      generation for `INTERRUPTED`, Epic 5 option (c) `RESEND`); `status`
      0 in requests. **`LOAD_PROFILE`/`LOAD_CONDITIONS` now have their own
      wire layouts, distinct from the internal `_SHOT_DESC` buffer** (see
      the split above and Epic 8) — the dispatcher unpacks each into the
      persistent internal `Shot` buffer's existing (non-contiguous)
      offsets rather than writing it in place. Max packet
      ≈ 1.1 KB (`LOAD_PROFILE`'s drag table, up to 128 pts: 64 B fixed +
      128·8 = 1088 B + header + CRC) → fixed 1536 B RX buffer still covers
      it with margin.
- [x] **Resolved — array element counts:** every variable-length part is
      preceded by its count at a fixed position in the payload; the
      payload length (known from the frame) must **equal** the size
      computed from the counts. Receiver order: counts ≤ caps → compute
      expected size → `==` payload length. Reply `ERR_BAD_ARG` on a count
      over its cap, `ERR_BAD_SIZE` on a size mismatch.
    - **`LOAD_PROFILE`** (own wire layout, no winds — see Epic 8):
          `drag_type:u8, drag_count:u16` (≤ 128) precede the drag table.
          Expected size = fixed profile fields +
          `(drag_type == CUSTOM ? drag_count·8 : 0)` — `drag_count` is
          ignored for G1/G7.
    - **`LOAD_CONDITIONS`** (own wire layout — see Epic 8): `wind_count:u8`
          (≤ 16) precedes the wind array. Expected size = fixed
          atmosphere/geometry fields + `wind_count·16`.
    - **Stream `MORE` frames:** `row_idx:u16, count:u8, rsvd:u8,
          rows[count]`, size exactly `4 + count·traj_row_size` (explicit
          `count` as the cross-check, even though it is derivable).
    - **Strings** (`IDENT` version): `u8` length prefix.
    - **The existing C parser is not strict enough for the wire**
          (`src/tiny_bclibc_mp.c`, Shot unpacking): it checks
          `bi.len < needed` (so trailing bytes from a merged/truncated frame
          pass), and silently clamps `wind_count` to 16 / `drag_count` to
          128 — with `wind_count > 16` the drag offset is still computed
          from the unclamped count, i.e. an inconsistent profile instead of
          an error. Fine for Python callers; the dispatcher must validate
          strictly before handing the buffer to C.
- [ ] CRC16 over the whole packet before CRC. Variant not fixed yet —
      proposed CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF), table-driven.
- [ ] Bad-CRC frames are dropped silently (their `seq` cannot be trusted,
      so there is nothing to reply to); host relies on a timeout. Optional
      drop counter reported via `IDENT`.
- [x] **Resolved:** `FIND_APEX` and `FIND_MAX_RANGE` are in the v1 command
      set (both already natively bound).
- [ ] Command enum: `LOAD_PROFILE, LOAD_CONDITIONS, INTEGRATE,
      INTEGRATE_AT, FIND_APEX, FIND_MAX_RANGE, RESET, IDENT, STREAM_START,
      STREAM_END, ABORT, ACK/NAK/ERROR`. **`FIND_ZERO_ANGLE` dropped from
      the wire command set** — see Epic 8 (now internal-only,
      auto-triggered by `LOAD_PROFILE`/`LOAD_CONDITIONS`). **`RESET`
      redefined, not dropped** — see Epic 8: an application soft-reset,
      not a data-clearer and not an MCU reboot. `SET_BLE_PASS` is deferred
      to the BLE transport epic (see Epic 8) — not part of v1.
- [x] **Resolved — `LOAD_PROFILE` split from `LOAD_CONDITIONS`**
      (supersedes "`LOAD_PROFILE` = the `Shot` buffer byte-for-byte"
      below — see Epic 8 for the field-level breakdown). Rationale: the
      two change at very different rates and gain nothing from being one
      message —
      rifle/ammo/zero (`LOAD_PROFILE`) is set up once per session, while
      wind/atmosphere/shot-geometry (`LOAD_CONDITIONS`) can be updated
      every few shots as the field environment changes. Bundling them
      meant resending ~1.4 KB just to push a new wind reading. Split max
      sizes: `LOAD_PROFILE` ≈ 1.1 KB (dominated by the drag table, up to
      128 pts), `LOAD_CONDITIONS` ≈ 300 B (dominated by winds, up to 16).
      `INTEGRATE`'s own request frame was already thin (`_REQ_DESC`, 16 B:
      `range_limit_ft/range_step_ft/time_step/filter_flags`) and needs no
      change — it already carries only per-call parameters, not shot
      data.
      **Proposed, not confirmed:** fold `ACK/NAK/ERROR` into the header's
      `status` (`OK` / `MORE` / `INTERRUPTED` / `ERR_*`) instead of
      commands, and drop `STREAM_START` — `INTEGRATE` itself streams
      (`MORE` frames `row_idx:u16, count:u8, rsvd:u8, rows[count]`, then a
      final `OK` with `total:u32, reason:i32`). `IDENT` must report
      `real_size` / `traj_row_size` (64 B float vs 124 B double) since the
      payload layout is effectively the ABI.
- [ ] Response frame: same shape, status code distinguishes
      `OK` / `ERR` / `INTERRUPTED`.
- [ ] **Open:** does a cheap command (`IDENT`) preempt a running
      computation too, or does core0 answer it without touching the
      worker? Lean: the latter, otherwise `IDENT` mid-`INTEGRATE` kills it.

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

- [x] **Resolved — no command queue.** The co-processor never queues work:
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

- [x] **Resolved — `LOAD_PROFILE`/`LOAD_CONDITIONS` split** (not an a7p
      blob either way — the fields below still map onto `_SHOT_PROPS_DESC`
      / `_CFG_DESC`, just regrouped by how often each changes):
    - **`LOAD_PROFILE`** — rifle + ammo + solver tuning + the zero
          *distance* (not the angle — see below), cached until the next
          `LOAD_PROFILE` or `RESET`:
          `bc, weight_grain, diameter_inch, length_inch,
          muzzle_velocity_fps, sight_height_ft, twist_inch` (bullet/rifle),
          `zero_distance_ft` (**replaces `barrel_elevation_rad`** — see
          below), `config` (`step_multiplier, zero_finding_accuracy,
          minimum_velocity, maximum_drop, gravity_constant,
          minimum_altitude, max_iterations`), `drag_type` + drag table
          (G1/G7 selector or custom `mach/cd` points, ≤ 128 — see the
          array-count rule above). ≈ 1.1 KB max (dominated by a full
          custom drag table).
    - **`LOAD_CONDITIONS`** — atmosphere + shot geometry + wind, expected
          to change every few shots as the field environment shifts:
          `temp_c, pressure_hpa, altitude_ft, humidity` (atmosphere),
          `look_angle_rad, barrel_azimuth_rad, cant_angle_rad` (shot
          geometry/pitch), `latitude_deg, azimuth_deg` (Coriolis), plus
          the wind array (≤ 16 — see the array-count rule above). ≈ 300 B
          max. **Not loaded yet** at first `INTEGRATE`/`FIND_*`: falls
          back to `Shot()`'s existing Python-side defaults (ICAO standard
          atmosphere, no wind, zero cant/look angle) — same defaults,
          just applied on-device instead of by the caller.
    - **Resolved — internal `Shot` layout stays untouched.** `_SHOT_DESC`
          interleaves profile and condition fields inside the same
          68-byte props block (e.g. `bc` at offset 0, `temp_c` at 28,
          `barrel_elevation_rad` at 48), so the wire split does not map
          onto two contiguous halves of it — and it shouldn't try to:
          `_SHOT_DESC`/`_SHOT_PROPS_DESC` is already tested and used as-is
          by non-BCP callers. The dispatcher keeps one persistent internal
          `Shot` buffer and scatters each `LOAD_*`'s wire fields to that
          buffer's existing offsets, rather than reordering the internal
          struct to match the wire grouping.
    - **Resolved — `FIND_ZERO_ANGLE` is not a wire command.** It stays an
          internal function only, called automatically by the dispatcher
          — not something a client invokes directly. `LOAD_PROFILE`
          carries `zero_distance_ft`, not a pre-solved angle: the
          elevation needed to hit that distance depends on the current
          atmosphere (air density affects drop), so it can't be supplied
          by the client once and cached verbatim — it has to be
          *recomputed* whenever either half of the picture changes.
          Dispatcher behavior: after a `LOAD_PROFILE` (against whatever
          conditions are cached, or the defaults above if none yet) *and*
          after every `LOAD_CONDITIONS` (against the cached profile's
          `zero_distance_ft`), internally call `find_zero_angle()` and
          store the result into the internal `Shot`'s
          `barrel_elevation_rad` before replying `OK`. **Consequence:** a
          zero-solve failure (no bracket, no convergence — see
          `engine.h`'s `find_zero_angle` error paths) must now surface as
          an error status on the triggering `LOAD_PROFILE`/
          `LOAD_CONDITIONS` response, since there is no separate
          `FIND_ZERO_ANGLE` response to carry it. **Resolved:** the `OK`
          response to both `LOAD_PROFILE` and `LOAD_CONDITIONS` echoes
          back the solved `barrel_elevation_rad:f32` as telemetry — cheap
          (4 B), and it's the only way the host learns the current zero
          without a redundant query round-trip.
- [x] **Resolved — `RESET` = application soft-reset, not a data-clearer
      and not an MCU reboot.** Corrects the earlier "drop it, a full
      reload already fixes any stuck state" framing — that argument
      addressed only *targeted clearing* (making `LOAD_PROFILE` alone, or
      `LOAD_CONDITIONS` alone, act as if nothing were cached), which is
      indeed redundant with a full overwrite. `RESET`'s actual job is
      different: **collapse the entire dispatcher back to its
      power-on-equivalent state in one command**, without the client
      needing to know or resupply anything:
    - Discards cached profile *and* cached conditions/zero (back to "no
          profile loaded" — `INTEGRATE`/`FIND_*` before the next
          `LOAD_PROFILE` should error, not run on stale data).
    - Resets dispatcher bookkeeping: current command generation/seq
          tracking (Epic 6), any in-progress stream state (Epic 5), drop
          counters (Epic 3).
    - Implies the same preemption `ABORT` already does — a `RESET` while
          something is running must kill/relaunch the worker first (Epic
          6's rule), then clear state; it is not a *replacement* for
          `ABORT`, it is a superset that also wipes cached data.
    - Explicitly **not** `machine.reset()`/an MCU reboot — that stays a
          CDC0 REPL/firmware-update concern, out of scope for the BCP
          command set.
- [x] **Resolved:** `SET_BLE_PASS` is deferred entirely until the BLE
      transport epic — no stub in v1, to avoid dead code in the meantime.
- [ ] `IDENT` — version + capabilities; minimum viable version is just the
      existing `bc.version()` passthrough.
