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
 * calls straight into the C engine (tiny_bclibc_build_shot_props(),
 * tiny_bclibc_find_zero_angle(), etc.), never through Python objects --
 * a real-time target has no business converting through Python just to
 * call C. Once state is a native struct, winds and the drag curve are
 * independent pointers/arrays (TINY_BCLIBC_Shot's own shape), so there's
 * no byte-offset interleaving to manage regardless of which order
 * LOAD_PROFILE/LOAD_CONDITIONS arrive in.
 *
 * Only IDENT, LOAD_CONFIG and LOAD_PROFILE are implemented so far — see
 * BACKLOG.md Epic 3/8 for the rest of the command table; unimplemented
 * commands raise NotImplementedError (a development-time signal, not a
 * wire status — production dispatch will route every BCP_CMD_* to a
 * real handler before this ships).
 */

#include <math.h>
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

/* From tiny_bclibc_mp.c — same interpolate-against-a-reference-table math
 * Epic 2's MultiBC()/build_multibc() already does, reused here for
 * LOAD_PROFILE's *_MULTIBC drag_type variants instead of duplicated. */
extern real_t tiny_bclibc_mp_interp_bc(const real_t *bc_mach, const real_t *bc_val, int32_t n, real_t mach);
extern void tiny_bclibc_mp_sort_bc_points(real_t *mach, real_t *val, int32_t n);

/* drag_type values (PROTOCOL.md §4.2) — final, not provisional. */
enum
{
    BCP_DRAG_G1 = 0,
    BCP_DRAG_G7 = 1,
    BCP_DRAG_CUSTOM = 2,
    BCP_DRAG_G1_MULTIBC = 3,
    BCP_DRAG_G7_MULTIBC = 4,
};

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

static uint16_t bcp_rdu16(const uint8_t *p, size_t off)
{
    return (uint16_t)((uint32_t)p[off] | ((uint32_t)p[off + 1] << 8));
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
    real_t zero_distance_ft; /* from LOAD_PROFILE -- not a TINY_BCLIBC_Shot field, wire-only, drives the zero re-solve */
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
 * already hit once, hand-transcribing the COBS test vectors).
 *
 * Atmosphere/geometry fields also need real defaults here, not C's
 * zero-init: PROTOCOL.md §4.3 documents that LOAD_CONDITIONS not having
 * arrived yet falls back to "Shot()'s existing Python-side defaults (ICAO
 * standard atmosphere, no wind, zero cant/look angle)" -- but a
 * zero-initialized `pressure_hpa=0` is not "standard atmosphere", it's a
 * vacuum: TINY_BCLIBC_Atmosphere_from_conditions() explicitly special-cases
 * `p_hpa <= 0` to `density_ratio=0`, which makes drag disappear entirely
 * regardless of bc/drag table (caught by a real LOAD_PROFILE test that
 * varied bc across a wide range and got a bit-identical zero angle every
 * time -- not a coincidence of the physics, a missing default). Matches
 * tiny_bclibc.py's Shot() defaults exactly, including NaN lat/az, which
 * TINY_BCLIBC_Coriolis_from_lat_az() treats as its own documented
 * "no Coriolis" sentinel, not a hazard. */
static void bcp_state_ensure_init(void)
{
    if (bcp_state.ready)
    {
        return;
    }
    bcp_state.shot.config = TINY_BCLIBC_Config_default();
    bcp_state.shot.temp_c = REAL_C(15.0);
    bcp_state.shot.pressure_hpa = REAL_C(1013.25);
    bcp_state.shot.altitude_ft = REAL_C(0.0);
    bcp_state.shot.humidity = REAL_C(0.5);
    bcp_state.shot.latitude_deg = (real_t)NAN;
    bcp_state.shot.azimuth_deg = (real_t)NAN;
    bcp_state.ready = true;
}

/* ── Shared zero re-solve ──────────────────────────────────────────────────
 * LOAD_PROFILE/LOAD_CONFIG/LOAD_CONDITIONS all re-trigger this exact same
 * solve (PROTOCOL.md §4.2/§4.2a/§4.3): builds a ShotProps from whatever's
 * currently cached, calls the engine's own find_zero_angle() against the
 * cached zero_distance_ft, and caches the solved angle back into
 * shot.barrel_elevation_rad (so the next INTEGRATE/INTEGRATE_AT picks it up
 * too). Returns TINY_BCLIBC_OK on success (*angle_out holds the solved
 * angle) or a tiny_bclibc error code otherwise -- callers map any non-OK
 * result to ERR_INTERNAL, there's no separate FIND_ZERO_ANGLE response to
 * carry a more specific one. */
static int32_t bcp_resolve_zero(real_t *angle_out)
{
    TINY_BCLIBC_ShotProps props;
    int32_t rc = tiny_bclibc_build_shot_props(&bcp_state.shot, bcp_state.curve_buf, &props);
    if (rc != TINY_BCLIBC_OK)
    {
        return rc;
    }
    real_t angle = REAL_C(0.0);
    rc = tiny_bclibc_find_zero_angle(&props, bcp_state.zero_distance_ft, &angle);
    if (rc != TINY_BCLIBC_OK)
    {
        return rc;
    }
    bcp_state.shot.barrel_elevation_rad = angle;
    *angle_out = angle;
    return TINY_BCLIBC_OK;
}

