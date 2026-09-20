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
 * a, b must stay volatile in the throughput variants: plain locals let GCC
 * constant-fold a*b at compile time and hoist it out of the loop entirely
 * (zero multiply instructions executed), which silently inflates the
 * reported MFLOPS ~2-3x. Mirrors the fix applied to the standalone
 * benchmarks/flops_bench/flops_bench_natmod.c .mpy after that exact bug was
 * found there via disassembly. */
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
    return mp_obj_new_float((mp_float_t)c);
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
    return mp_obj_new_float((mp_float_t)c);
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
    return mp_obj_new_float((mp_float_t)sink);
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
    return mp_obj_new_float((mp_float_t)sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bclibc_bench_thr_sp_obj, mp_bclibc_bench_thr_sp);

#endif /* BENCH_MP_H */
