/* bcp_dispatch_mp.c — BCP command dispatch (PROTOCOL.md §4). Only compiled
 * when BCLIBC_BCP=1 (see usermod/micropython.mk/.cmake).
 *
 * bcp_frame_mp.c owns wire framing (COBS+CRC16, header pack/unpack) and
 * knows nothing about what a command *means*; this file owns command
 * semantics and knows nothing about wire framing. A future C read/write
 * loop calls both: parse_frame() -> dispatch() -> build_frame(). For now
 * dispatch() is also directly callable from Python (see
 * tests/test_bcp_dispatch_native.py) for testing without that loop.
 *
 * Cached state (BcpState below) is native, typed C -- TINY_BCLIBC_Shot,
 * the engine's own raw-field struct, not a byte-packed buffer. Earlier
 * drafts of this file kept a `_SHOT_DESC`-shaped byte buffer instead,
 * because tiny_bclibc_mp.c's existing Python-facing functions expect a
 * buffer-protocol object. That constraint doesn't apply here: this file
 * is meant to call straight into the C engine (tiny_bclibc_build_shot_props(),
 * tiny_bclibc_find_zero_angle(), etc. -- wired up starting with
 * LOAD_PROFILE, next), never through Python objects -- a real-time
 * target has no business converting through Python just to call C. Once
 * state is a native struct, winds and the drag curve are
 * independent pointers/arrays (TINY_BCLIBC_Shot's own shape), so there's
 * no byte-offset interleaving to manage regardless of which order
 * LOAD_PROFILE/LOAD_CONDITIONS arrive in.
 *
 * Only IDENT and LOAD_CONFIG are implemented so far — see BACKLOG.md
 * Epic 3/8 for the rest of the command table; unimplemented commands raise
 * NotImplementedError (a development-time signal, not a wire status —
 * production dispatch will route every BCP_CMD_* to a real handler before
 * this ships).
 */

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "py/misc.h"

#include "tiny_bclibc.h"
#include "generated/bclibc_mp/version.h"
#include "drag_tables.h" /* g1_mach/g1_cd/g7_mach/g7_cd, G1_N/G7_N -- same header tiny_bclibc_mp.c uses */

/* ── Command ids (PROTOCOL.md §4) — final, not provisional ──────────────── */
enum
{
    BCP_CMD_LOAD_PROFILE = 1,
    BCP_CMD_LOAD_CONFIG = 2,
    BCP_CMD_LOAD_CONDITIONS = 3,
    BCP_CMD_INTEGRATE = 4,
    BCP_CMD_INTEGRATE_FAST = 5,
    BCP_CMD_INTEGRATE_AT = 6,
    BCP_CMD_RESET = 7,
    BCP_CMD_IDENT = 8,
    BCP_CMD_ABORT = 9,
};

/* ── Status codes — mirror bcp_frame's STATUS_* (PROTOCOL.md §3) ─────────── */
enum
{
    BCP_STATUS_OK = 0,
    BCP_STATUS_MORE = 1,
    BCP_STATUS_INTERRUPTED = 2,
    BCP_STATUS_ERR_BAD_SIZE = 3,
    BCP_STATUS_ERR_BAD_ARG = 4,
    BCP_STATUS_ERR_NOT_LOADED = 5,
    BCP_STATUS_ERR_INTERNAL = 6,
};

/* ── BCP-specific size caps (PROTOCOL.md §4.1) — tighter than tiny_bclibc's
 * own internal limits, matching the .a7p profile schema's own precedent
 * (BACKLOG.md Epic 8, "MultiBC wire exposure"). Not the same constants as
 * tiny_bclibc's MAX_WINDS/MAX_DRAG_PTS/MAX_BC_POINTS (16/200/16). */
#define BCP_MAX_WINDS 5u
#define BCP_MAX_DRAG_PTS 200u
#define BCP_MAX_BC_POINTS 5u

#define BCP_PROTO_VERSION 1u

/* From bcp_frame_mp.c — frames dropped for bad COBS/size/CRC since boot. */
extern uint32_t bcp_frame_drop_count(void);

/* ── Explicit byte-order wire helpers (response packing / payload parsing)
 * -- same convention as tiny_bclibc_mp.c's own _rdf()/_wrf() (a union
 * would work too on our little-endian-only targets, but this is correct
 * regardless). Only used at the wire boundary now -- the cached state
 * itself is native C, not bytes. */
static void bcp_wu16(uint8_t *p, size_t off, uint16_t v)
{
    p[off] = (uint8_t)(v & 0xFFu);
    p[off + 1] = (uint8_t)((v >> 8) & 0xFFu);
}

