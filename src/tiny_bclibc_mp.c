/**
 * bclibc_mp.c — MicroPython native module backed by tiny_bclibc (C99, header-only)
 *
 * Python API
 * ----------
 *   import bclibc
 *   from bclibc_types import Shot, Request, Wind, Config
 *
 *   bclibc.version()
 *   bclibc.integrate(shot._buf, shot._holder, req._buf)              -> (list[tuple], int)
 *   bclibc.integrate_stream(shot._buf, shot._holder, req._buf, cb)  -> (int total, int reason)
 *   bclibc.find_zero_angle(shot._buf, shot._holder, dist_ft)        -> float
 *   bclibc.find_apex(shot._buf, shot._holder)                       -> tuple
 *   bclibc.find_max_range(shot._buf, shot._holder, lo, hi)          -> (float_ft, float_rad)
 *   bclibc.integrate_at(shot._buf, shot._holder, key, target)       -> (tuple_base, tuple_full)
 *
 * All shot/request arguments are packed binary buffers produced by
 * bclibc_types.Shot.pack() / Request.pack() — no dict parsing.
 *
 * Shot buffer layout (little-endian, produced by struct '<17f6fiBBH'):
 *   [0-67]   17 × float32: bc, weight_grain, diameter_inch, length_inch,
 *                           muzzle_velocity_fps, sight_height_ft, twist_inch,
 *                           temp_c, pressure_hpa, altitude_ft, humidity,
 *                           look_angle_rad, barrel_elevation_rad,
 *                           barrel_azimuth_rad, cant_angle_rad,
 *                           latitude_deg, azimuth_deg
 *   [68-91]   6 × float32: cStepMultiplier, cZeroFindingAccuracy,
 *                           cMinimumVelocity, cMaximumDrop,
 *                           cGravityConstant, cMinimumAltitude
 *   [92-95]   int32:  cMaxIterations
 *   [96]      uint8:  drag_type (0=G1, 1=G7, 2=custom)
 *   [97]      uint8:  wind_count
 *   [98-99]   uint16: drag_count
 *   [100..]   wind_count × 16 bytes (4 × float32 each)
 *   [100 + wind_count*16 ..] drag_count × 8 bytes (2 × float32 each, custom only)
 *
 * Request buffer layout (struct '<3fi'):
 *   [0-11]  3 × float32: range_limit_ft, range_step_ft, time_step
 *   [12-15] int32: filter_flags
 */

#ifdef BCLIBC_BUILD_NATMOD
#include "py/dynruntime.h"
#undef mp_obj_new_float
#define mp_obj_new_float(d) mp_obj_new_float_from_d((double)(d))
#undef mp_obj_get_float
#define mp_obj_get_float(o) mp_obj_get_float_to_d(o)
/* dynruntime.h defines mp_raise_msg(type, const char*) — pass string directly */
#define _RAISE_BCLIBC_ERROR(msg) mp_raise_msg(&mp_type_ValueError, (msg))
#else
#include "py/obj.h"
#include "py/runtime.h"
#include "py/misc.h"
/* usermod: mp_raise_msg takes mp_rom_error_text_t; use varg with %s for runtime strings */
#define _RAISE_BCLIBC_ERROR(msg) mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("%s"), (msg))
#endif

#include "tiny_bclibc.h"
#include "generated/bclibc_mp/version.h"

/* ── Error helpers ───────────────────────────────────────────────────────── */

static const char *_tiny_bclibc_err_str(int32_t rc)
{
    switch (rc)
    {
    case TINY_BCLIBC_ERR_RUNTIME:
        return "runtime error";
    case TINY_BCLIBC_ERR_OUT_OF_RANGE:
        return "trajectory out of range";
    case TINY_BCLIBC_ERR_ZERO_FINDING:
        return "zero finding failed";
    case TINY_BCLIBC_ERR_INTERCEPTION:
        return "interception error";
    case TINY_BCLIBC_ERR_INVALID_ARG:
        return "invalid argument";
    case TINY_BCLIBC_ERR_BUF_TOO_SMALL:
        return "buffer too small";
    default:
        return "unknown tiny_bclibc error";
    }
}

