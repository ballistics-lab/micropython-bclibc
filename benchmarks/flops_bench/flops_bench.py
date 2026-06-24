# ruff: noqa

import time
import _flops_bench as fb

# N values tuned for ~1-3s per test on RP2040 (armv6m soft-float ~2-5 MFLOPS)
# Reduce if too slow, increase for more stable numbers on faster platforms.
N_LAT = 500_000  # × 4 ops  = 2M ops
N_THRU = 100_000  # × 16 ops = 1.6M ops


def bench(label, fn, n, ops):
    fn(n // 10)  # warmup
    t0 = time.ticks_us()
    result = fn(n)
    dt = time.ticks_diff(time.ticks_us(), t0) / 1e6
    mflops = n * ops / dt / 1e6
    print("  {:8s}: {:9.2f} MFLOPS   dt={:.3f}s".format(label, mflops, dt))


print("=" * 52)
print("FPU FLOPS Benchmark (native .mpy)")
print("=" * 52)

print("\nLatency-bound (volatile, sequential chain):")
bench("DP", fb.lat_dp, N_LAT, 4)
bench("SP", fb.lat_sp, N_LAT, 4)

print("\nThroughput (8 independent accumulators):")
bench("DP", fb.thr_dp, N_THRU, 16)
bench("SP", fb.thr_sp, N_THRU, 16)

print("=" * 52)