static void bcp_wu32(uint8_t *p, size_t off, uint32_t v)
{
    for (int i = 0; i < 4; i++)
    {
        p[off + i] = (uint8_t)((v >> (8 * i)) & 0xFFu);
    }
}

static void bcp_wf32(uint8_t *p, size_t off, float v)
{
    union
    {
        uint32_t u;
        float f;
    } x;
    x.f = v;
    bcp_wu32(p, off, x.u);
}

static float bcp_rdf32(const uint8_t *p, size_t off)
{
    union
    {
        uint32_t u;
        float f;
    } x;
    x.u = (uint32_t)p[off] | ((uint32_t)p[off + 1] << 8) | ((uint32_t)p[off + 2] << 16) | ((uint32_t)p[off + 3] << 24);
    return x.f;
}

static int32_t bcp_rdi32(const uint8_t *p, size_t off)
{
    return (int32_t)((uint32_t)p[off] | ((uint32_t)p[off + 1] << 8) | ((uint32_t)p[off + 2] << 16) | ((uint32_t)p[off + 3] << 24));
}

/* ── Persistent BCP state ──────────────────────────────────────────────────
 * Survives across dispatch() calls until RESET (not implemented yet).
 * `shot` is TINY_BCLIBC_Shot -- the engine's own raw-field struct, the
 * exact input tiny_bclibc_build_shot_props() already expects. Winds and
 * the drag curve are independent backing arrays that `shot.winds`/
 * `shot.mach_data`/`shot.cd_data` point into (or, for G1/G7, directly at
 * the static reference tables below, zero-copy) -- no interleaving, no
 * offset arithmetic, regardless of which order LOAD_PROFILE/
 * LOAD_CONDITIONS arrive in. */
typedef struct
{
    TINY_BCLIBC_Shot shot;
    real_t drag_mach[BCP_MAX_DRAG_PTS]; /* backing storage for CUSTOM or MULTIBC curves */
    real_t drag_cd[BCP_MAX_DRAG_PTS];
    TINY_BCLIBC_Wind winds[BCP_MAX_WINDS];
    TINY_BCLIBC_CurvePoint curve_buf[BCP_MAX_DRAG_PTS]; /* scratch for tiny_bclibc_build_shot_props()'s PCHIP */
    bool has_profile;
    bool has_config;
    bool has_conditions;
    bool ready;
} BcpState;
static BcpState bcp_state;

/* Lazy init on first dispatch() call: usermod modules have no natmod-style
 * mpy_init hook to run this at boot instead. Config defaults come straight
 * from the engine's own TINY_BCLIBC_Config_default() -- not hand-copied
 * numbers, so there's no way for this to drift from what the library
 * itself considers "default" (the same class of mistake this session
 * already hit once, hand-transcribing the COBS test vectors). */
static void bcp_state_ensure_init(void)
{
    if (bcp_state.ready)
    {
        return;
    }
    bcp_state.shot.config = TINY_BCLIBC_Config_default();
    bcp_state.ready = true;
}

/* ── LOAD_CONFIG (PROTOCOL.md §4.2a) ──────────────────────────────────────
 * Request: fixed 28 B. Field-by-field parse, not a memcpy: the wire order
 * (step_multiplier..minimum_altitude, max_iterations last) differs from
 * TINY_BCLIBC_Config's own field order (cMaxIterations sits before
 * cGravityConstant/cMinimumAltitude there). No variable-length part, so
 * its "array-count rule" (§4.1) reduces to an exact size match.
 *
 * Response: barrel_elevation_rad -- solver tuning affects the zero-angle
 * solve too, so LOAD_CONFIG re-triggers it exactly like LOAD_PROFILE/
 * LOAD_CONDITIONS. **Not wired yet**: that re-solve needs a cached
 * zero_distance_ft, which only exists once LOAD_PROFILE is implemented
 * (next). Until then, config is still validated and stored for real --
 * only the "answer with a solved zero" half is deferred, reported
 * honestly as ERR_NOT_LOADED rather than faked.
 */
#define BCP_LOAD_CONFIG_SIZE 28u