/* Builds the (status, response_payload) tuple every LOAD_PROFILE/
 * LOAD_CONFIG/LOAD_CONDITIONS handler returns: `barrel_elevation_rad:f32`
 * on success, empty payload otherwise (PROTOCOL.md §4.2/§4.2a/§4.3). */
static mp_obj_t bcp_zero_response(uint8_t status, int ok)
{
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

/* ── LOAD_CONFIG (PROTOCOL.md §4.2a) ──────────────────────────────────────
 * Request: fixed 28 B. Field-by-field parse, not a memcpy: the wire order
 * (step_multiplier..minimum_altitude, max_iterations last) differs from
 * TINY_BCLIBC_Config's own field order (cMaxIterations sits before
 * cGravityConstant/cMinimumAltitude there). No variable-length part, so
 * its "array-count rule" (§4.1) reduces to an exact size match.
 *
 * Response: barrel_elevation_rad -- solver tuning affects the zero-angle
 * solve too, so LOAD_CONFIG re-triggers it exactly like LOAD_PROFILE/
 * LOAD_CONDITIONS, via the shared bcp_resolve_zero(). ERR_NOT_LOADED if no
 * profile is cached yet (nothing to solve a zero for).
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
    real_t angle;
    if (bcp_resolve_zero(&angle) != TINY_BCLIBC_OK)
    {
        status_out[0] = (uint8_t)BCP_STATUS_ERR_INTERNAL;
        return 0;
    }
    status_out[0] = (uint8_t)BCP_STATUS_OK;
    return 1;
}

/* ── LOAD_PROFILE (PROTOCOL.md §4.2) ──────────────────────────────────────
 * Request: 36 B fixed (bc, weight_grain, diameter_inch, length_inch,
 * muzzle_velocity_fps, sight_height_ft, twist_inch, zero_distance_ft,
 * drag_type:u8, rsvd:u8, drag_count:u16) + drag_count x 8 B drag points
 * (shape depends on drag_type, see below). `zero_distance_ft` is wire-only
 * -- not a TINY_BCLIBC_Shot field -- the client supplies a *distance*, not
 * a pre-solved angle, since the elevation needed depends on atmosphere/
 * config too (BACKLOG.md Epic 8's "MultiBC wire exposure" bullet).
 *
 * drag_type is a tagged union over what the trailing points mean and
 * whether `bc` (offset 0) is used:
 *   G1/G7 (0/1):        no points (drag_count must be 0), bc used normally.
 *   CUSTOM (2):         drag_count x {mach:f32, cd:f32}, <= BCP_MAX_DRAG_PTS,
 *                       bc used normally.
 *   G1_MULTIBC/G7_MULTIBC (3/4): drag_count x {mach:f32, bc:f32},
 *                       1..BCP_MAX_BC_POINTS breakpoints -- same
 *                       interpolate-against-the-reference-table math Epic
 *                       2's MultiBC()/build_multibc() already does
 *                       (tiny_bclibc_mp_interp_bc/sort_bc_points, reused
 *                       not duplicated). The resulting curve is always
 *                       exactly the reference table's own length
 *                       (G1_N/G7_N), *not* drag_count -- that's only the
 *                       input breakpoint count. `bc` is ignored (not
 *                       validated, not applied) and forced to 1.0
 *                       internally, matching MultiBC()'s own contract: the
 *                       BC-ratio scaling is already baked into the curve.
 *
 * Response: barrel_elevation_rad, via the shared bcp_resolve_zero() (same
 * as LOAD_CONFIG). A zero-solve failure is ERR_INTERNAL -- there's no
 * separate FIND_ZERO_ANGLE response to carry it (it's not a wire command
 * at all, see Epic 8).
 */
#define BCP_LOAD_PROFILE_FIXED_SIZE 36u

static int bcp_handle_load_profile(const uint8_t *payload, size_t payload_len, uint8_t status_out[1])
{
    if (payload_len < BCP_LOAD_PROFILE_FIXED_SIZE)
    {
        status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_SIZE;
        return 0;
    }
    uint8_t drag_type = payload[32];
    uint16_t drag_count = bcp_rdu16(payload, 34);

    switch (drag_type)
    {
    case BCP_DRAG_G1:
    case BCP_DRAG_G7:
        if (drag_count != 0)
        {
            status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_ARG;
            return 0;
        }
        break;
    case BCP_DRAG_CUSTOM:
        if (drag_count > (uint16_t)BCP_MAX_DRAG_PTS)
        {
            status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_ARG;
            return 0;
        }
        break;
    case BCP_DRAG_G1_MULTIBC:
    case BCP_DRAG_G7_MULTIBC:
        if (drag_count < 1 || drag_count > (uint16_t)BCP_MAX_BC_POINTS)
        {
            status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_ARG;
            return 0;
        }
        break;
    default:
        status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_ARG;
        return 0;
    }

    size_t expected = BCP_LOAD_PROFILE_FIXED_SIZE + (size_t)drag_count * 8u;
    if (payload_len != expected)
    {
        status_out[0] = (uint8_t)BCP_STATUS_ERR_BAD_SIZE;
        return 0;
    }

    real_t wire_bc = (real_t)bcp_rdf32(payload, 0);
    bcp_state.shot.weight_grain = (real_t)bcp_rdf32(payload, 4);
    bcp_state.shot.diameter_inch = (real_t)bcp_rdf32(payload, 8);
    bcp_state.shot.length_inch = (real_t)bcp_rdf32(payload, 12);
    bcp_state.shot.muzzle_velocity_fps = (real_t)bcp_rdf32(payload, 16);
    bcp_state.shot.sight_height_ft = (real_t)bcp_rdf32(payload, 20);
    bcp_state.shot.twist_inch = (real_t)bcp_rdf32(payload, 24);
    bcp_state.zero_distance_ft = (real_t)bcp_rdf32(payload, 28);

    const uint8_t *drag_points = payload + BCP_LOAD_PROFILE_FIXED_SIZE;

    switch (drag_type)
    {
    case BCP_DRAG_G1:
        bcp_state.shot.bc = wire_bc;
        bcp_state.shot.mach_data = g1_mach;
        bcp_state.shot.cd_data = g1_cd;
        bcp_state.shot.drag_table_size = G1_N;
        break;
    case BCP_DRAG_G7:
        bcp_state.shot.bc = wire_bc;
        bcp_state.shot.mach_data = g7_mach;
        bcp_state.shot.cd_data = g7_cd;
        bcp_state.shot.drag_table_size = G7_N;
        break;
    case BCP_DRAG_CUSTOM:
        bcp_state.shot.bc = wire_bc;
        for (uint16_t i = 0; i < drag_count; i++)
        {
            size_t off = (size_t)i * 8u;
            bcp_state.drag_mach[i] = (real_t)bcp_rdf32(drag_points, off);
            bcp_state.drag_cd[i] = (real_t)bcp_rdf32(drag_points, off + 4u);
        }
        bcp_state.shot.mach_data = bcp_state.drag_mach;
        bcp_state.shot.cd_data = bcp_state.drag_cd;
        bcp_state.shot.drag_table_size = (int32_t)drag_count;
        break;
    case BCP_DRAG_G1_MULTIBC:
    case BCP_DRAG_G7_MULTIBC:
    {
        real_t bc_mach[BCP_MAX_BC_POINTS];
        real_t bc_val[BCP_MAX_BC_POINTS];
        for (uint16_t i = 0; i < drag_count; i++)
        {
            size_t off = (size_t)i * 8u;
            bc_mach[i] = (real_t)bcp_rdf32(drag_points, off);
            bc_val[i] = (real_t)bcp_rdf32(drag_points, off + 4u);
        }
        tiny_bclibc_mp_sort_bc_points(bc_mach, bc_val, (int32_t)drag_count);

        int is_g1 = (drag_type == BCP_DRAG_G1_MULTIBC);
        const real_t *ref_mach = is_g1 ? g1_mach : g7_mach;
        const real_t *ref_cd = is_g1 ? g1_cd : g7_cd;
        int32_t ref_n = is_g1 ? G1_N : G7_N;
        for (int32_t i = 0; i < ref_n; i++)
        {
            real_t bc_at = tiny_bclibc_mp_interp_bc(bc_mach, bc_val, (int32_t)drag_count, ref_mach[i]);
            bcp_state.drag_mach[i] = ref_mach[i];
            bcp_state.drag_cd[i] = ref_cd[i] / bc_at;
        }
        /* bc ignored -- see the doc comment above. */
        bcp_state.shot.bc = REAL_C(1.0);
        bcp_state.shot.mach_data = bcp_state.drag_mach;
        bcp_state.shot.cd_data = bcp_state.drag_cd;
        bcp_state.shot.drag_table_size = ref_n;
        break;
    }
    }

    bcp_state.has_profile = true;

    real_t angle;
    if (bcp_resolve_zero(&angle) != TINY_BCLIBC_OK)
    {
        status_out[0] = (uint8_t)BCP_STATUS_ERR_INTERNAL;
        return 0;
    }
    status_out[0] = (uint8_t)BCP_STATUS_OK;
    return 1;
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
        return bcp_zero_response(status, ok);
    }
    case BCP_CMD_LOAD_PROFILE:
    {
        mp_buffer_info_t pbi;
        mp_get_buffer_raise(payload_obj, &pbi, MP_BUFFER_READ);
        uint8_t status;
        int ok = bcp_handle_load_profile((const uint8_t *)pbi.buf, pbi.len, &status);
        return bcp_zero_response(status, ok);
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
