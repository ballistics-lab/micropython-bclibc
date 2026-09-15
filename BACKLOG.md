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
      and return (Epic 4's "CDC1 never blocks the CDC0 REPL"). **Shape,
      per Epic 3/6/7's C-dispatcher resolution:** `bclibc_bcp.py` stays
      thin plumbing, not the dispatcher itself — it constructs/configures
      the transport object (CDC1 or UART), optionally picks which core to
      run on (Epic 7), and hands the transport object to one C entry point
      that owns the whole read/decode/dispatch/write loop from there.
      Something like `import bclibc_bcp; bclibc_bcp.start(cdc1)` where
      `start()` is a thin Python function whose entire body is
      constructing the transport and calling into the native module —
      no per-frame Python code in the running loop at all.

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

> Byte-level layout (packet header, per-command struct fields, status
> codes) lives in [`PROTOCOL.md`](PROTOCOL.md) -- kept in one place instead
> of duplicated across backlog bullets. This epic tracks the *decisions*;
> `PROTOCOL.md` is the *reference*.

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
      0 in requests. **`LOAD_PROFILE`/`LOAD_CONFIG`/`LOAD_CONDITIONS` now
      have their own wire layouts, distinct from the internal
      `_SHOT_DESC` buffer** (see the split above and Epic 8) — the
      dispatcher unpacks each into the persistent internal `Shot`
      buffer's existing (non-contiguous) offsets rather than writing it
      in place. Max packet
      ≈ 1.0 KB (`LOAD_PROFILE`'s drag table, up to 128 pts: 36 B fixed +
      128·8 = 1060 B + header + CRC) → fixed 1536 B RX buffer still covers
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
    - **`LOAD_CONFIG`** (own wire layout — see Epic 8): no variable-length
          part, no count field — expected size is just its fixed 28 B.
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
- [x] **Resolved — CRC16/CCITT-FALSE (poly 0x1021, init 0xFFFF), 256-entry
      table-driven**, over the whole packet before the CRC field.
      Implemented and tested in `src/bcp_frame.py` (`tests/test_bcp_frame.py`
      — known-answer vector `crc16(b"123456789") == 0x29B1`, the standard
      catalogue check value for this variant). **Measured on real
      hardware, not assumed** — Waveshare RP2040-Zero (RP2040), MicroPython
      1.29.0, plain bytecode (no `@native`/`@viper`), via `mpremote run`:

      | variant | µs/byte | vs. table256 |
      |---|---|---|
      | 256-entry table (chosen) | ~12.6 | 1× |
      | 16-entry nibble table | ~24.9 | 2× slower |
      | bitwise, no table | ~87.5 | 7× slower |
      | (for comparison) COBS encode | ~17.5 | same order as CRC |

      256-entry wins outright on speed, so the only real cost worth
      minimizing is the table's **RAM** footprint (not ROM/flash — the
      table is computed once at import, not a frozen constant, so it
      lives on the heap either way; see the follow-up below). Worst-case
      framing cost (`LOAD_PROFILE`, ~1.0 KB, COBS + CRC together) ≈ 30 ms
      — fine since that frame is sent once per rifle/ammo setup, not per
      shot; small frames (`Request`, 16 B) cost well under 1 ms,
      negligible next to the actual integration compute time.
- [x] **Resolved — CRC table stored as `array('H', ...)`, not a plain
      `list`.** A `list` of 256 ints is really a 256-pointer object array;
      measured on the same RP2040-Zero: **1040 B** RAM for the list vs
      **528 B** for a packed `array('H', ...)` holding the same 256
      values — same lookup, ~5% slower (16855 vs 16037 µs for a 1400 B
      CRC, i.e. noise next to the table-size choice above). Applied in
      `src/bcp_frame.py`, re-verified for real on-device (not just the
      isolated micro-benchmark): imported the updated module over
      `mpremote`, `crc16(b"123456789")` still `0x29B1`, `build_frame`/
      `FrameDecoder` round-trip still correct. **Not pursued further:**
      going all the way to a zero-RAM table (a `bytes` literal that a
      *frozen* build keeps in flash instead of computing at import) would
      need hand-verified hex-table source instead of the current 6-line
      poly loop computed at runtime — real transcription risk (this
      session already hit exactly that mistake once, with the COBS test
      vectors) for savings that don't matter yet at this scale. Revisit
      only if on-device RAM actually gets tight.