static int bcp_handle_load_config(const uint8_t *payload, size_t payload_len, uint8_t status_out[1])
{
    if (payload_len != BCP_LOAD_CONFIG_SIZE)
    {
        status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_SIZE;
        return 0;
    }
    bcp_state.shot.config.cStepMultiplier = (real_t)bcp_rdf32(payload, 0);
    bcp_state.shot.config.cZeroFindingAccuracy = (real_t)bcp_rdf32(payload, 4);
    bcp_state.shot.config.cMinimumVelocity = (real_t)bcp_rdf32(payload, 8);
    bcp_state.shot.config.cMaximumDrop = (real_t)bcp_rdf32(payload, 12);
    bcp_state.shot.config.cGravityConstant = (real_t)bcp_rdf32(payload, 16);
    bcp_state.shot.config.cMinimumAltitude = (real_t)bcp_rdf32(payload, 20);
    bcp_state.shot.config.cMaxIterations = bcp_rdi32(payload, 24);
    bcp_state.has_config = true;

    if (!bcp_state.has_profile)
    {
        /* Nothing cached to solve a zero against yet -- see the comment
         * above. Config is stored regardless. */
        status_out[0] = (uint8_t)BCP_STATUS_ERR_NOT_LOADED;
        return 0;
    }
    /* TODO(LOAD_PROFILE): re-solve the zero against zero_distance_ft here
     * and return barrel_elevation_rad:f32. Unreachable today since
     * bcp_state.has_profile can't yet become true. */
    status_out[0] = (uint8_t)BCP_STATUS_ERR_INTERNAL;
    return 0;
}

/* ── IDENT (PROTOCOL.md §4.6) ─────────────────────────────────────────────
 * No request payload (ignored). Response, fixed part matches struct format
 * "<BBHHBHBIB" (15 B) followed by the version string:
 *   0  proto_ver      u8
 *   1  real_size      u8   -- sizeof(real_t): 4 (sp) or 8 (dp)
 *   2  traj_row_size  u16  -- sizeof(TINY_BCLIBC_TrajectoryData)
 *   4  base_traj_size u16  -- sizeof(TINY_BCLIBC_BaseTrajData)
 *   6  max_winds      u8
 *   7  max_drag_pts   u16
 *   9  max_bc_points  u8
 *   10 drop_count     u32
 *   14 version_len    u8
 *   15 version        bytes[version_len]
 */
static size_t bcp_handle_ident(uint8_t *out, size_t out_cap)
{
#ifdef TINY_BCLIBC_SINGLE_PRECISION
    static const char ver_suffix[] = "-sp";
#else
    static const char ver_suffix[] = "-dp";
#endif
    char version[32];
    int vlen = snprintf(version, sizeof(version), "%s%s", MP_BCLIBC_VERSION, ver_suffix);
    if (vlen < 0)
    {
        vlen = 0;
    }
    if ((size_t)vlen > sizeof(version))
    {
        vlen = (int)sizeof(version);
    }

    size_t fixed = 15u;
    size_t total = fixed + (size_t)vlen;
    if (out_cap < total)
    {
        return (size_t)-1;
    }

    out[0] = (uint8_t)BCP_PROTO_VERSION;
    out[1] = (uint8_t)sizeof(real_t);
    bcp_wu16(out, 2, (uint16_t)sizeof(TINY_BCLIBC_TrajectoryData));
    bcp_wu16(out, 4, (uint16_t)sizeof(TINY_BCLIBC_BaseTrajData));
    out[6] = (uint8_t)BCP_MAX_WINDS;
    bcp_wu16(out, 7, (uint16_t)BCP_MAX_DRAG_PTS);
    out[9] = (uint8_t)BCP_MAX_BC_POINTS;
    bcp_wu32(out, 10, bcp_frame_drop_count());
    out[14] = (uint8_t)vlen;
    memcpy(out + fixed, version, (size_t)vlen);
    return total;
}

/* ── dispatch(type_, seq, payload) -> (status, response_payload) ─────────
 * `seq` is accepted but not yet used by any handler (no handler needs to
 * echo/branch on it yet -- IDENT doesn't care who's asking). Kept in the
 * signature now so the call shape matches PROTOCOL.md's per-command
 * table from the start, instead of changing it once a command that does
 * need `seq` lands. */
