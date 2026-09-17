## Summary

Reference: RP2040 Stock (125 MHz) `integrate()` 1 km avg = 1.0x.

| Architecture / Chip                         | Mode                            | integrate(1 km) | integrate(3 km) | integrate_at() | find_zero_angle() | find_apex() | Shots/sec (1km) |         Speedup |
| ------------------------------------------- | ------------------------------- | --------------: | --------------: | -------------: | ----------------: | ----------: | --------------: | --------------: |
| RP2040 (armv6m)                             | Stock (125 MHz)                 |       353.75 ms |      2158.65 ms |       66.99 ms |         119.07 ms |    33.42 ms |             2.8 | 1.0x (baseline) |
| RP2040 (armv6m)                             | OC (200 MHz)                    |       221.08 ms |      1349.12 ms |       41.88 ms |          74.43 ms |    20.90 ms |             4.5 |            1.6x |
| RP2350 (armv7m, soft-float)                 | Stock (150 MHz)                 |       140.88 ms |       843.10 ms |       27.10 ms |          48.40 ms |    13.41 ms |             7.1 |            2.5x |
| RP2350 (armv7m, soft-float)                 | OC (200 MHz)                    |       105.71 ms |       632.27 ms |       20.36 ms |          36.30 ms |    10.09 ms |             9.5 |            3.3x |
| RP2350 (armv7emsp, hardware FPU)            | Stock (150 MHz)                 |        15.99 ms |        73.20 ms |        2.42 ms |           4.13 ms |     1.21 ms |            62.6 |           22.1x |
| RP2350 (armv7emsp, hardware FPU)            | OC (200 MHz)                    |        11.98 ms |        54.91 ms |        1.81 ms |           3.10 ms |     0.91 ms |            83.6 |           29.5x |
| ESP32-S3 (xtensawin, usermod, hardware FPU) | Stock (240 MHz, no OC headroom) |        14.85 ms |        66.88 ms |        2.51 ms |           4.01 ms |     1.48 ms |            67.4 |           23.8x |
| RP2350 (armv7emsp, hardware FPU, RK45)      | Stock (150 MHz)                 |        20.05 ms |        11.86 ms |        2.48 ms |           4.28 ms |     1.24 ms |            49.9 |           17.6x |
| RP2350 (armv7emsdp, hardware FPU, RK45)     | OC (200 MHz)                    |        15.04 ms |         8.90 ms |        1.86 ms |           3.21 ms |     0.93 ms |            66.5 |           23.5x |
| RP2350 (armv7emsdp, hardware FPU, RK45)     | OC (220 MHz)                    |        13.67 ms |         8.09 ms |        1.69 ms |           2.92 ms |     0.85 ms |            73.2 |           25.9x |
| RP2350 (armv7emsdp, hardware FPU, RK45)     | OC (240 MHz)                    |        12.54 ms |         7.42 ms |        1.56 ms |           2.68 ms |     0.78 ms |            79.8 |           28.2x |

## Stock

### RP2040 (armv6m / RK4)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.1-5-g99641a8-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 353.75 ms  (353746 µs)
  Min: 353508 µs  Max: 353998 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 2158.65 ms  (2158646 µs)
  Min: 2158481 µs  Max: 2158725 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 66.989 ms  (66988.8 µs)
  Min: 10009 µs  Max: 133678 µs
  Calls: 500
  ~15 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 119.073 ms  (119072.7 µs)
  Min: 119054 µs  Max: 119144 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 33.420 ms  (33419.9 µs)
  Min: 33415 µs  Max: 33487 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 76,736 B
  After integrate: 86,816 B
  After GC: 86,800 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 156,992 B → 146,928 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 2.8 shots/sec
  Interpolation: 14.9 calls/sec
  Zero finding: 8.4 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7m)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.2-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 140.88 ms  (140883 µs)
  Min: 140752 µs  Max: 141023 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 843.10 ms  (843104 µs)
  Min: 843017 µs  Max: 843133 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 27.100 ms  (27100.0 µs)
  Min: 3848 µs  Max: 54279 µs
  Calls: 500
  ~37 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 48.398 ms  (48398.3 µs)
  Min: 48391 µs  Max: 48415 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 13.408 ms  (13408.0 µs)
  Min: 13406 µs  Max: 13430 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 74,256 B
  After integrate: 84,336 B
  After GC: 84,320 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 413,424 B → 403,360 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 7.1 shots/sec
  Interpolation: 36.8 calls/sec
  Zero finding: 20.7 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7emsp / RK4)

