/* bcp_shot_layout.h — shared byte offsets for the internal Shot buffer.
 *
 * Single source of truth for this layout, included by both
 * tiny_bclibc_mp.c (Shot() constructor binding) and bcp_dispatch_mp.c (BCP
 * LOAD_* handlers, which write directly into the same layout so the exact
 * same buffer can later be handed to tiny_bclibc_mp.c's own integrate()/
 * find_zero_angle()/etc. unchanged). Must match tiny_bclibc.py's
 * _SHOT_DESC/_SHOT_PROPS_DESC/_CFG_DESC exactly — this is the one place
 * that mapping is written down in C, instead of two files each hand-typing
 * the same magic numbers with no way to notice if they drift apart.
 *
 * Only the offsets actually needed by C code so far are listed; add more
 * as more BCP commands land (see BACKLOG.md Epic 8).
 */
#ifndef BCP_SHOT_LAYOUT_H
#define BCP_SHOT_LAYOUT_H

#define BCP_SHOT_HDR_SIZE 100u /* fixed part: props(68) + cfg(28) + drag_type/wind_count/drag_count(4) */

/* ── props (offset 0, 68 B, 17 x float32) ────────────────────────────────── */
#define BCP_SHOT_OFF_BC 0u
#define BCP_SHOT_OFF_WEIGHT_GRAIN 4u
#define BCP_SHOT_OFF_DIAMETER_INCH 8u
#define BCP_SHOT_OFF_LENGTH_INCH 12u
#define BCP_SHOT_OFF_MUZZLE_VELOCITY_FPS 16u
#define BCP_SHOT_OFF_SIGHT_HEIGHT_FT 20u
#define BCP_SHOT_OFF_TWIST_INCH 24u
#define BCP_SHOT_OFF_TEMP_C 28u
#define BCP_SHOT_OFF_PRESSURE_HPA 32u
#define BCP_SHOT_OFF_ALTITUDE_FT 36u
#define BCP_SHOT_OFF_HUMIDITY 40u
#define BCP_SHOT_OFF_LOOK_ANGLE_RAD 44u
#define BCP_SHOT_OFF_BARREL_ELEVATION_RAD 48u
#define BCP_SHOT_OFF_BARREL_AZIMUTH_RAD 52u
#define BCP_SHOT_OFF_CANT_ANGLE_RAD 56u
#define BCP_SHOT_OFF_LATITUDE_DEG 60u
#define BCP_SHOT_OFF_AZIMUTH_DEG 64u

/* ── cfg (offset 68, 28 B: 6 x float32 + 1 x int32) ──────────────────────── */
#define BCP_SHOT_OFF_CFG 68u
#define BCP_SHOT_OFF_STEP_MULTIPLIER 68u
#define BCP_SHOT_OFF_ZERO_FINDING_ACCURACY 72u
#define BCP_SHOT_OFF_MINIMUM_VELOCITY 76u
#define BCP_SHOT_OFF_MAXIMUM_DROP 80u
#define BCP_SHOT_OFF_GRAVITY_CONSTANT 84u
#define BCP_SHOT_OFF_MINIMUM_ALTITUDE 88u
#define BCP_SHOT_OFF_CFG_MAXITER 92u /* int32_t — same field as _CFG_DESC's own max_iterations */

/* ── header tail (offset 96-99) ──────────────────────────────────────────── */
#define BCP_SHOT_OFF_DRAG_TYPE 96u /* uint8_t: 0=G1, 1=G7, 2=CUSTOM, 3=G1_MULTIBC, 4=G7_MULTIBC */
#define BCP_SHOT_OFF_WIND_CNT 97u  /* uint8_t */
#define BCP_SHOT_OFF_DRAG_CNT 98u  /* uint16_t */
#define BCP_SHOT_OFF_WINDS_START 100u

#endif /* BCP_SHOT_LAYOUT_H */
