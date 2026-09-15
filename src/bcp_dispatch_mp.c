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
 * Only IDENT is implemented so far — see BACKLOG.md Epic 3/8 for the rest
 * of the command table; unimplemented commands raise NotImplementedError
 * (a development-time signal, not a wire status — production dispatch
 * will route every BCP_CMD_* to a real handler before this ships).
 */

#include <stdio.h>
#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "py/misc.h"

#include "tiny_bclibc.h"
#include "generated/bclibc_mp/version.h"

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