Fixed natmod/Makefile float-ABI mismatch first (see CHANGELOG / commit):
dynruntime.mk builds armv7emsp natmod as -mfloat-abi=hard, but the actual
RP2350 (Pico2) firmware is built -mfloat-abi=softfp by pico-sdk's own
toolchain file. Every float crossing the mp_fun_table boundary was silently
corrupted, so integrate_at()/find_apex() always raised "interception error".
Elevation avg (0.1434°) and apex (532.1 ft, 0.6 ft) below match the other
platforms exactly, confirming the fix, not just that it no longer crashes.

Built with `make ARCH=armv7emsp RP2350=1 dist`, not the plain `ARCH=armv7emsp`
from the table above in `## Build`. `armv7emsp` on its own still means
`dynruntime.mk`'s own default (hard-float, right for STM32F4 and for the
`test (armv7emsp / 32-bit ARM Linux)` CI leg) -- RP2350's softfp firmware
needs the explicit override. See README.md's own "RP2350 needs a separate
build" section for why this can't just be the shared default.

Already known upstream, actively being fixed from the firmware side:
[micropython/micropython#19279](https://github.com/micropython/micropython/issues/19279)
("mp_obj_new_float returns 0") is the identical symptom/root cause,
confirmed by a MicroPython maintainer.
[micropython/micropython#19661](https://github.com/micropython/micropython/pull/19661)
(open) fixes it the other way -- makes the RP2350 firmware itself
`-mfloat-abi=hard` via pico-sdk 2.3.0's new `PICO_HARD_FLOAT_ABI`, instead
of what we did here (build the natmod softfp to match the firmware that's
already out there). Complementary, not redundant: that PR only helps once
users rebuild/reflash with pico-sdk >= 2.3.0; this natmod-side fix works
against any already-deployed RP2350 firmware today.

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.1-5-g99641a8-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 15.99 ms  (15988 µs)
  Min: 15825 µs  Max: 16178 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 73.20 ms  (73200 µs)
  Min: 73132 µs  Max: 73218 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 2.416 ms  (2416.5 µs)
  Min: 437 µs  Max: 4736 µs
  Calls: 500
  ~414 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 4.131 ms  (4131.3 µs)
  Min: 4120 µs  Max: 4150 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 1.210 ms  (1210.4 µs)
  Min: 1196 µs  Max: 1226 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 70,224 B
  After integrate: 80,304 B
  After GC: 80,288 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 417,456 B → 407,392 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 62.6 shots/sec
  Interpolation: 413.8 calls/sec
  Zero finding: 242.1 calls/sec
============================================================
Benchmark complete.
```

### ESP32-S3 (xtensawin / RK4)

Board: LilyGO T-Display-S3 (ESP32-S3R8, 16MB flash, 8MB Octal PSRAM).
Firmware: official `ESP32_GENERIC_S3-SPIRAM_OCT` v1.29.0 build, `usermod`
(bclibc compiled directly into the firmware via `usermod/micropython.cmake`,
ESP-IDF v5.5.2), 240 MHz stock.

**`natmod` (`ARCH=xtensawin`) does NOT work on real ESP32-S3 hardware --
likely an upstream MicroPython bug, not bclibc's.** `usermod` (below)
works fine and is the supported route on this platform; this natmod finding
is recorded here for anyone who hits the same wall.

Symptom: the built `.mpy` imports cleanly -- `import tiny_bclibc as bc`
succeeds, `dir(bc)` lists every expected attribute -- but the board hard-crashes
on the *first* native call, before any bclibc computation runs. No exception,
no Python traceback: the USB-Serial-JTAG console itself drops mid-call
(`OSError: [Errno 5] Input/output error` from the host side) and the board
silently resets, with no panic backtrace captured on either side of the
reset (tried re-opening the serial port across the reset window in case the
dump landed after re-enumeration -- nothing).

Isolated with a minimal non-bclibc probe module (`mp_obj_new_int(42)`, no
floats, no bclibc, 5 GOT entries vs. bclibc's 72) built the same way
(`dynruntime.mk`, `ARCH=xtensawin`): **same crash**, on the very first call
to a plain builtin native function. So this is not a bclibc bug, not the
armv7emsp float-ABI class of bug (Xtensa's calling convention has no
hard/softfp split -- `dynruntime.mk`'s `xtensawin` branch sets no
`-mfloat-abi`-equivalent flag at all), and not a GOT-size/relocation-count
edge case (5 entries is about as minimal as a natmod gets).

Telling detail: `mpy_init()` itself -- the natmod's own entry point, invoked
directly by the import machinery -- runs fine (it's what registers the
module's globals, and that clearly succeeds). The crash is specifically in
calling a *plain builtin function object* pulled out of those globals
through the VM's normal call dispatch afterward. That points at
`tools/mpy_ld.py`'s Xtensa relocation/trampoline code (`asm_jump_xtensa`,
`build_got_xtensa`) or how the VM's generic call path invokes a relocated
native function pointer on `xtensawin` -- not at anything specific to this
module.

Circumstantial support: upstream `tools/ci.sh`'s own xtensawin natmod job
is literally named `ci_native_mpy_modules_build` -- build-only, no ESP32
hardware or emulator to run it on. So this may be an upstream bug nobody
has actually executed on real silicon before.

Root-causing further needs a real backtrace -- JTAG over the same USB port
the board already exposes (`openocd` + `xtensa-esp32s3-elf-gdb`, not set up
in this session) -- since the panic handler never gets to print before the
USB peripheral itself goes down.

Searched upstream for an existing report before writing this up (~25 query
variants, issues + PRs, open + closed) -- nothing matches this exact
symptom (crash on the very first call, minimal single-file probe, no
linker errors). Checked and ruled out as unrelated, all older and already
resolved:
[#8781](https://github.com/micropython/micropython/issues/8781) `R_XTENSA_NDIFF32 not supported`
(closed, link-time only, fix landed in
[#19286](https://github.com/micropython/micropython/pull/19286), already in v1.29.0),
[#8782](https://github.com/micropython/micropython/issues/8782) and
[#8783](https://github.com/micropython/micropython/issues/8783) (sibling
reports from the same person, both closed, both link-time `mpy_ld.py`
errors, not a runtime crash),
[#19276](https://github.com/micropython/micropython/issues/19276) `mpy-ld incorrectly merging literals (esp32) across source files`
(open, but needs two source files sharing a literal offset -- our probe is
one file), and
[#19452](https://github.com/micropython/micropython/pull/19452) `Fix aligned jump target in natmod trampolines`
(merged, already in v1.29.0; notable mainly as a reminder that a real
xtensawin natmod regression already slipped past upstream CI once before,
for the same reason -- QEMU-only testing, no real ESP32 hardware). No
upstream issue filed for this yet as of this writing.

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: ed3b702-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 14.85 ms  (14853 µs)
  Min: 14263 µs  Max: 19161 µs  p95: 19161 µs  p99: 19161 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 66.88 ms  (66875 µs)
  Min: 66824 µs  Max: 66968 µs  p95: 66968 µs  p99: 66968 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 2.509 ms  (2508.6 µs)
  Min: 851 µs  Max: 4459 µs  p95: 4448 µs  p99: 4456 µs
  Calls: 500
  ~399 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 4.014 ms  (4014.0 µs)
  Min: 3991 µs  Max: 4152 µs  p95: 4128 µs  p99: 4152 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 1.475 ms  (1474.5 µs)
  Min: 1458 µs  Max: 1643 µs  p95: 1497 µs  p99: 1643 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 38,976 B
  After integrate: 49,056 B
  After GC: 49,040 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 8,282,560 B → 8,272,496 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 67.4 shots/sec
  Interpolation: 396.9 calls/sec
  Zero finding: 249.8 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7emsp / RK45)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 3c7b13e-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 20.05 ms  (20048 µs)
  Min: 19917 µs  Max: 20203 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 11.86 ms  (11855 µs)
  Min: 11748 µs  Max: 11902 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 2.475 ms  (2475.4 µs)
  Min: 426 µs  Max: 4876 µs
  Calls: 500
  ~404 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 4.282 ms  (4282.4 µs)
  Min: 4275 µs  Max: 4293 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 1.238 ms  (1238.2 µs)
  Min: 1236 µs  Max: 1257 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 66,896 B
  After integrate: 76,976 B
  After GC: 76,960 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 420,784 B → 410,720 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 49.9 shots/sec
  Interpolation: 404.0 calls/sec
  Zero finding: 233.5 calls/sec
============================================================
Benchmark complete.
```

## Overclocked

`machine.freq(200_000_000)` before each run (RP2040 default 125 MHz, RP2350 default 150 MHz).

### RP2040 (armv6m / RK4)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.1-5-g99641a8-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 221.08 ms  (221077 µs)
  Min: 220947 µs  Max: 221246 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 1349.12 ms  (1349125 µs)
  Min: 1349077 µs  Max: 1349197 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 41.878 ms  (41878.3 µs)
  Min: 6268 µs  Max: 83555 µs
  Calls: 500
  ~24 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 74.425 ms  (74425.5 µs)
  Min: 74411 µs  Max: 74507 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 20.899 ms  (20899.4 µs)
  Min: 20885 µs  Max: 20965 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 76,752 B
  After integrate: 86,832 B
  After GC: 86,816 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 156,976 B → 146,912 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 4.5 shots/sec
  Interpolation: 23.9 calls/sec
  Zero finding: 13.4 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7m / RK4)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.1-5-g99641a8-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 105.71 ms  (105708 µs)
  Min: 105590 µs  Max: 105840 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 632.27 ms  (632267 µs)
  Min: 632207 µs  Max: 632294 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 20.359 ms  (20359.2 µs)
  Min: 2917 µs  Max: 40747 µs
  Calls: 500
  ~49 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 36.298 ms  (36298.2 µs)
  Min: 36291 µs  Max: 36317 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 10.089 ms  (10089.4 µs)
  Min: 10079 µs  Max: 10106 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 74,304 B
  After integrate: 84,384 B
  After GC: 84,368 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 413,376 B → 403,312 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 9.5 shots/sec
  Interpolation: 49.1 calls/sec
  Zero finding: 27.5 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7emsp / RK4)