/* ── Constants ───────────────────────────────────────────────────────────── */

#define MAX_DRAG_PTS 128
#define MAX_WINDS 16

/* Shot buffer offsets (must match bclibc_types._SHOT_HDR layout) */
#define SHOT_HDR_SIZE 100u
#define OFF_CFG_MAXITER 92u /* int32_t */
#define OFF_DRAG_TYPE 96u   /* uint8_t */
#define OFF_WIND_CNT 97u    /* uint8_t */
#define OFF_DRAG_CNT 98u    /* uint16_t */
#define OFF_WINDS_START 100u

/* Request buffer offsets (struct '<3fi') */
#define REQ_SIZE 16u

/* ── Safe unaligned read helpers (byte-by-byte, no <string.h> needed) ────── */

static float _rdf(const uint8_t *p, uint32_t off)
{
    union
    {
        uint32_t u;
        float f;
    } x;
    x.u = (uint32_t)p[off] | ((uint32_t)p[off + 1] << 8) | ((uint32_t)p[off + 2] << 16) | ((uint32_t)p[off + 3] << 24);
    return x.f;
}

static int32_t _rdi(const uint8_t *p, uint32_t off)
{
    return (int32_t)((uint32_t)p[off] | ((uint32_t)p[off + 1] << 8) | ((uint32_t)p[off + 2] << 16) | ((uint32_t)p[off + 3] << 24));
}

static uint16_t _rdu16(const uint8_t *p, uint32_t off)
{
    return (uint16_t)((uint32_t)p[off] | ((uint32_t)p[off + 1] << 8));
}

#include "drag_tables.h"

/* ── Tuple converters ────────────────────────────────────────────────────── */

static mp_obj_t traj_to_tuple(const TINY_BCLIBC_TrajectoryData *r)
{
    mp_obj_t items[16];
    items[0] = mp_obj_new_float(r->time);
    items[1] = mp_obj_new_float(r->distance_ft);
    items[2] = mp_obj_new_float(r->velocity_fps);
    items[3] = mp_obj_new_float(r->mach);
    items[4] = mp_obj_new_float(r->height_ft);
    items[5] = mp_obj_new_float(r->slant_height_ft);
    items[6] = mp_obj_new_float(r->drop_angle_rad);
    items[7] = mp_obj_new_float(r->windage_ft);
    items[8] = mp_obj_new_float(r->windage_angle_rad);
    items[9] = mp_obj_new_float(r->slant_distance_ft);
    items[10] = mp_obj_new_float(r->angle_rad);
    items[11] = mp_obj_new_float(r->density_ratio);
    items[12] = mp_obj_new_float(r->drag);
    items[13] = mp_obj_new_float(r->energy_ft_lb);
    items[14] = mp_obj_new_float(r->ogw_lb);
    items[15] = mp_obj_new_int((mp_int_t)r->flag);
    return mp_obj_new_tuple(16, items);
}

static mp_obj_t base_traj_to_tuple(const TINY_BCLIBC_BaseTrajData *r)
{
    mp_obj_t items[8];
    items[0] = mp_obj_new_float(r->time);
    items[1] = mp_obj_new_float(r->px);
    items[2] = mp_obj_new_float(r->py);
    items[3] = mp_obj_new_float(r->pz);
    items[4] = mp_obj_new_float(r->vx);
    items[5] = mp_obj_new_float(r->vy);
    items[6] = mp_obj_new_float(r->vz);
    items[7] = mp_obj_new_float(r->mach);
    return mp_obj_new_tuple(8, items);
}

/* ── ShotHolder (Python-owned, pre-allocated per Shot instance) ──────────── */

