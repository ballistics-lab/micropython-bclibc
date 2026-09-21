/* bench_mp.h — native FPU FLOPS micro-benchmark (bench() in tiny_bclibc.py)
 *
 * `.h` on purpose despite holding full function bodies, not just
 * declarations: `#include`d exactly once, from tiny_bclibc_mp.c, so these
 * stay `static` instead of needing `extern` across translation units (the
 * same "single amalgamated unit" pattern as bcp/bcp_frame_mp.h) -- never
 * compiled as its own translation unit, never listed in
 * usermod/micropython.mk or .cmake. Unlike the bcp_*_mp.h headers this one
 * is included unconditionally for BOTH natmod and usermod builds, so it
 * must not #include py/obj.h or py/dynruntime.h itself -- it relies on
 * mp_obj_t/mp_int_t and the mp_obj_new_float() macro already being in
 * scope from whichever branch tiny_bclibc_mp.c's own top-of-file #ifdef
 * BCLIBC_BUILD_NATMOD picked before #include-ing this file. The include
 * guard below is defensive only, given the single call site.
 *
 * Raw timing loops only -- wall-clock measurement and MFLOPS formatting
 * happen in Python (tiny_bclibc.py's bench()).
 *
 * a, b must stay volatile in the throughput (thr_*) variants: plain locals
 * let GCC constant-fold a*b at compile time and hoist it out of the loop
 * entirely (zero multiply instructions executed), which silently inflates
 * the reported MFLOPS ~2-3x. Mirrors the fix applied to the standalone
 * benchmarks/flops_bench/flops_bench_natmod.c .mpy after that exact bug was
 * found there via disassembly.
 *
 * peak_* deliberately does NOT need volatile: it's add-only, no multiply,
 * so there's no loop-invariant product to hoist -- and repeated float
 * addition can't be collapsed into a closed form (c + n*a) without
 * -ffast-math, since that would change rounding behaviour, which strict
 * IEEE754 evaluation (the default, and what every build here uses)
 * forbids. So `a` safely stays a plain non-volatile local, GCC keeps it
 * (and all 8 accumulators) resident in FPU registers, and the loop compiles
 * to back-to-back vadd with zero loads/stores -- confirmed via
 * disassembly. This is the same thing flops.py's asm_thumb loop measures
 * (bare register-to-register vadd, no memory traffic at all), just
 * portable C instead of hand-written Cortex-M assembly, and with 8
 * independent accumulators for ILP instead of flops.py's single serial
 * chain of 10. thr_* deliberately pays a real memory-traffic cost (see
 * above) to guarantee 8 independent multiplies aren't optimized away;
 * peak_* has no multiply to protect, so it reports the FPU's actual best
 * case instead of a memory-bound one. */
#ifndef BENCH_MP_H
#define BENCH_MP_H

static mp_obj_t mp_bclibc_bench_lat_dp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile double a = 1.00001, b = 1.00002, c = 0.0;
    for (mp_int_t i = 0; i < n; i++)
    {
        c = c + a * b;
        c = c - a * b;
    }
    return mp_obj_new_float(c);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_lat_dp_obj, mp_bclibc_bench_lat_dp);

static mp_obj_t mp_bclibc_bench_lat_sp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile float a = 1.00001f, b = 1.00002f, c = 0.0f;
    for (mp_int_t i = 0; i < n; i++)
    {
        c = c + a * b;
        c = c - a * b;
    }
    return mp_obj_new_float(c);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_lat_sp_obj, mp_bclibc_bench_lat_sp);

static mp_obj_t mp_bclibc_bench_thr_dp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile double a = 1.00001, b = 1.00002;
    double c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (mp_int_t i = 0; i < n; i++)
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
    return mp_obj_new_float(sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_thr_dp_obj, mp_bclibc_bench_thr_dp);

static mp_obj_t mp_bclibc_bench_thr_sp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile float a = 1.00001f, b = 1.00002f;
    float c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (mp_int_t i = 0; i < n; i++)
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
    return mp_obj_new_float(sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_thr_sp_obj, mp_bclibc_bench_thr_sp);

static mp_obj_t mp_bclibc_bench_peak_dp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    double a = 1.00001;
    double c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (mp_int_t i = 0; i < n; i++)
    {
        c0 += a;
        c1 += a;
        c2 += a;
        c3 += a;
        c4 += a;
        c5 += a;
        c6 += a;
        c7 += a;
    }
    volatile double sink = c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7;
    return mp_obj_new_float(sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_peak_dp_obj, mp_bclibc_bench_peak_dp);

static mp_obj_t mp_bclibc_bench_peak_sp(mp_obj_t n_obj)
{
    mp_int_t n = mp_obj_get_int(n_obj);
    float a = 1.00001f;
    float c0 = 1, c1 = 2, c2 = 3, c3 = 4, c4 = 5, c5 = 6, c6 = 7, c7 = 8;
    for (mp_int_t i = 0; i < n; i++)
    {
        c0 += a;
        c1 += a;
        c2 += a;
        c3 += a;
        c4 += a;
        c5 += a;
        c6 += a;
        c7 += a;
    }
    volatile float sink = c0 + c1 + c2 + c3 + c4 + c5 + c6 + c7;
    return mp_obj_new_float(sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_peak_sp_obj, mp_bclibc_bench_peak_sp);

#endif /* BENCH_MP_H */
