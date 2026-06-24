# tiny_bclibc MicroPython natmod — Benchmark Report

**Shot config:** G7, BC=0.310, 168 gr @ 2750 fps, zeroed at 300 m  
**Script:** `tests/tiny_bclibc_bench.py`

---

## Cross-platform — `integrate` 1 km, 10 m steps

| Platform | Engine / Precision | avg ms | shots/sec | vs RP2040 SP |
|---|---|---:|---:|---:|
| RP2040 · Cortex-M0+ · 125 MHz · no FPU | tiny_bclibc SP | 353 ms | **2.8** | 1× |
| RP2040 · Cortex-M0+ · 125 MHz · no FPU | tiny_bclibc DP | 662 ms | **1.5** | 0.5× |
| ish · iOS · i686 emu · ~25 MFLOPS | tiny_bclibc SP | 9.4 ms | **107.5** | 38× |
| ish · iOS · i686 emu · ~25 MFLOPS | tiny_bclibc DP | 17.6 ms | **54.0** | 19× |
| ish · iOS · i686 emu · ~25 MFLOPS | py-balcalc Cython DP | 10.1 ms | **99.2** | 35× |
| XBurst · MIPS LE · mipsel | tiny_bclibc DP (usermod) | 3.00 ms | **309** | 110× |
| x64 Linux · MicroPython unix | tiny_bclibc SP | 0.46 ms | **2,217** | 792× |
| x64 Linux · MicroPython unix | tiny_bclibc DP | 1.07 ms | **980** | 350× |
| x64 Linux · CPython | py-balcalc Cython DP ¹ | 0.123 ms | **8,152** | 2912× |