typedef struct
{
    TINY_BCLIBC_Shot shot;
    real_t mach_data[MAX_DRAG_PTS]; /* custom drag only */
    real_t cd_data[MAX_DRAG_PTS];   /* custom drag only */
#ifndef MP_BCLIBC_SINGLE_PRECISION
    TINY_BCLIBC_Wind winds[MAX_WINDS]; /* double build: convert float32 → double */
#endif
    TINY_BCLIBC_CurvePoint curve_buf[MAX_DRAG_PTS];
} ShotHolder;

/* ── Buffer → ShotProps ─────────────────────────────────────────────────── */

static int32_t build_props_buf(mp_obj_t shot_obj, mp_obj_t holder_obj, TINY_BCLIBC_ShotProps *out)
{
    mp_buffer_info_t bi, hi;
    mp_get_buffer_raise(shot_obj, &bi, MP_BUFFER_READ);
    mp_get_buffer_raise(holder_obj, &hi, MP_BUFFER_WRITE);
    if (bi.len < SHOT_HDR_SIZE || hi.len < sizeof(ShotHolder))
        return TINY_BCLIBC_ERR_INVALID_ARG;

    const uint8_t *p = (const uint8_t *)bi.buf;
    ShotHolder *h = (ShotHolder *)hi.buf;
    TINY_BCLIBC_Shot *s = &h->shot;

    /* 17 scalar floats at offsets 0, 4, 8, ... 64 */
    s->bc = (real_t)_rdf(p, 0);
    s->weight_grain = (real_t)_rdf(p, 4);
    s->diameter_inch = (real_t)_rdf(p, 8);
    s->length_inch = (real_t)_rdf(p, 12);
    s->muzzle_velocity_fps = (real_t)_rdf(p, 16);
    s->sight_height_ft = (real_t)_rdf(p, 20);
    s->twist_inch = (real_t)_rdf(p, 24);
    s->temp_c = (real_t)_rdf(p, 28);
    s->pressure_hpa = (real_t)_rdf(p, 32);
    s->altitude_ft = (real_t)_rdf(p, 36);
    s->humidity = (real_t)_rdf(p, 40);
    s->look_angle_rad = (real_t)_rdf(p, 44);
    s->barrel_elevation_rad = (real_t)_rdf(p, 48);
    s->barrel_azimuth_rad = (real_t)_rdf(p, 52);
    s->cant_angle_rad = (real_t)_rdf(p, 56);
    s->latitude_deg = (real_t)_rdf(p, 60);
    s->azimuth_deg = (real_t)_rdf(p, 64);

    /* 6 config floats at offsets 68..88 (Python order), cMaxIterations int32 at 92 */
    s->config.cStepMultiplier = (real_t)_rdf(p, 68);
    s->config.cZeroFindingAccuracy = (real_t)_rdf(p, 72);
    s->config.cMinimumVelocity = (real_t)_rdf(p, 76);
    s->config.cMaximumDrop = (real_t)_rdf(p, 80);
    s->config.cGravityConstant = (real_t)_rdf(p, 84);
    s->config.cMinimumAltitude = (real_t)_rdf(p, 88);
    s->config.cMaxIterations = _rdi(p, OFF_CFG_MAXITER);

    /* drag_type(96), wind_count(97), drag_count(98-99) */
    uint8_t drag_type = p[OFF_DRAG_TYPE];
    uint8_t wind_count = p[OFF_WIND_CNT];
    uint16_t drag_count = _rdu16(p, OFF_DRAG_CNT);

    uint32_t winds_off = OFF_WINDS_START;
    uint32_t drag_off = winds_off + (uint32_t)wind_count * 16u;

    /* validate total buffer length */
    {
        uint32_t needed = drag_off;
        if (drag_type == 2u)
            needed += (uint32_t)drag_count * 8u;
        if ((uint32_t)bi.len < needed)
            return TINY_BCLIBC_ERR_INVALID_ARG;
    }

    /* drag table */
    if (drag_type == 0u)
    { /* G1 — static table, zero-copy */
        s->mach_data = g1_mach;
        s->cd_data = g1_cd;
        s->drag_table_size = G1_N;
    }
    else if (drag_type == 2u)
    { /* custom — de-interleave {mach,cd} pairs into holder arrays */
        int32_t n = (int32_t)drag_count;
        if (n > MAX_DRAG_PTS)
            n = MAX_DRAG_PTS;
        for (int32_t i = 0; i < n; i++)
        {
            uint32_t off = drag_off + (uint32_t)i * 8u;
            h->mach_data[i] = (real_t)_rdf(p, off);
            h->cd_data[i] = (real_t)_rdf(p, off + 4u);
        }
        s->mach_data = h->mach_data;
        s->cd_data = h->cd_data;
        s->drag_table_size = n;
    }
    else
    { /* G7 — static table, zero-copy */
        s->mach_data = g7_mach;
        s->cd_data = g7_cd;
        s->drag_table_size = G7_N;
    }

    /* winds */
    int32_t wn = (int32_t)wind_count;
    if (wn > MAX_WINDS)
        wn = MAX_WINDS;
#ifdef MP_BCLIBC_SINGLE_PRECISION
    /* sp build: TINY_BCLIBC_Wind = {float×4} matches Python buffer layout exactly */
    s->winds = (const TINY_BCLIBC_Wind *)(p + winds_off);
#else
    /* dp build: convert float32 → double per field */
    for (int32_t i = 0; i < wn; i++)
    {
        uint32_t off = winds_off + (uint32_t)i * 16u;
        h->winds[i].velocity_fps = (real_t)_rdf(p, off);
        h->winds[i].direction_from_rad = (real_t)_rdf(p, off + 4u);
        h->winds[i].until_distance_ft = (real_t)_rdf(p, off + 8u);
        h->winds[i].max_distance_ft = (real_t)_rdf(p, off + 12u);
    }
    s->winds = h->winds;
#endif
    s->wind_count = wn;

    return tiny_bclibc_build_shot_props(s, h->curve_buf, out);
}