```
MPY: soft reboot
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 1.2.1-5-g99641a8-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 11.98 ms  (11975 µs)
  Min: 11875 µs  Max: 12076 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 54.91 ms  (54907 µs)
  Min: 54836 µs  Max: 54951 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 1.812 ms  (1812.5 µs)
  Min: 324 µs  Max: 3555 µs
  Calls: 500
  ~552 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 3.102 ms  (3102.1 µs)
  Min: 3092 µs  Max: 3119 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 0.907 ms  (907.3 µs)
  Min: 898 µs  Max: 925 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 70,224 B
  After integrate: 80,304 B
  After GC: 80,288 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 417,456 B → 407,392 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 83.6 shots/sec
  Interpolation: 551.8 calls/sec
  Zero finding: 322.4 calls/sec
============================================================
Benchmark complete.
```

### RP2350 (armv7emsdp / RK45)

```
MPY: soft reboot
Freq: 200000000
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 3c7b13e-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 15.04 ms  (15041 µs)
  Min: 14943 µs  Max: 15157 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 8.90 ms  (8899 µs)
  Min: 8822 µs  Max: 8937 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 1.863 ms  (1862.9 µs)
  Min: 327 µs  Max: 3662 µs
  Calls: 500
  ~537 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 3.214 ms  (3214.3 µs)
  Min: 3208 µs  Max: 3233 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 0.931 ms  (931.0 µs)
  Min: 929 µs  Max: 957 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 66,960 B
  After integrate: 77,040 B
  After GC: 77,024 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 420,720 B → 410,656 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 66.5 shots/sec
  Interpolation: 536.8 calls/sec
  Zero finding: 311.2 calls/sec
============================================================
Benchmark complete.
```

