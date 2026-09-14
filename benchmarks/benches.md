## Stock

### RP2040 (armv6m)

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


### RP2350 (armv7m)

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


### RP2350 (armv7emsp)

Fixed natmod/Makefile float-ABI mismatch first (see CHANGELOG / commit):
dynruntime.mk builds armv7emsp natmod as -mfloat-abi=hard, but the actual
RP2350 (Pico2) firmware is built -mfloat-abi=softfp by pico-sdk's own
toolchain file. Every float crossing the mp_fun_table boundary was silently
corrupted, so integrate_at()/find_apex() always raised "interception error".
Elevation avg (0.1434°) and apex (532.1 ft, 0.6 ft) below match the other
platforms exactly, confirming the fix, not just that it no longer crashes.

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


## Overclocked

`machine.freq(200_000_000)` before each run (RP2040 default 125 MHz, RP2350 default 150 MHz).

### RP2040 (armv6m)

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


### RP2350 (armv7m)

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


### RP2350 (armv7emsp)

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