- [x] **Resolved — implementation language is C, not Python.** MicroPython's
      job is transport plumbing only (open/configure UART or CDC1, feed
      bytes to/from the parser) — **not** COBS, CRC, frame validation, or
      dispatch. All of that belongs in C next to `tiny_bclibc_mp.c`, same
      as the engine itself. Reasons, in order of weight:
    - **C already builds on all three targets today** (Epic 2's real
          cross-builds), closing the one open portability question the
          Python-side exploration below kept running into: whether
          `@micropython.viper` is even available/mature on ESP32-S3's
          Xtensa port (only ever tested here on rp2/ARM) — moot in C.
    - **The numbers justify it, not just the principle.** `benches.md`
          (RP2350, `armv7emsp` hardware-FPU build): `integrate()` 1 km/10 m
          steps = 101 rows in 15.99 ms ⇒ ~158 µs/row. Packed 4-to-a-frame
          (`INTEGRATE_FAST`'s `MORE` frame, 68 B), the solver produces
          those 4 rows in ~633 µs. Plain-Python `build_frame` (COBS+CRC)
          on that same 68 B costs **~2253 µs** — ~3.6× *slower* than the
          solver that's supposedly the bottleneck. On the production tier
          this backlog is actually targeting, naive Python framing is the
          bottleneck, not the engine.
    - Below is the full exploration that led here (viper, DMA-hardware
          CRC, RP2040 vs. RP2350 economics) — kept for the numbers, not as
          a proposal to actually ship any of these Python-level tricks.
- [x] **Corrected — `src/bcp_frame.py` is not kept on as a permanent
      "oracle."** The earlier framing (a maintained parallel Python
      implementation, kept around specifically to diff the C
      implementation's output against) doesn't hold up: nothing here
      actually needs a second maintained implementation to test against.
      What the C implementation should be verified against is the same
      external ground truth `bcp_frame.py` was itself checked against —
      catalogue known-answer vectors (`crc16(b"123456789") == 0x29B1`,
      the COBS paper's small vectors), round-trip properties tested
      against the one real implementation, the real RP2040 DMA-sniffer
      comparison (already independent hardware, done above), and the
      framing-failure-scenario tests (behavior against the spec, not
      against a second encoder). Two implementations kept in sync purely
      so they can diff each other is an unneeded extra mechanism, not a
      safety net -- check the plain option (test the one real
      implementation against known-answer vectors) before reaching for a
      parallel one. What
      `bcp_frame.py`/`tests/test_bcp_frame.py` actually were: a fast
      design-iteration tool for nailing down the wire format this
      session (now settled in `PROTOCOL.md`) — that job is done. Once the
      C port lands, tests target the C module directly (via the unix
      port, same pattern as `tests/test_bclibc.py`), reusing this
      session's known-answer vectors and failure-scenario cases as the
      actual test content, not diffing against a kept-alive Python twin.
- [x] **Explored, not adopted — `@micropython.native`/`@micropython.viper`
      for `crc16`, on real RP2040-Zero hardware, `mpremote run`:**

      | impl | µs/byte (1400 B) |
      |---|---|
      | plain (current) | ~13.1 |
      | `@micropython.native` | ~9.0 (1.46×) |
      | `@micropython.viper` (typed `ptr8`/`ptr16`) | **~0.50 (~26×)** |

      All three verified byte-identical (`crc16(b"123456789") == 0x29B1`).
      Not adopted: `viper`'s typed pointer signature is MicroPython-only
      (no CPython fallback without a second code path), doesn't help COBS
      unless COBS gets the same treatment, and — per the resolution above
      — C makes the whole question moot rather than needing a
      viper/plain split.
- [x] **Explored, not adopted — RP2040/RP2350 DMA "sniff" hardware CRC.**
      RP2040 (and RP2350, same register layout confirmed in
      `pico-sdk`'s `rp2350/hardware_regs/dma.h`) has a DMA-channel sniffer
      that computes a checksum on the fly during a memory-to-memory
      transfer, config'd via `DMA_SNIFF_CTRL`/`DMA_SNIFF_DATA`
      (`dma_sniffer_enable()` etc. in `hardware/dma.h`). Mode `0x2` =
      "CRC-16-CCITT" (non-bit-reversed), mode `0x3` = same, bit-reversed;
      **no configurable arbitrary polynomial and no CRC-16/IBM (`0x8005`)
      mode** — only `0x1021`, in either bit order. **Verified for real**
      on RP2040-Zero via `mpremote` + `rp2.DMA()` + raw register pokes:
      seeded `DMA_SNIFF_DATA=0xFFFF`, mode `0x2`, output byte-identical to
      software `CCITT-FALSE` across every tested size (1–1400 B) including
      the `0x29B1` known-answer vector — **confirms the CCITT-FALSE choice
      needed no change to get hardware acceleration on RP2040/RP2350**
      (mode `0x3` would have matched a reflected/KERMIT choice just as
      well — this was a lucky-neutral pick, not a reason either variant
      was better). **Why not adopted:** the Python-level `rp2.DMA` API has
      a **large fixed per-call overhead (~100 µs)** — channel config +
      `dma.config()` + busy-poll `dma.active()` — that dominates at the
      protocol's typical small frame sizes and makes it *slower* than
      `viper` below ~300 B:

      | size | crc `viper` | crc DMA (incl. Python-level setup) |
      |---|---|---|
      | 16 B (`Request`) | 35.7 µs | 106.0 µs |
      | 68 B (`MORE` frame, 4 rows) | 60.1 µs | 102.3 µs |
      | 296 B (`LOAD_CONDITIONS` max) | 167.7 µs | 102.1 µs |
      | 1060 B (`LOAD_PROFILE` max) | 527.5 µs | **109.8 µs** |

      Only wins for the rare large `LOAD_PROFILE` frame, loses for every
      frequent small one — the opposite of "DMA is just strictly faster
      hardware," which is what the earlier exploration assumed before
      actually measuring it. A lower-level implementation (raw
      `READ_ADDR`/`WRITE_ADDR`/`CTRL_TRIG` register pokes + IRQ completion
      instead of the busy-poll Python API) would likely cut that fixed
      cost, but wasn't tried — moot given the C resolution above; a C
      dispatcher can reach these same registers directly with none of the
      Python-call overhead, if this specific trick is ever revisited.
      RP2350's ARMv8-M core (Cortex-M33) additionally has native
      `CRC32B`/`CRC32H`/`CRC32W` instructions (confirmed present in the
      ISA; **no ready-made pico-sdk wrapper found**, would need hand-written
      intrinsics/inline-asm) — but those compute **CRC-32**, not CRC-16,
      so using them would mean widening the wire CRC field to 4 bytes;
      not pursued, same "C makes this moot for now" reasoning.
- [x] **Resolved — RP2040 is not this project's real-time target;
      RP2350 (`armv7emsp`, hardware FPU) and ESP32-S3 are.** Per
      `benchmarks/benches.md`: RP2040 `integrate()` 1 km = 353.75 ms —
      **22× slower** than RP2350 hw-FPU's 15.99 ms (ESP32-S3 hw-FPU:
      14.85 ms, essentially tied with RP2350). Notably, RP2350 *without*
      the hardware-FPU build (`armv7m` soft-float) is still 140.88 ms —
      **8.8× slower than the same silicon's own `armv7emsp` build** —
      the natmod's float ABI (Epic 2's `armv7emsp`-vs-softfp fix) matters
      far more than anything CRC/COBS-related. No framing optimization
      changes this: RP2040's bottleneck is the solver itself, 22× too
      slow regardless of wire format. This directly informs Epic 6/7
      below.
- [ ] **Open, deliberately deferred — COBS vs. plain `start_byte + len +
      CRC`.** Raised directly: COBS is a full second O(n) pass on top of
      CRC (roughly doubling total framing cost — measured ~17.7 µs/byte
      COBS vs. ~13.1 µs/byte CRC, plain Python, RP2040), where a bare
      length field would need none. COBS's actual justification was never
      CDC1 (USB bulk transfers already have their own link-layer CRC +
      retry, per the byte-loss note above) — it's the **already-planned**
      UART/BLE transport epic, where raw corruption is real and
      `start_byte` re-sync is false-sync-prone (the original reason
      `len` and `start_byte` were dropped, see above). Reversing this
      would mean redesigning framing again once UART/BLE actually lands,
      vs. paying a now-quantified, C-eliminable cost today. **Left open
      on purpose** rather than re-resolved — revisit if CDC1 stays the
      only transport for a long time and the UART/BLE epic keeps slipping.
- [ ] Bad-CRC frames are dropped silently (their `seq` cannot be trusted,
      so there is nothing to reply to); host relies on a timeout. Optional
      drop counter reported via `IDENT`.
- [x] **Superseded — `FIND_APEX` and `FIND_MAX_RANGE` dropped from the
      wire command set entirely.** Corrects the earlier "in the v1
      command set" resolution. Both are trajectory-shape analysis
      questions (max ordinate, max achievable range), not part of the
      live-shot holdover workflow this protocol targets
      (`LOAD_PROFILE`/`LOAD_CONFIG`/`LOAD_CONDITIONS` once, then
      `INTEGRATE_AT`/`INTEGRATE(_FAST)` per actual range) —
      `find_zero_angle` was already made internal-only for a related
      reason (Epic 8), and neither of these is even auto-triggered by
      anything, so there's no equivalent internal role for them either.
      `FIND_APEX` is redundant with `INTEGRATE` besides: a host already
      streaming full rows can find the max-height row itself. Both stay
      ordinary `tiny_bclibc`/`tiny_bclibc.py` library functions outside
      BCP — not removed from the engine, just not exposed over the wire
      in v1. Revisit only if a real diagnostics/analysis use case for the
      co-processor specifically shows up.
- [ ] Command enum: `LOAD_PROFILE, LOAD_CONFIG, LOAD_CONDITIONS, INTEGRATE,
      INTEGRATE_FAST, INTEGRATE_AT, RESET, IDENT, ABORT, ACK/NAK/ERROR`.
      **`FIND_ZERO_ANGLE`, `FIND_APEX`, `FIND_MAX_RANGE` dropped from
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
      sizes at the time: `LOAD_PROFILE` ≈ 1.1 KB (dominated by the drag
      table, up to 128 pts), `LOAD_CONDITIONS` ≈ 300 B (dominated by
      winds, up to 16) — `LOAD_PROFILE` shrank further to ≈ 1.0 KB once
      solver tuning also split out into its own `LOAD_CONFIG` (below).
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
- [x] **Resolved — MicroPython's role is transport construction only, not
      I/O.** Per Epic 3's "implementation language is C" resolution:
      Python builds/configures the CDC1 (or later, UART) stream object and
      passes it once into a C entry point (`mp_stream_read`/`mp_stream_write`
      from `py/stream.h`, the standard way to drive a Python stream object
      from C) — the read/decode/dispatch/write loop then runs entirely in
      C, with no per-frame trip back into the Python interpreter. "Never
      blocks the CDC0 REPL" (below) is therefore about **which core** that
      C loop runs on (Epic 7's now-optional core-placement choice), not
      about keeping the loop itself in non-blocking Python.
- [ ] Verify `usb.device` CDC-composite support/parity across the actual
      MicroPython port versions targeted for RP2040, RP2350, and ESP32-S3
      — confirm per-port before relying on it uniformly across all three.
- [ ] Non-blocking (or second-core) operation of the CDC1 dispatch loop, so
      CDC1 traffic never blocks the CDC0 REPL.
- [ ] UART and BLE NUS transports: explicitly deferred to a later epic
      (same frame parser, different byte source — and per the above, that
      parser is C, so "same" now literally means the same compiled code,
      not just the same design).

## Epic 5 — Streaming (Y-modem-like)

- [x] **Superseded — no `STREAM_START`/`STREAM_DATA`/`STREAM_END`.** Per
      Epic 3's resolved framing, `INTEGRATE`/`INTEGRATE_FAST` stream on
      their own: a sequence of `status=MORE` frames (full trajectories are
      never returned as one packet), terminated by a final `status=OK`
      frame carrying the `total`/`reason` (`tiny_bclibc_integrate_stream`'s
      stop reason). See `PROTOCOL.md` §4.4/§4.4a for the exact frame
      layout.
- [x] **Resolved — `INTEGRATE_FAST` alongside `INTEGRATE`, same request,
      thinner per-row wire struct.** `INTEGRATE`'s `MORE` frames carry the
      full 16-field `TrajectoryData` row (64 B sp / 124 B dp). Most
      callers only need a few fields (holdover angles for a
      scope/reticle), and the row size directly gates **per-point
      latency**, not just total bandwidth -- this matters most once the
      UART transport epic lands (out of phase-1 scope, see the non-goals
      above, but the frame layer is transport-agnostic by design, so this
      is decided now rather than retrofitted later). On a serial link,
      byte transmission time itself dominates, not CPU-side COBS/CRC cost:
      at 115200 baud (8N1, ~86.8 µs/byte) a full double-precision row
      (124 B) takes ~10.8 ms to transmit versus ~1.4 ms for a 16 B
      compact row -- both well above the ~12.6 µs/byte CRC16 cost measured
      in Epic 3, so on UART the wire itself sets the pace and row size is
      the only lever that shortens time-to-next-point. `INTEGRATE_FAST`'s
      row (`FastTrajData`, `PROTOCOL.md` §4.5a): `distance_ft,
      drop_angle_rad, windage_angle_rad, velocity_fps` (16 B, fixed
      regardless of build precision since all wire floats are `f32`).
      Both commands run the identical underlying
      `tiny_bclibc_integrate_stream()` call -- `INTEGRATE_FAST` is a
      thinner wire projection of the same computed rows, not a cheaper
      computation, so it costs nothing extra on USB CDC1 either.
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
- [x] **Superseded — no async kill/relaunch needed at all, on any target.**
      Replaces the earlier "dual-core kill/relaunch is the primary
      mechanism" resolution below (kept, struck through in spirit, for the
      reasoning trail). Once the whole read → decode → dispatch → write
      loop lives in C (see Epic 3's "implementation language is C"
      resolution) with MicroPython only handing it a transport object and
      picking which core it runs on (Epic 7), every blocking call this
      protocol makes turns out to already be either cooperatively
      interruptible or provably bounded — an async kill was solving a
      problem that doesn't actually exist here:
    - **`INTEGRATE`/`INTEGRATE_FAST` (the only unbounded-length
          operation):** **asynchronous-feeling interruption is still there
          for the host** — an `ABORT` (or any new frame, per the no-queue
          rule) still stops a running trajectory promptly, it's just
          implemented cooperatively rather than by killing anything.
          Already has the checkpoint for it — `mp_stream_cb`'s
          `TINY_BCLIBC_TERM_HANDLER_STOP`, returned between rows. With the
          dispatch loop in C, "is a new frame waiting" is a cheap
          non-blocking check on the transport object at that same per-row
          boundary — no different in kind from the Python-level version,
          just cheaper and now the *only* preemption primitive this
          protocol needs. Responsiveness is bounded by one row's compute
          time, not by the whole trajectory's: `benches.md` gives ~158 µs/
          row on RP2350 hw-FPU, ~3.5 ms/row even on RP2040 — either way
          well under what the host would perceive as latency, so nothing
          is actually given up by dropping the hard kill.
    - **Every other command is bounded, not open-ended** — `find_zero_angle`
          /`find_apex`/`find_max_range`/`integrate_at` all terminate on
          their own via `Config.max_iterations` (default 50) or a fixed
          step count; there is no pathological input that loops forever.
          A preempting command just waits for the current bounded call to
          return, then gets serviced — slower on a slow platform, never
          stuck. `benches.md` gives the actual worst case per target
          (RP2350 hw-FPU: `find_zero_angle` ~4 ms, `find_apex` ~1 ms; even
          RP2040's worst row, `find_zero_angle` ~119 ms, is a documented
          latency bound, not a hang).
    - **Consequence:** the killable-window/shared-lock deadlock risk below
          (FreeRTOS `vTaskDelete()` not releasing mutexes, RP2040's
          shared-heap threading model) never arises, because nothing ever
          gets killed mid-call. Demotes the same way the earlier
          `longjmp`-from-ISR risk was demoted when kill/relaunch first
          replaced it — one fewer failure mode to verify per platform.
    - Second core (Epic 7) is therefore **not** required for correctness
          on any target, phase-1 RP2040 included — it becomes a pure
          concurrency/responsiveness choice (does the solver block the
          REPL's core), decided by MicroPython at startup, decoupled from
          this epic entirely.
  - **Superseded material below, kept for the reasoning trail (dual-core
        kill/relaunch, single-core `setjmp`/`longjmp`, unix
        `pthread_kill`/`siglongjmp`/`fork`+`SIGKILL`):** all three were
        answers to "how do we forcibly stop a call already in flight,"
        which turned out to be the wrong question once every call is
        either cooperative (`INTEGRATE`) or bounded (everything else).
        None of this machinery needs building. Left in place, not deleted,
        in case a future command genuinely needs unbounded/unstructured
        blocking (e.g. an operation with no natural per-iteration
        checkpoint and no iteration cap) — revisit only if one shows up:
    <details>
    <summary>Original dual-core / single-core / unix mechanism drafts</summary>

    - **Dual-core (RP2040/RP2350: pico-sdk `multicore_reset_core1()` +
          `multicore_launch_core1()`; ESP32-S3: FreeRTOS `vTaskDelete()` +
          `xTaskCreatePinnedToCore()`):** kill and relaunch the worker
          core/task, discarding its entire execution context rather than
          unwinding it. Risk: killing a worker holding a shared lock
          (MicroPython's GC lock on a shared-heap dual-core port) can
          deadlock the other core — needs the killable window to be
          exactly a lock-free pure-C call.
    - **Single-core:** `setjmp`/`longjmp` in the binding layer, wrapping
          each blocking call, triggered from the CDC1 RX ISR on a
          preempting frame; single global `jmp_buf` given the no-queue
          rule; once `setjmp()` returns nonzero, any output buffer is
          garbage and the wrapper returns `INTERRUPTED` without touching
          it.
    - **Unix port:** `_thread` wraps POSIX pthreads; `pthread_cancel()`'s
          deferred cancellation never fires inside `tiny_bclibc`'s
          checkpoint-free RK4 loop; recommended `pthread_kill(tid,
          SIGUSR1)` + `siglongjmp` in the signal handler (the
          async-signal-safe pair); a forked worker + `SIGKILL` sidesteps
          the shared-lock risk entirely if `fork()` turns out to be
          available, at the cost of IPC instead of shared buffers.

    </details>
- [ ] `INTERRUPTED` response status for whatever got preempted (distinct
      from the normal response to the command that preempted it) — still
      needed: it is the response to whatever bounded call was still
      running when a fresher command arrived, even without a kill.
- [ ] `INTEGRATE` (streamed) cooperative hook: `mp_stream_cb` (its C-level
      equivalent) returns `TINY_BCLIBC_TERM_HANDLER_STOP` when a new frame
      is waiting on the transport — the one preemption mechanism this
      epic actually needs.

## Epic 7 — Second core (where supported)

- [x] **Superseded — not an abort mechanism, just a core-placement
      choice.** Per Epic 6, no target needs kill/relaunch, so this epic is
      no longer load-bearing scaffolding for anything. What survives:
      **MicroPython decides which core the C dispatch-loop-plus-solver
      runs on** (e.g. `_thread.start_new_thread()` onto core1 on
      RP2040/RP2350, `xTaskCreatePinnedToCore()` on ESP32-S3), purely so a
      long `INTEGRATE` stream doesn't block the CDC0 REPL on the other
      core — a responsiveness nicety, not a correctness requirement.
      Genuinely optional per-target, and not blocking anything else in
      this backlog.
- [ ] If pursued: launch the C dispatcher loop (transport object handed
      in from Python, per Epic 3/4) on a second core/task. Precedent in
      repo: `natmod/examples/tiny_bclibc_natmod_test_2core.py` and
      `..._bench_2core.py`.
- [ ] No inter-core kill/generation-tracking channel needed anymore (that
      was Epic 6's now-superseded requirement) — if a ring buffer or
      similar is still wanted between the solver core and the transport
      core for streaming rows, it's a throughput/simplicity choice, not a
      correctness one.

## Epic 8 — Commands on top of existing structures (no a7p)

> Byte-level layout (per-command struct fields) lives in
> [`PROTOCOL.md`](PROTOCOL.md) -- kept in one place instead of duplicated
> across backlog bullets. This epic tracks the *decisions*; `PROTOCOL.md`
> is the *reference*.

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