static mp_obj_t mp_bcp_dispatch(mp_obj_t type_obj, mp_obj_t seq_obj, mp_obj_t payload_obj)
{
    (void)seq_obj;
    bcp_state_ensure_init();
    uint8_t type_ = (uint8_t)mp_obj_get_int(type_obj);

    switch (type_)
    {
    case BCP_CMD_IDENT:
    {
        uint8_t out[15 + 32];
        size_t n = bcp_handle_ident(out, sizeof(out));
        if (n == (size_t)-1)
        {
            mp_obj_t items[2] = {MP_OBJ_NEW_SMALL_INT(BCP_STATUS_ERR_INTERNAL), mp_const_empty_bytes};
            return mp_obj_new_tuple(2, items);
        }
        mp_obj_t items[2] = {MP_OBJ_NEW_SMALL_INT(BCP_STATUS_OK), mp_obj_new_bytes(out, n)};
        return mp_obj_new_tuple(2, items);
    }
    case BCP_CMD_LOAD_CONFIG:
    {
        mp_buffer_info_t pbi;
        mp_get_buffer_raise(payload_obj, &pbi, MP_BUFFER_READ);
        uint8_t status;
        int ok = bcp_handle_load_config((const uint8_t *)pbi.buf, pbi.len, &status);
        mp_obj_t resp_payload = mp_const_empty_bytes;
        if (ok)
        {
            uint8_t out[4];
            bcp_wf32(out, 0, (float)bcp_state.shot.barrel_elevation_rad);
            resp_payload = mp_obj_new_bytes(out, sizeof(out));
        }
        mp_obj_t items[2] = {MP_OBJ_NEW_SMALL_INT(status), resp_payload};
        return mp_obj_new_tuple(2, items);
    }
    default:
        /* mp_raise_NotImplementedError() is a natmod-only (dynruntime.h)
         * macro; mp_type_NotImplementedError itself is declared directly
         * in py/obj.h for usermod, so call mp_raise_msg with it plainly. */
        mp_raise_msg(&mp_type_NotImplementedError, MP_ERROR_TEXT("BCP command not implemented yet"));
    }
}
static MP_DEFINE_CONST_FUN_OBJ_3(mp_bcp_dispatch_obj, mp_bcp_dispatch);

/* ── Module registration (usermod only — BCLIBC_BCP is usermod-only) ────── */

static const mp_rom_map_elem_t bcp_dispatch_module_globals_table[] = {
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR__bcp_dispatch)},
    {MP_ROM_QSTR(MP_QSTR_dispatch), MP_ROM_PTR(&mp_bcp_dispatch_obj)},
    {MP_ROM_QSTR(MP_QSTR_CMD_LOAD_PROFILE), MP_ROM_INT(BCP_CMD_LOAD_PROFILE)},
    {MP_ROM_QSTR(MP_QSTR_CMD_LOAD_CONFIG), MP_ROM_INT(BCP_CMD_LOAD_CONFIG)},
    {MP_ROM_QSTR(MP_QSTR_CMD_LOAD_CONDITIONS), MP_ROM_INT(BCP_CMD_LOAD_CONDITIONS)},
    {MP_ROM_QSTR(MP_QSTR_CMD_INTEGRATE), MP_ROM_INT(BCP_CMD_INTEGRATE)},
    {MP_ROM_QSTR(MP_QSTR_CMD_INTEGRATE_FAST), MP_ROM_INT(BCP_CMD_INTEGRATE_FAST)},
    {MP_ROM_QSTR(MP_QSTR_CMD_INTEGRATE_AT), MP_ROM_INT(BCP_CMD_INTEGRATE_AT)},
    {MP_ROM_QSTR(MP_QSTR_CMD_RESET), MP_ROM_INT(BCP_CMD_RESET)},
    {MP_ROM_QSTR(MP_QSTR_CMD_IDENT), MP_ROM_INT(BCP_CMD_IDENT)},
    {MP_ROM_QSTR(MP_QSTR_CMD_ABORT), MP_ROM_INT(BCP_CMD_ABORT)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_OK), MP_ROM_INT(BCP_STATUS_OK)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_MORE), MP_ROM_INT(BCP_STATUS_MORE)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_INTERRUPTED), MP_ROM_INT(BCP_STATUS_INTERRUPTED)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_ERR_BAD_SIZE), MP_ROM_INT(BCP_STATUS_ERR_BAD_SIZE)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_ERR_BAD_ARG), MP_ROM_INT(BCP_STATUS_ERR_BAD_ARG)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_ERR_NOT_LOADED), MP_ROM_INT(BCP_STATUS_ERR_NOT_LOADED)},
    {MP_ROM_QSTR(MP_QSTR_STATUS_ERR_INTERNAL), MP_ROM_INT(BCP_STATUS_ERR_INTERNAL)},
    {MP_ROM_QSTR(MP_QSTR_MAX_WINDS), MP_ROM_INT(BCP_MAX_WINDS)},
    {MP_ROM_QSTR(MP_QSTR_MAX_DRAG_PTS), MP_ROM_INT(BCP_MAX_DRAG_PTS)},
    {MP_ROM_QSTR(MP_QSTR_MAX_BC_POINTS), MP_ROM_INT(BCP_MAX_BC_POINTS)},
};
static MP_DEFINE_CONST_DICT(bcp_dispatch_module_globals, bcp_dispatch_module_globals_table);

const mp_obj_module_t bcp_dispatch_module = {
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&bcp_dispatch_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR__bcp_dispatch, bcp_dispatch_module);