/* ── Request buffer parser ──────────────────────────────────────────────── */

static void parse_req(mp_obj_t req_obj, TINY_BCLIBC_TrajectoryRequest *req)
{
    mp_buffer_info_t bi;
    mp_get_buffer_raise(req_obj, &bi, MP_BUFFER_READ);
    const uint8_t *p = (const uint8_t *)bi.buf;
    req->range_limit_ft = (real_t)_rdf(p, 0);
    req->range_step_ft = (real_t)_rdf(p, 4);
    req->time_step = (real_t)_rdf(p, 8);
    req->filter_flags = _rdi(p, 12);
}

/* ── Module functions ────────────────────────────────────────────────────── */

static mp_obj_t mp_bclibc_version(void)
{
#ifdef MP_BCLIBC_SINGLE_PRECISION
    static const char _v[] = MP_BCLIBC_VERSION "-sp";
#else
    static const char _v[] = MP_BCLIBC_VERSION "-dp";
#endif
    return mp_obj_new_str(_v, sizeof(_v) - 1);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_bclibc_version_obj, mp_bclibc_version);

static mp_obj_t mp_bclibc_find_zero_angle(mp_obj_t shot_arg, mp_obj_t holder_arg, mp_obj_t dist_arg)
{
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(shot_arg, holder_arg, &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    real_t angle = REAL_C(0.0);
    rc = tiny_bclibc_find_zero_angle(&props, (real_t)mp_obj_get_float(dist_arg), &angle);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    return mp_obj_new_float(angle);
}
static MP_DEFINE_CONST_FUN_OBJ_3(mp_bclibc_find_zero_angle_obj, mp_bclibc_find_zero_angle);

static mp_obj_t mp_bclibc_find_apex(mp_obj_t shot_arg, mp_obj_t holder_arg)
{
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(shot_arg, holder_arg, &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    TINY_BCLIBC_TrajectoryData out;
    rc = tiny_bclibc_find_apex(&props, &out);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    return traj_to_tuple(&out);
}
static MP_DEFINE_CONST_FUN_OBJ_2(mp_bclibc_find_apex_obj, mp_bclibc_find_apex);

static mp_obj_t mp_bclibc_find_max_range(size_t n_args, const mp_obj_t *args)
{
    /* args: shot, holder, lo, hi */
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(args[0], args[1], &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    real_t out_range = REAL_C(0.0), out_angle = REAL_C(0.0);
    rc = tiny_bclibc_find_max_range(&props,
                                    (real_t)mp_obj_get_float(args[2]),
                                    (real_t)mp_obj_get_float(args[3]),
                                    &out_range, &out_angle);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    mp_obj_t items[2] = {
        mp_obj_new_float(out_range),
        mp_obj_new_float(out_angle),
    };
    return mp_obj_new_tuple(2, items);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bclibc_find_max_range_obj, 4, 4, mp_bclibc_find_max_range);

static mp_obj_t mp_bclibc_integrate(size_t n_args, const mp_obj_t *args)
{
    /* args: shot, holder, req, traj_buf */
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(args[0], args[1], &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));

    TINY_BCLIBC_TrajectoryRequest req;
    parse_req(args[2], &req);

    mp_buffer_info_t tbi;
    mp_get_buffer_raise(args[3], &tbi, MP_BUFFER_WRITE);
    TINY_BCLIBC_TrajectoryData *buf = (TINY_BCLIBC_TrajectoryData *)tbi.buf;
    int32_t cap = (int32_t)(tbi.len / sizeof(TINY_BCLIBC_TrajectoryData));

    int32_t written = 0, total = 0, reason = 0;
    rc = tiny_bclibc_integrate(&props, &req, buf, cap, &written, &total, &reason);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));

    mp_obj_t list = mp_obj_new_list(0, NULL);
    for (int32_t i = 0; i < written; i++)
        mp_obj_list_append(list, traj_to_tuple(&buf[i]));

    mp_obj_t result[2] = {list, mp_obj_new_int((mp_int_t)reason)};
    return mp_obj_new_tuple(2, result);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bclibc_integrate_obj, 4, 4, mp_bclibc_integrate);