> ¹ `performance_check.py -n 10000` — different shot config / step size from tiny_bclibc bench.
> See [x64 engine comparison](#x64-tiny_bclibc-vs-py-ballisticcalc-cython) for details.

---

## Cross-platform — `find_zero_angle`

| Platform | Engine / Precision | target | avg ms | calls/sec |
|---|---|---|---:|---:|
| RP2040 | tiny_bclibc SP | 300 m | 119 ms | **8.4** |
| RP2040 | tiny_bclibc DP | 300 m | 337 ms | **3.0** |
| ish | tiny_bclibc SP | 300 m | 2.9 ms | **331.5** |
| ish | tiny_bclibc DP | 300 m | 10.1 ms | **94.9** |
| ish | py-balcalc Cython DP | 300 m | 6.5 ms | **153.0** |
| XBurst · mipsel | tiny_bclibc DP (usermod) | 300 m | 1.555 ms | **912.4** |
| x64 | tiny_bclibc SP | 300 m | 0.131 ms | **7,398** |
| x64 | tiny_bclibc DP | 300 m | 0.624 ms | **1,575** |
| x64 | py-balcalc Cython DP ² | 300 m | 0.960 ms | **1,042** |
| x64 | py-balcalc Cython DP ¹ | 100 m | 0.045 ms | **22,296** |

> ² `benchmark.py -r 1000 -w 100`.

---

## SP vs DP — x64 Linux (v1.1.3-10-g4a6c3b6)

| Benchmark | SP | DP | Ratio DP/SP |
|---|---:|---:|---:|
| `integrate` 1 km — avg | 0.46 ms | 1.07 ms | 2.33× |
| `integrate` 3 km — avg | 2.46 ms | 5.94 ms | 2.41× |
| `integrate_at` — avg | 0.062 ms | 0.217 ms | 3.50× |
| `find_zero_angle` — avg | 0.131 ms | 0.624 ms | 4.76× |
| `find_apex` — avg | 0.024 ms | 0.049 ms | 2.04× |
| Peak heap (3 km traj) | 19,520 B | 19,520 B | 1.0× |
| Free heap before | 2,032 KB | 2,012 KB | −20 KB |

> On x64 the SP/DP ratio is higher than on RP2040 (2.3–4.8× vs 1.9–2.8×).
> SP uses bundled fdlibm (`sinf`/`cosf`/`atan2f`), DP uses bundled libm_dbl.
> `find_zero_angle` hits 4.76× because the double tolerance (`1e-8`) requires
> significantly more Ridder iterations than float (`1e-4`).

---

## SP vs DP — RP2040 single-core (v1.1.3-10-g4a6c3b6)

| Benchmark | SP | DP | Ratio DP/SP |
|---|---:|---:|---:|
| `integrate` 1 km — avg | 353 ms | 662 ms | 1.87× |
| `integrate` 3 km — avg | 2151 ms | 4162 ms | 1.93× |
| `integrate_at` — avg | 66.9 ms | 127 ms | 1.90× |
| `find_zero_angle` — avg | 119 ms | 337 ms | 2.83× |
| `find_apex` — avg | 33.4 ms | 63.3 ms | 1.90× |
| Peak heap (3 km traj) | 10,080 B | 10,080 B | 1.0× |
| Free heap before | 179,872 B | 144,912 B | −35 KB |

## SP vs DP — RP2040 dual-core Core1 (v1.1.3-10-g4a6c3b6)

| Benchmark | SP | DP | Ratio DP/SP |
|---|---:|---:|---:|
| `integrate` 1 km — avg | 353.23 ms | 661.73 ms | 1.87× |
| `integrate` 3 km — avg | 2151.21 ms | 4161.80 ms | 1.93× |
| `integrate_at` — avg | 66.949 ms | 127.042 ms | 1.90× |
| `find_zero_angle` — avg | 119.104 ms | 336.923 ms | 2.83× |
| `find_apex` — avg | 33.435 ms | 63.370 ms | 1.90× |
| Free heap before | 170,976 B | 137,120 B | −34 KB |

> Single-core and Core1 results agree within <1 ms.

## SP vs DP — ish / i686 (v1.1.3-19-gf2b28fa)

| Benchmark | SP | DP | Ratio DP/SP |
|---|---:|---:|---:|
| `integrate` 1 km — avg | 9.44 ms | 17.62 ms | 1.87× |
| `integrate` 3 km — avg | 42.79 ms | 91.63 ms | 2.14× |
| `integrate_at` — avg | 1.648 ms | 3.656 ms | 2.22× |
| `find_zero_angle` — avg | 2.899 ms | 10.146 ms | 3.50× |
| `find_apex` — avg | 0.837 ms | 1.824 ms | 2.18× |
| Free heap before | 990,704 B | 971,552 B | −19 KB |

---

## py-ballisticcalc Cython vs tiny_bclibc SP — ish / i686

| Metric | tiny SP | py-balcalc Cython | tiny SP advantage |
|---|---:|---:|---:|
| `integrate` 1 km | 9.44 ms · **107.5/s** | 10.08 ms · **99.2/s** | +8% |
| `find_zero` 300 m | 2.90 ms · **331.5/s** | 6.54 ms · **153.0/s** | +116% |

> `benchmark.py` (different config): Cython Trajectory 28.18 ms, Zero 48.27 ms.

---

## x64: tiny_bclibc vs py-ballisticcalc Cython

Two different benchmark scripts — configs are **not identical**, numbers are indicative only.

### `benchmark.py -r 1000 -w 100` (py-balcalc, v2.3.0b3, warmed up)

| Case | py-balcalc Cython | tiny_bclibc SP | tiny_bclibc DP |
|---|---:|---:|---:|
| Trajectory 1 km | 0.334 ms · **2,994/s** | 0.459 ms · **2,217/s** | 1.068 ms · **980/s** |
| Zero | 0.960 ms · **1,042/s** | 0.131 ms · **7,398/s** | 0.624 ms · **1,575/s** |

> tiny_bclibc SP is **7.1× faster** at zero-finding; py-balcalc is **1.4× faster** at trajectory
> (likely due to coarser output step or different integration config).

### `performance_check.py -n 10000` (py-balcalc, v2.3.0b3, 10k iters)

| Case | py-balcalc Cython | tiny_bclibc SP | tiny_bclibc DP |
|---|---:|---:|---:|
| Trajectory 1 km | 0.123 ms · **8,152/s** | 0.459 ms · **2,217/s** | 1.068 ms · **980/s** |
| Trajectory 1 km + extra | 0.132 ms · **7,598/s** | — | — |
| integrate_at 1 km | 0.054 ms · **18,475/s** | 0.062 ms · **16,159/s** | 0.217 ms · **4,524/s** |
| Zero 100 m | 0.045 ms · **22,296/s** | 0.131 ms · **7,398/s** ³ | 0.624 ms · **1,575/s** ³ |

> ³ tiny_bclibc zeros at 300 m, py-balcalc at 100 m — fewer Ridder iterations for shorter distance.

`integrate_at` is the most comparable call (same target: 1 km, no step-size differences).
tiny_bclibc SP (0.062 ms) is on par with py-balcalc Cython (0.054 ms) — 15% slower.

---

## Analysis

**x64 (SSE2 FPU, bundled math):** SP uses fdlibm (`sinf`/`cosf`), DP uses libm_dbl.
The SP/DP ratio is 2.3–4.8× — larger than on RP2040 (1.9–2.8×) because the
float libm path is proportionally much lighter than the double path on x64.
`find_zero_angle` shows the biggest gap (4.76×): tighter double convergence tolerance
demands more inner `integrate` calls per root iteration.

**RP2040 (Cortex-M0+, newlib, no FPU):** Both precisions are software via newlib.
DP uses 8-byte operands → ~1.9× slower across most paths. `find_zero_angle` is
2.83× due to tighter convergence tolerance.

**ish / i686 (~25 MFLOPS):** x87 FPU running under iOS emulation. SP is ~38× faster
than RP2040 SP; DP ~19× faster than RP2040 DP. `find_zero_angle` shows 3.50× DP/SP
ratio — between RP2040 and x64.

**Numerical accuracy:**  
All platforms agree on elevation (`0.1434°` on x64 / RP2040, `0.1426–0.1428°` on ish
due to different libm version). Apex `532.1 ft / 0.6 ft` on x64 and RP2040.
SP and DP give identical visible results — float32 is sufficient for ≤ 3 km range.

**Recommendation:**
- RP2040: SP — 1.9–2.8× faster, identical accuracy.
- x64 / server: DP when maximum accuracy needed, SP for throughput-critical paths.
- ish / i686: SP already outperforms Cython engine; DP available for validation.

---

## FPU raw throughput — platform comparison

Benchmark: scalar FP add+multiply loop, native C  
(RP2040: native `.mpy`; ish/x64: `gcc -O2 -march=native`).

| Platform | Mode | DP MFLOPS | SP MFLOPS | SP/DP |
|---|---|---:|---:|---:|
| RP2040 · Cortex-M0+ · 125 MHz · no FPU | latency-bound (volatile chain) | 0.52 | 1.10 | 2.12× |
| RP2040 · Cortex-M0+ · 125 MHz · no FPU | throughput (8 accumulators) | **1.41** | **2.21** | 1.57× |
| ish · iOS · i686 emu | latency-bound (volatile chain) | 41.6 | 39.6 | 0.95× |
| ish · iOS · i686 emu | throughput (8 accumulators) | **853** | **1,449** | 1.70× |
| x64 Linux · AMD Ryzen 7 8845HS | latency-bound (volatile chain) | 668 | ~720 | ~1.1× |
| x64 Linux · AMD Ryzen 7 8845HS | throughput (8 accumulators) | **23,214** | **23,451** | 1.01× |

> **Latency-bound** (`volatile c; c = c + a*b; c = c - a*b`) — sequential dependency chain,
> no ILP; measures FPU/soft-float latency + stack/L1 round-trip.  
> **Throughput** (8 independent accumulators) — variables kept in registers, partial
> pipeline overlap possible.

**Key observations:**
- RP2040 latency DP = **0.52 MFLOPS** — volatile stack spills + soft-float `__muldf3`/`__adddf3`
  (~200 cycles each). Throughput/latency ratio: DP **2.7×**, SP **2.0×** — even on soft-float,
  8 independent accumulators help by eliminating volatile spills and allowing partial call pipelining.
- ish latency (~40 MFLOPS) reflects x87 dispatch overhead under iOS ARM emulation; actual
  throughput is **853 MFLOPS DP / 1,449 MFLOPS SP**.
- On ish, SP is **1.7×** faster than DP — x87 processes DP internally in 80-bit, costlier under ARM emulation.
- On x64, SP ≈ DP — both go through SSE2/AVX2 with equal pipeline width.
- x64 throughput exceeds RP2040 by **16,500× (DP)** and **10,600× (SP)**.

---

## Summary — all platforms, all engines (calls/sec, higher = better)

> ⚠ py-ballisticcalc and tiny_bclibc use **different shot configs and step sizes**
> — numbers are not strictly apples-to-apples except for `integrate_at` (same 1 km target).

| Platform | Engine | `integrate` 1 km/s | `integrate_at` /s | `find_zero` 300 m/s | `find_apex` /s |
|---|---|---:|---:|---:|---:|
| RP2040 · armv6m · 125 MHz · no FPU | tiny_bclibc **SP** | **2.8** | **15** | **8.4** | **30** |
| RP2040 · armv6m · 125 MHz · no FPU | tiny_bclibc DP | 1.5 | 8 | 3.0 | 16 |
| ish · iOS · i686 emu · ~25 MFLOPS | tiny_bclibc **SP** | **107.5** | **607** | **331.5** | **1,195** |
| ish · iOS · i686 emu · ~25 MFLOPS | tiny_bclibc DP | 54.0 | 274 | 94.9 | 548 |
| ish · iOS · i686 emu · ~25 MFLOPS | py-balcalc Cython DP ¹ | 99.2 | 255 | 153.0 ² | — |
| XBurst · MIPS LE · mipsel | tiny_bclibc DP (usermod) | 309 | 2,194 | 912.4 | ~3,717 |
| x64 Linux · MicroPython unix | tiny_bclibc **SP** | **2,217** | **16,159** | **7,398** | **41,667** |
| x64 Linux · MicroPython unix | tiny_bclibc DP | 980 | 4,524 | 1,575 | 20,408 |
| x64 Linux · CPython | py-balcalc Cython DP ³ | 2,994 | 18,475 | 1,042 ⁴ | — |

> ¹ `performance_check.py -n 120` (ish).  
> ² py-balcalc zeros at **100 m** on ish (performance_check.py), not 300 m.  
> ³ `benchmark.py -r 1000 -w 100` for trajectory/zero; `performance_check.py -n 10000` for integrate_at.  
> ⁴ py-balcalc zeros at **300 m** here (benchmark.py).

**Key takeaways:**
- `integrate_at` is the most directly comparable call: tiny_bclibc SP is within **15%** of Cython on x64, and **2.4×** faster on ish.
- `find_zero` 300 m: tiny_bclibc SP beats Cython by **7.1×** on x64 and **2.2×** on ish (300 m vs 100 m).
- RP2040 SP is **792×** slower than x64 SP — expected for Cortex-M0+ soft-float vs SSE2.
- SP vs DP overhead grows with algorithm complexity: `integrate` ~1.9–2.3×, `find_zero` 2.8–4.8×.

---

## Raw logs

### tiny_bclibc natmod

| File | Platform | Prec |
|---|---|---|
| [`tiny_bclibc_natmod_bench_x64_sp.log.txt`](tiny_bclibc_natmod_bench_x64_sp.log.txt) | x64 Linux | SP |
| [`tiny_bclibc_usermod_mipsel_dp.log.txt`](logs/tiny_bclibc_usermod_mipsel_dp.log.txt) | XBurst · MIPS LE (usermod) | DP |
| [`tiny_bclibc_natmod_bench_x64_dp.log.txt`](tiny_bclibc_natmod_bench_x64_dp.log.txt) | x64 Linux | DP |
| [`tiny_bclibc_natmod_bench_ish_sp.log.txt`](tiny_bclibc_natmod_bench_ish_sp.log.txt) | ish / iOS / i686 | SP |
| [`tiny_bclibc_natmod_bench_ish_dp.log.txt`](tiny_bclibc_natmod_bench_ish_dp.log.txt) | ish / iOS / i686 | DP |
| [`tiny_bclibc_natmod_bench_sp.log.txt`](tiny_bclibc_natmod_bench_sp.log.txt) | RP2040 single-core | SP |
| [`tiny_bclibc_natmod_bench_dp.log.txt`](tiny_bclibc_natmod_bench_dp.log.txt) | RP2040 single-core | DP |
| [`tiny_bclibc_natmod_bench_2core.log.txt`](tiny_bclibc_natmod_bench_2core.log.txt) | RP2040 dual-core (Core1) | SP |
| [`tiny_bclibc_natmod_bench_2core_dp.log.txt`](tiny_bclibc_natmod_bench_2core_dp.log.txt) | RP2040 dual-core (Core1) | DP |

### py-ballisticcalc CythonizedRK4

| File | Platform |
|---|---|
| [`py_balcalc_cython_bench_x64.log.txt`](py_balcalc_cython_bench_x64.log.txt) | x64 Linux (benchmark.py + performance_check.py) |
| [`py_balcalc_cython_bench_ish.log.txt`](py_balcalc_cython_bench_ish.log.txt) | ish / iOS / i686 |