```
MPY: soft reboot
Freq: 220000000
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 3c7b13e-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 13.67 ms  (13673 µs)
  Min: 13583 µs  Max: 13775 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 8.09 ms  (8089 µs)
  Min: 8022 µs  Max: 8128 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 1.694 ms  (1693.6 µs)
  Min: 298 µs  Max: 3329 µs
  Calls: 500
  ~590 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 2.922 ms  (2922.1 µs)
  Min: 2916 µs  Max: 2939 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 0.846 ms  (846.4 µs)
  Min: 844 µs  Max: 871 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 66,960 B
  After integrate: 77,040 B
  After GC: 77,024 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 420,720 B → 410,656 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 73.2 shots/sec
  Interpolation: 590.5 calls/sec
  Zero finding: 342.3 calls/sec
============================================================
Benchmark complete.
```

```
MPY: soft reboot
Freq: 240000000
============================================================
tiny_bclibc Performance Benchmark
============================================================
Version: 3c7b13e-sp

--- integrate() (1 km, 10 m steps) ---
  Rows: 101
  Stop reason: 1
  Avg: 12.54 ms  (12539 µs)
  Min: 12455 µs  Max: 12631 µs
  Iterations: 10

--- integrate() (3 km, 100 m steps) ---
  Rows: 31
  Stop reason: 1
  Avg: 7.42 ms  (7420 µs)
  Min: 7365 µs  Max: 7455 µs
  Iterations: 10

--- integrate_at() (single point interpolation) ---
  Avg: 1.555 ms  (1554.9 µs)
  Min: 276 µs  Max: 3055 µs
  Calls: 500
  ~643 calls/sec

--- find_zero_angle() (300 m zero) ---
  Avg: 2.680 ms  (2680.0 µs)
  Min: 2674 µs  Max: 2702 µs
  Elevation avg: 0.1434°
  Iterations: 50

--- find_apex() ---
  Avg: 0.777 ms  (777.4 µs)
  Min: 775 µs  Max: 801 µs
  Apex: 532.1 ft, 0.6 ft
  Iterations: 50

--- Memory usage (3 km trajectory) ---
  Before: 66,960 B
  After integrate: 77,040 B
  After GC: 77,024 B
  Peak allocation: 10,080 B
  Rows: 31
  Free memory: 420,720 B → 410,656 B

============================================================
Benchmark Summary
============================================================
  Trajectory (1 km, 10 m steps): 79.8 shots/sec
  Interpolation: 643.2 calls/sec
  Zero finding: 373.2 calls/sec
============================================================
Benchmark complete.
```