/* ── integrate_stream ────────────────────────────────────────────────────── */

typedef struct
{
    mp_obj_t callable;
} StreamCbCtx;

static int32_t mp_stream_cb(const TINY_BCLIBC_TrajectoryData *pt, void *ctx_)
{
    StreamCbCtx *ctx = (StreamCbCtx *)ctx_;
    mp_obj_t tup = traj_to_tuple(pt);
    mp_obj_t ret = mp_call_function_n_kw(ctx->callable, 1, 0, &tup);
    return mp_obj_is_true(ret) ? TINY_BCLIBC_TERM_HANDLER_STOP : 0;
}

static mp_obj_t mp_bclibc_integrate_stream(size_t n_args, const mp_obj_t *args)
{
    /* args: shot, holder, req, cb */
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(args[0], args[1], &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));

    TINY_BCLIBC_TrajectoryRequest req;
    parse_req(args[2], &req);

    StreamCbCtx cb_ctx = {args[3]};
    int32_t total = 0, reason = 0;
    rc = tiny_bclibc_integrate_stream(&props, &req, mp_stream_cb, &cb_ctx, &total, &reason);

    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));

    mp_obj_t result[2] = {mp_obj_new_int(total), mp_obj_new_int(reason)};
    return mp_obj_new_tuple(2, result);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bclibc_integrate_stream_obj, 4, 4, mp_bclibc_integrate_stream);

