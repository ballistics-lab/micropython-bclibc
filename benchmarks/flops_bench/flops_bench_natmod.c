#include "py/dynruntime.h"

/* Latency-bound: volatile forces stack reads; c depends on prev c → no ILP */
static mp_obj_t lat_dp(mp_obj_t n_obj) {
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile double a = 1.00001, b = 1.00002, c = 0.0;
    for (mp_int_t i = 0; i < n; i++) { c = c + a * b; c = c - a * b; }
    return mp_obj_new_float((mp_float_t)c);
}
static MP_DEFINE_CONST_FUN_OBJ_1(lat_dp_obj, lat_dp);

static mp_obj_t lat_sp(mp_obj_t n_obj) {
    mp_int_t n = mp_obj_get_int(n_obj);
    volatile float a = 1.00001f, b = 1.00002f, c = 0.0f;
    for (mp_int_t i = 0; i < n; i++) { c = c + a * b; c = c - a * b; }
    return mp_obj_new_float((mp_float_t)c);
}
static MP_DEFINE_CONST_FUN_OBJ_1(lat_sp_obj, lat_sp);

/* Throughput: 8 independent accumulators; compiler can interleave ops */
static mp_obj_t thr_dp(mp_obj_t n_obj) {
    mp_int_t n = mp_obj_get_int(n_obj);
    double a = 1.00001, b = 1.00002;
    double c0=1,c1=2,c2=3,c3=4,c4=5,c5=6,c6=7,c7=8;
    for (mp_int_t i = 0; i < n; i++) {
        c0+=a*b; c1+=a*b; c2+=a*b; c3+=a*b;
        c4+=a*b; c5+=a*b; c6+=a*b; c7+=a*b;
    }
    volatile double sink = c0+c1+c2+c3+c4+c5+c6+c7;
    return mp_obj_new_float((mp_float_t)sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(thr_dp_obj, thr_dp);

static mp_obj_t thr_sp(mp_obj_t n_obj) {
    mp_int_t n = mp_obj_get_int(n_obj);
    float a = 1.00001f, b = 1.00002f;
    float c0=1,c1=2,c2=3,c3=4,c4=5,c5=6,c6=7,c7=8;
    for (mp_int_t i = 0; i < n; i++) {
        c0+=a*b; c1+=a*b; c2+=a*b; c3+=a*b;
        c4+=a*b; c5+=a*b; c6+=a*b; c7+=a*b;
    }
    volatile float sink = c0+c1+c2+c3+c4+c5+c6+c7;
    return mp_obj_new_float((mp_float_t)sink);
}
static MP_DEFINE_CONST_FUN_OBJ_1(thr_sp_obj, thr_sp);

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args) {
    MP_DYNRUNTIME_INIT_ENTRY
    mp_store_global(MP_QSTR_lat_dp, MP_OBJ_FROM_PTR(&lat_dp_obj));
    mp_store_global(MP_QSTR_lat_sp, MP_OBJ_FROM_PTR(&lat_sp_obj));
    mp_store_global(MP_QSTR_thr_dp, MP_OBJ_FROM_PTR(&thr_dp_obj));
    mp_store_global(MP_QSTR_thr_sp, MP_OBJ_FROM_PTR(&thr_sp_obj));
    MP_DYNRUNTIME_INIT_EXIT
}
