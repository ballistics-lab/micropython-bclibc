/* bench_shim.c — native FPU FLOPS micro-benchmark, ffimod backend.
 *
 * Same loop bodies as src/bench_mp.h (natmod/usermod), exported as plain
 * C functions (no mp_obj_t) so ffimod/_tiny_bclibc.py can call them via
 * ffi/ctypes, the same way it calls tiny_bclibc_integrate() etc. Kept as
 * its own ffimod-local file rather than folded into the bclibc submodule's
 * tiny_bclibc_impl.c: bclibc is a separate git repo
 * (ballistics-lab/bclibc, see ../.gitmodules) and this benchmark has
 * nothing to do with the ballistics engine it ships.
 *
 * a, b volatile in the throughput variants for the same reason as
 * bench_mp.h: otherwise GCC constant-folds a*b at compile time and hoists
 * it out of the loop entirely (zero multiply instructions executed),
 * which silently inflates the reported MFLOPS.
 */
#include <stdint.h>

double tiny_bclibc_bench_lat_dp(int64_t n)
{
    volatile double a = 1.00001, b = 1.00002, c = 0.0;
    for (int64_t i = 0; i < n; i++)
    {
        c = c + a * b;
        c = c - a * b;
    }
    return c;
}

double tiny_bclibc_bench_lat_sp(int64_t n)
{
    volatile float a = 1.00001f, b = 1.00002f, c = 0.0f;
    for (int64_t i = 0; i < n; i++)
    {
        c = c + a * b;
        c = c - a * b;
    }
    return (double)c;
}

double tiny_bclibc_bench_thr_dp(int64_t n)
{
    volatile double a = 1.00001, b = 1.00002;
    double c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (int64_t i = 0; i < n; i++)
    {
        c0 += a * b;
        c1 += a * b;
        c2 += a * b;
        c3 += a * b;
        c4 += a * b;
        c5 += a * b;
        c6 += a * b;
        c7 += a * b;
    }
    volatile double sink = c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7;
    return sink;
}

double tiny_bclibc_bench_thr_sp(int64_t n)
{
    volatile float a = 1.00001f, b = 1.00002f;
    float c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (int64_t i = 0; i < n; i++)
    {
        c0 += a * b;
        c1 += a * b;
        c2 += a * b;
        c3 += a * b;
        c4 += a * b;
        c5 += a * b;
        c6 += a * b;
        c7 += a * b;
    }
    volatile float sink = c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7;
    return (double)sink;
}