static mp_obj_t mp_bclibc_integrate_at(size_t n_args, const mp_obj_t *args)
{
    /* args: shot, holder, key, target */
    TINY_BCLIBC_ShotProps props;
    int32_t rc = build_props_buf(args[0], args[1], &props);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    TINY_BCLIBC_BaseTrajData raw;
    TINY_BCLIBC_TrajectoryData full;
    rc = tiny_bclibc_integrate_at(&props,
                                  (int32_t)mp_obj_get_int(args[2]),
                                  (real_t)mp_obj_get_float(args[3]),
                                  &raw, &full);
    if (rc != TINY_BCLIBC_OK)
        _RAISE_BCLIBC_ERROR(_tiny_bclibc_err_str(rc));
    mp_obj_t result[2] = {base_traj_to_tuple(&raw), traj_to_tuple(&full)};
    return mp_obj_new_tuple(2, result);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bclibc_integrate_at_obj, 4, 4, mp_bclibc_integrate_at);

/* ── Module entry point ──────────────────────────────────────────────────── */

#ifdef BCLIBC_BUILD_NATMOD

mp_obj_t mpy_init(mp_obj_fun_bc_t *self, size_t n_args, size_t n_kw, mp_obj_t *args)
{
    MP_DYNRUNTIME_INIT_ENTRY

    mp_store_global(MP_QSTR_SHOT_HOLDER_SIZE, MP_OBJ_NEW_SMALL_INT((mp_int_t)sizeof(ShotHolder)));
    mp_store_global(MP_QSTR_TRAJ_DATA_SIZE, MP_OBJ_NEW_SMALL_INT((mp_int_t)sizeof(TINY_BCLIBC_TrajectoryData)));
    mp_store_global(MP_QSTR_version, MP_OBJ_FROM_PTR(&mp_bclibc_version_obj));
    mp_store_global(MP_QSTR_integrate, MP_OBJ_FROM_PTR(&mp_bclibc_integrate_obj));
    mp_store_global(MP_QSTR_integrate_stream, MP_OBJ_FROM_PTR(&mp_bclibc_integrate_stream_obj));
    mp_store_global(MP_QSTR_find_zero_angle, MP_OBJ_FROM_PTR(&mp_bclibc_find_zero_angle_obj));
    mp_store_global(MP_QSTR_find_apex, MP_OBJ_FROM_PTR(&mp_bclibc_find_apex_obj));
    mp_store_global(MP_QSTR_find_max_range, MP_OBJ_FROM_PTR(&mp_bclibc_find_max_range_obj));
    mp_store_global(MP_QSTR_integrate_at, MP_OBJ_FROM_PTR(&mp_bclibc_integrate_at_obj));

    /* Trajectory flag constants */
    mp_store_global(MP_QSTR_TRAJ_FLAG_NONE, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_NONE));
    mp_store_global(MP_QSTR_TRAJ_FLAG_ZERO_UP, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO_UP));
    mp_store_global(MP_QSTR_TRAJ_FLAG_ZERO_DOWN, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO_DOWN));
    mp_store_global(MP_QSTR_TRAJ_FLAG_ZERO, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO));
    mp_store_global(MP_QSTR_TRAJ_FLAG_MACH, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_MACH));
    mp_store_global(MP_QSTR_TRAJ_FLAG_RANGE, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_RANGE));
    mp_store_global(MP_QSTR_TRAJ_FLAG_APEX, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_APEX));
    mp_store_global(MP_QSTR_TRAJ_FLAG_ALL, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_ALL));
    mp_store_global(MP_QSTR_TRAJ_FLAG_MRT, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_TRAJ_FLAG_MRT));

    /* Interpolation key constants */
    mp_store_global(MP_QSTR_INTERP_TIME, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_TIME));
    mp_store_global(MP_QSTR_INTERP_MACH, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_MACH));
    mp_store_global(MP_QSTR_INTERP_POS_X, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_POS_X));
    mp_store_global(MP_QSTR_INTERP_POS_Y, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_POS_Y));
    mp_store_global(MP_QSTR_INTERP_POS_Z, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_POS_Z));
    mp_store_global(MP_QSTR_INTERP_VEL_X, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_VEL_X));
    mp_store_global(MP_QSTR_INTERP_VEL_Y, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_VEL_Y));
    mp_store_global(MP_QSTR_INTERP_VEL_Z, MP_OBJ_NEW_SMALL_INT(TINY_BCLIBC_KEY_VEL_Z));

    /* Trajectory tuple field indices */
    mp_store_global(MP_QSTR_T_TIME, MP_OBJ_NEW_SMALL_INT(0));
    mp_store_global(MP_QSTR_T_DISTANCE, MP_OBJ_NEW_SMALL_INT(1));
    mp_store_global(MP_QSTR_T_VELOCITY, MP_OBJ_NEW_SMALL_INT(2));
    mp_store_global(MP_QSTR_T_MACH, MP_OBJ_NEW_SMALL_INT(3));
    mp_store_global(MP_QSTR_T_HEIGHT, MP_OBJ_NEW_SMALL_INT(4));
    mp_store_global(MP_QSTR_T_SLANT_HEIGHT, MP_OBJ_NEW_SMALL_INT(5));
    mp_store_global(MP_QSTR_T_DROP_ANGLE, MP_OBJ_NEW_SMALL_INT(6));
    mp_store_global(MP_QSTR_T_WINDAGE, MP_OBJ_NEW_SMALL_INT(7));
    mp_store_global(MP_QSTR_T_WINDAGE_ANGLE, MP_OBJ_NEW_SMALL_INT(8));
    mp_store_global(MP_QSTR_T_SLANT_DISTANCE, MP_OBJ_NEW_SMALL_INT(9));
    mp_store_global(MP_QSTR_T_ANGLE, MP_OBJ_NEW_SMALL_INT(10));
    mp_store_global(MP_QSTR_T_DENSITY_RATIO, MP_OBJ_NEW_SMALL_INT(11));
    mp_store_global(MP_QSTR_T_DRAG, MP_OBJ_NEW_SMALL_INT(12));
    mp_store_global(MP_QSTR_T_ENERGY, MP_OBJ_NEW_SMALL_INT(13));
    mp_store_global(MP_QSTR_T_OGW, MP_OBJ_NEW_SMALL_INT(14));
    mp_store_global(MP_QSTR_T_FLAG, MP_OBJ_NEW_SMALL_INT(15));

    MP_DYNRUNTIME_INIT_EXIT
}

#else /* usermod — static ROM dict registered via MP_REGISTER_MODULE */

static const mp_rom_map_elem_t bclibc_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__tiny_bclibc)},
    /* size constants */
    {MP_ROM_QSTR(MP_QSTR_SHOT_HOLDER_SIZE), MP_ROM_INT(sizeof(ShotHolder))},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_DATA_SIZE), MP_ROM_INT(sizeof(TINY_BCLIBC_TrajectoryData))},
    /* functions */
    {MP_ROM_QSTR(MP_QSTR_version), MP_ROM_PTR(&mp_bclibc_version_obj)},
    {MP_ROM_QSTR(MP_QSTR_integrate), MP_ROM_PTR(&mp_bclibc_integrate_obj)},
    {MP_ROM_QSTR(MP_QSTR_integrate_stream), MP_ROM_PTR(&mp_bclibc_integrate_stream_obj)},
    {MP_ROM_QSTR(MP_QSTR_find_zero_angle), MP_ROM_PTR(&mp_bclibc_find_zero_angle_obj)},
    {MP_ROM_QSTR(MP_QSTR_find_apex), MP_ROM_PTR(&mp_bclibc_find_apex_obj)},
    {MP_ROM_QSTR(MP_QSTR_find_max_range), MP_ROM_PTR(&mp_bclibc_find_max_range_obj)},
    {MP_ROM_QSTR(MP_QSTR_integrate_at), MP_ROM_PTR(&mp_bclibc_integrate_at_obj)},
    /* trajectory flags */
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_NONE), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_NONE)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_ZERO_UP), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO_UP)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_ZERO_DOWN), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO_DOWN)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_ZERO), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_ZERO)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_MACH), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_MACH)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_RANGE), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_RANGE)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_APEX), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_APEX)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_ALL), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_ALL)},
    {MP_ROM_QSTR(MP_QSTR_TRAJ_FLAG_MRT), MP_ROM_INT(TINY_BCLIBC_TRAJ_FLAG_MRT)},
    /* interpolation keys */
    {MP_ROM_QSTR(MP_QSTR_INTERP_TIME), MP_ROM_INT(TINY_BCLIBC_KEY_TIME)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_MACH), MP_ROM_INT(TINY_BCLIBC_KEY_MACH)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_POS_X), MP_ROM_INT(TINY_BCLIBC_KEY_POS_X)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_POS_Y), MP_ROM_INT(TINY_BCLIBC_KEY_POS_Y)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_POS_Z), MP_ROM_INT(TINY_BCLIBC_KEY_POS_Z)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_VEL_X), MP_ROM_INT(TINY_BCLIBC_KEY_VEL_X)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_VEL_Y), MP_ROM_INT(TINY_BCLIBC_KEY_VEL_Y)},
    {MP_ROM_QSTR(MP_QSTR_INTERP_VEL_Z), MP_ROM_INT(TINY_BCLIBC_KEY_VEL_Z)},
    /* trajectory tuple field indices */
    {MP_ROM_QSTR(MP_QSTR_T_TIME), MP_ROM_INT(0)},
    {MP_ROM_QSTR(MP_QSTR_T_DISTANCE), MP_ROM_INT(1)},
    {MP_ROM_QSTR(MP_QSTR_T_VELOCITY), MP_ROM_INT(2)},
    {MP_ROM_QSTR(MP_QSTR_T_MACH), MP_ROM_INT(3)},
    {MP_ROM_QSTR(MP_QSTR_T_HEIGHT), MP_ROM_INT(4)},
    {MP_ROM_QSTR(MP_QSTR_T_SLANT_HEIGHT), MP_ROM_INT(5)},
    {MP_ROM_QSTR(MP_QSTR_T_DROP_ANGLE), MP_ROM_INT(6)},
    {MP_ROM_QSTR(MP_QSTR_T_WINDAGE), MP_ROM_INT(7)},
    {MP_ROM_QSTR(MP_QSTR_T_WINDAGE_ANGLE), MP_ROM_INT(8)},
    {MP_ROM_QSTR(MP_QSTR_T_SLANT_DISTANCE), MP_ROM_INT(9)},
    {MP_ROM_QSTR(MP_QSTR_T_ANGLE), MP_ROM_INT(10)},
    {MP_ROM_QSTR(MP_QSTR_T_DENSITY_RATIO), MP_ROM_INT(11)},
    {MP_ROM_QSTR(MP_QSTR_T_DRAG), MP_ROM_INT(12)},
    {MP_ROM_QSTR(MP_QSTR_T_ENERGY), MP_ROM_INT(13)},
    {MP_ROM_QSTR(MP_QSTR_T_OGW), MP_ROM_INT(14)},
    {MP_ROM_QSTR(MP_QSTR_T_FLAG), MP_ROM_INT(15)},
};
static MP_DEFINE_CONST_DICT(bclibc_module_globals, bclibc_module_globals_table);

const mp_obj_module_t tiny_bclibc_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&bclibc_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__tiny_bclibc, tiny_bclibc_module);

#endif /* BCLIBC_BUILD_NATMOD */
