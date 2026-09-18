/* ════════════════════════════════════════════════════════════════════════
 * UNWIRED REFERENCE / PROTOTYPE -- NOT INTEGRATED INTO ANY BUILD.
 *
 * This is a reconstruction (from the investigating session's transcript) of a
 * Cash-Karp embedded adaptive RK45 integrator prototyped against a scratch,
 * NEVER-COMMITTED copy of the real `ballistics-lab/bclibc` submodule checkout
 * vendored at py-ballisticcalc's
 * `py_ballisticcalc.exts/py_ballisticcalc_exts/external/bclibc`. That checkout
 * was reverted to pristine (`git checkout --`) before the investigation
 * finished and has NOT been touched since -- this file exists purely so the
 * work isn't lost, for whoever picks up the follow-on effort described below.
 *
 * It is NOT wired into `micropython-bclibc`'s build (no `usermod/manifest.py`,
 * no `micropython.mk`, no `natmod` changes) and was never meant to be -- it
 * targets `tiny_bclibc/include/tiny_bclibc/engine.h`, a file that lives in the
 * separate `ballistics-lab/bclibc` repo, out of this repo's scope.
 *
 * ── How to actually use this, if you pick the work back up ─────────────────
 * 1. Get a local (never-pushed) checkout of `ballistics-lab/bclibc`'s
 *    `tiny_bclibc` -- e.g. the submodule at
 *    `py-ballisticcalc/py_ballisticcalc.exts/py_ballisticcalc_exts/external/bclibc`
 *    (that repo's `examples/tiny_bclibc/CMakeLists.txt` already builds real
 *    single- and double-precision `.so`s from it and can run py-ballisticcalc's
 *    real 375-test pytest suite and `scripts/benchmark.py` against them --
 *    that's how every number below was produced).
 * 2. Paste everything from "BEGIN SPLICE" to "END SPLICE" below into
 *    `tiny_bclibc/include/tiny_bclibc/engine.h`, right after the closing brace
 *    of `tiny_bclibc__run_rk4()` and before the
 *    "tiny_bclibc_build_shot_props" section comment banner.
 * 3. Replace the 5 existing call sites of `tiny_bclibc__run_rk4(` in that same
 *    file with `TINY_BCLIBC_RUN_ENGINE(` (same arguments) -- they are inside
 *    `tiny_bclibc_integrate`, `tiny_bclibc_integrate_stream`,
 *    `tiny_bclibc_integrate_raw`, `tiny_bclibc_integrate_at`'s internals, and
 *    `tiny_bclibc__range_for_angle`. `TINY_BCLIBC_RUN_ENGINE` is a compile-time
 *    macro that resolves to `tiny_bclibc__run_cashkarp` when
 *    `TINY_BCLIBC_USE_CASHKARP` is defined at compile time, else
 *    `tiny_bclibc__run_rk4` unchanged -- so the diff at every call site is
 *    zero-risk and the stock RK4 path is untouched unless you opt in.
 * 4. Build with `-DTINY_BCLIBC_USE_CASHKARP -DTINY_BCLIBC_CASHKARP_PERSTAGE_ATMO
 *    -DTINY_BCLIBC_CASHKARP_RTOL=1e-6` (single precision: use `1e-6f`) -- see
 *    README.md in this directory for why `PERSTAGE_ATMO` is the variant you
 *    want (the other two are dead ends, kept only for the comparison).
 *
 * See README.md in this directory for the full accuracy/speed numbers, the
 * dead ends, and — most importantly — the specific unresolved blocker
 * (event-crossing interpolation on sparse adaptive samples) that must be
 * fixed before this could replace `tiny_bclibc__run_rk4` in production.
 * ════════════════════════════════════════════════════════════════════════ */

/* ─────────────────────────────── BEGIN SPLICE ───────────────────────────── */

    /* ════════════════════════════════════════════════════════════════════
     *  EXPERIMENTAL: Cash-Karp embedded RK45 (prototype, not for production)
     *
     *  Local, throwaway A/B toggle -- never intended to land upstream in this
     *  form. Reuses tiny_bclibc__calc_dvdt and TINY_BCLIBC_ShotProps_drag_by_mach
     *  exactly like tiny_bclibc__run_rk4.
     *
     *  ── km/atmosphere evaluation strategy (3 variants below, pick ONE) ──
     *  tiny_bclibc__run_rk4 evaluates km = density_ratio * drag_by_mach(mach)
     *  ONCE per fixed 1.25ms step and reuses it across all 4 RK4 substages --
     *  a real approximation already baked into the existing engine, cheap
     *  because the step is always tiny. The three #ifdef'd `tiny_bclibc__ck_f`
     *  variants below explore how much of that reuse survives when the step
     *  itself is no longer tiny (Cash-Karp's whole point is to grow it 10-60x
     *  during smooth supersonic cruise):
     *
     *    (a) default (neither macro defined) -- km frozen at the step-start
     *        value and reused across all 6 stages, i.e. run_rk4's own trick
     *        extended from 4 stages to 6. MEASURED: BROKEN. 26-36/375
     *        py-ballisticcalc test failures, and this DOES NOT IMPROVE as
     *        rtol is tightened from 1e-4 to 1e-7 (1000x range) -- even in
     *        double precision, where stock RK4 has 0 failures. Root cause:
     *        the embedded 4th/5th-order error estimate only measures
     *        discretization error of the FROZEN-km sub-problem; it is blind
     *        to the model error from km itself going stale as the step
     *        grows. Tightening tolerance makes the wrong sub-problem's
     *        solution more precise -- it never touches the actual error
     *        source. Kept here only so the comparison is reproducible; do
     *        not use this variant.
     *
     *    (b) TINY_BCLIBC_CASHKARP_PERSTAGE_DRAG -- re-evaluate the
     *        mach-dependent drag COEFFICIENT at each of the 6 stages from
     *        that stage's own |v_rel|, but still reuse the step-start
     *        density_ratio/speed-of-sound (atmosphere barely changes over
     *        one step in altitude terms; this isolates whether it's
     *        specifically the drag curve, not the atmosphere, going stale).
     *        MEASURED: 26-36 -> 8-10/375 failures (double precision).  Big
     *        improvement, not sufficient on its own.
     *
     *    (c) TINY_BCLIBC_CASHKARP_PERSTAGE_ATMO -- the real fix: re-evaluate
     *        BOTH the drag coefficient AND the atmosphere sample
     *        (density_ratio, speed of sound) at each stage's own
     *        intermediate ALTITUDE (requires tracking intermediate `pos`
     *        through all 6 stages via the same Butcher coefficients used for
     *        v_rel, not just v_rel alone). MEASURED: down to a hard floor of
     *        5/375 failures at rtol=1e-8 in double precision (0 in stock
     *        RK4). This matches -- independently rediscovered, then
     *        confirmed against -- the `o-murphy/py-ballisticcalc` branch
     *        `rk45-dev`'s RKF45 prototype for the *full C++* bclibc engine
     *        (`py_ballisticcalc.exts/py_ballisticcalc_exts/src/rk45.cpp`),
     *        which also recomputes drag_by_mach() AND the atmosphere fresh
     *        at every one of its 6 stages. Two independent implementations
     *        landing on the same design is strong evidence this is the
     *        *required* cost of an embedded RK method here, not a matter of
     *        preference -- classical RK4's per-step memoization simply does
     *        not survive adaptive stepping. USE THIS VARIANT.
     *
     *  Even variant (c)'s 5-failure floor does NOT close with tighter
     *  tolerance (tried down to rtol=1e-8) -- see README.md: the remaining
     *  failures are a *different*, structural problem (event-crossing
     *  interpolation across sparse adaptive samples), not an integration-
     *  accuracy problem, and are the actual blocker to shipping this.
     * ════════════════════════════════════════════════════════════════════ */

#ifndef TINY_BCLIBC_CASHKARP_RTOL
#define TINY_BCLIBC_CASHKARP_RTOL REAL_C(1e-4)
#endif
#define TINY_BCLIBC_CASHKARP_ATOL_V REAL_C(1e-3)  /* fps floor */
#define TINY_BCLIBC_CASHKARP_ATOL_P REAL_C(1e-4)  /* ft floor */
#define TINY_BCLIBC_CASHKARP_SAFETY REAL_C(0.9)
#define TINY_BCLIBC_CASHKARP_MAX_RETRY 24
#define TINY_BCLIBC_CASHKARP_MIN_DT_DIV REAL_C(64.0) /* min dt = calc_step / this */
#define TINY_BCLIBC_CASHKARP_MAX_DT_MUL REAL_C(64.0) /* max dt = calc_step * this */

    /* Step-count telemetry -- thread-local so it composes with tiny_bclibc__s_error.
     * Reset at the start of every tiny_bclibc__run_cashkarp call, read back by the
     * host via tiny_bclibc_cashkarp_get_stats() after the integrate call returns.
     * (Used by benchmark_cashkarp.py in this directory to compare total step
     * counts against the fixed-step RK4 baseline -- the fairest apples-to-
     * apples comparison against a fixed cStepMultiplier.) */
    static TINY_BCLIBC_THREAD_LOCAL int32_t tiny_bclibc__g_ck_accepted = 0;
    static TINY_BCLIBC_THREAD_LOCAL int32_t tiny_bclibc__g_ck_rejected = 0;

    TINY_BCLIBC_FUNC void tiny_bclibc_cashkarp_get_stats(int32_t *out_accepted, int32_t *out_rejected)
    {
        if (out_accepted)
            *out_accepted = tiny_bclibc__g_ck_accepted;
        if (out_rejected)
            *out_rejected = tiny_bclibc__g_ck_rejected;
    }

    typedef struct tiny_bclibc__CkDeriv
    {
        TINY_BCLIBC_V3dT dvr; /* d(v_rel)/dt */
        TINY_BCLIBC_V3dT dp;  /* d(pos)/dt   */
    } tiny_bclibc__CkDeriv;

#if defined(TINY_BCLIBC_CASHKARP_PERSTAGE_ATMO)
    /* Full per-stage refresh (matches the reference RKF45 prototype at
     * py_ballisticcalc.exts/py_ballisticcalc_exts/src/rk45.cpp on the
     * bclibc-dev rk45-dev branch): both the drag coefficient AND the
     * atmosphere sample (density_ratio, speed of sound) are re-evaluated at
     * each stage's own intermediate altitude, not just its own speed. */
    static inline tiny_bclibc__CkDeriv tiny_bclibc__ck_f(
        TINY_BCLIBC_V3dT vr, TINY_BCLIBC_V3dT wind,
        TINY_BCLIBC_V3dT gpc, real_t km,
        const TINY_BCLIBC_ShotProps *props, real_t density_ratio, real_t inv_mach,
        real_t alt_y)
    {
        (void)km;
        (void)density_ratio;
        (void)inv_mach;
        tiny_bclibc__CkDeriv d;
        real_t local_density_ratio, local_mach_fps;
        TINY_BCLIBC_Atmosphere_update_density_mach(&props->atmo, props->alt0 + alt_y,
                                                    &local_density_ratio, &local_mach_fps);
        real_t local_inv_mach = (local_mach_fps != REAL_C(0.0)) ? (REAL_C(1.0) / local_mach_fps) : REAL_C(1.0);
        real_t sp = TINY_BCLIBC_SQRT(vr.x * vr.x + vr.y * vr.y + vr.z * vr.z);
        real_t local_mach = sp * local_inv_mach;
        real_t local_km = local_density_ratio * TINY_BCLIBC_ShotProps_drag_by_mach(props, local_mach);
        tiny_bclibc__calc_dvdt(vr, gpc, local_km, sp, &d.dvr);
        d.dp = TINY_BCLIBC_V3dT_make(vr.x + wind.x, vr.y + wind.y, vr.z + wind.z);
        return d;
    }
#define TINY_BCLIBC_CK_F(vr_, pos_) tiny_bclibc__ck_f((vr_), wind, gpc, km, props, density_ratio, inv_mach, (pos_).y)
#elif defined(TINY_BCLIBC_CASHKARP_PERSTAGE_DRAG)
    static inline tiny_bclibc__CkDeriv tiny_bclibc__ck_f(
        TINY_BCLIBC_V3dT vr, TINY_BCLIBC_V3dT wind,
        TINY_BCLIBC_V3dT gpc, real_t km,
        const TINY_BCLIBC_ShotProps *props, real_t density_ratio, real_t inv_mach)
    {
        (void)km;
        tiny_bclibc__CkDeriv d;
        real_t sp = TINY_BCLIBC_SQRT(vr.x * vr.x + vr.y * vr.y + vr.z * vr.z);
        real_t local_mach = sp * inv_mach;
        real_t local_km = density_ratio * TINY_BCLIBC_ShotProps_drag_by_mach(props, local_mach);
        tiny_bclibc__calc_dvdt(vr, gpc, local_km, sp, &d.dvr);
        d.dp = TINY_BCLIBC_V3dT_make(vr.x + wind.x, vr.y + wind.y, vr.z + wind.z);
        return d;
    }
#define TINY_BCLIBC_CK_F(vr_, pos_) tiny_bclibc__ck_f((vr_), wind, gpc, km, props, density_ratio, inv_mach)
#else
    static inline tiny_bclibc__CkDeriv tiny_bclibc__ck_f(
        TINY_BCLIBC_V3dT vr, TINY_BCLIBC_V3dT wind,
        TINY_BCLIBC_V3dT gpc, real_t km)
    {
        tiny_bclibc__CkDeriv d;
        real_t sp = TINY_BCLIBC_SQRT(vr.x * vr.x + vr.y * vr.y + vr.z * vr.z);
        tiny_bclibc__calc_dvdt(vr, gpc, km, sp, &d.dvr);
        d.dp = TINY_BCLIBC_V3dT_make(vr.x + wind.x, vr.y + wind.y, vr.z + wind.z);
        return d;
    }
#define TINY_BCLIBC_CK_F(vr_, pos_) tiny_bclibc__ck_f((vr_), wind, gpc, km)
#endif

    /* ── Main Cash-Karp adaptive loop ────────────────────────────────── */
    TINY_BCLIBC_INTERNAL int32_t tiny_bclibc__run_cashkarp(
        const TINY_BCLIBC_ShotProps *props,
        const TINY_BCLIBC_TrajectoryRequest *req,
        tiny_bclibc__OnStep on_step,
        void *ctx,
        int32_t *out_reason)
    {
        const real_t base_dt = props->calc_step;
        if (base_dt <= REAL_C(0.0))
        {
            tiny_bclibc__set_error("calc_step must be > 0");
            *out_reason = TINY_BCLIBC_TERM_NO_TERMINATE;
            return TINY_BCLIBC_ERR_INVALID_ARG;
        }
        const real_t min_dt = base_dt / TINY_BCLIBC_CASHKARP_MIN_DT_DIV;
        const real_t max_dt = base_dt * TINY_BCLIBC_CASHKARP_MAX_DT_MUL;
        real_t dt = base_dt;

        tiny_bclibc__g_ck_accepted = 0;
        tiny_bclibc__g_ck_rejected = 0;

        real_t range_limit = req ? req->range_limit_ft : TINY_BCLIBC_MAX_INTEGRATION_RANGE;

        tiny_bclibc__StopCtrl sc;
        tiny_bclibc__stop_ctrl_init(&sc, props, range_limit,
                                    props->cfg.cMinimumVelocity,
                                    props->cfg.cMaximumDrop, props->cfg.cMinimumAltitude, out_reason);

        TINY_BCLIBC_WindSock ws = props->wind_sock;
        TINY_BCLIBC_V3dT gravity = TINY_BCLIBC_V3dT_make(REAL_C(0.0), props->cfg.cGravityConstant, REAL_C(0.0));
        TINY_BCLIBC_V3dT wind = ws.last_vector;

        real_t muzzle = props->muzzle_velocity;
        real_t cos_el = TINY_BCLIBC_COS(props->barrel_elevation);
        TINY_BCLIBC_V3dT dir = TINY_BCLIBC_V3dT_make(
            cos_el * TINY_BCLIBC_COS(props->barrel_azimuth),
            TINY_BCLIBC_SIN(props->barrel_elevation),
            cos_el * TINY_BCLIBC_SIN(props->barrel_azimuth));

        TINY_BCLIBC_V3dT pos = TINY_BCLIBC_V3dT_make(
            REAL_C(0.0),
            -props->cant_cosine * props->sight_height,
            -props->cant_sine * props->sight_height);
        TINY_BCLIBC_V3dT vel = TINY_BCLIBC_V3dT_make(dir.x * muzzle, dir.y * muzzle, dir.z * muzzle);
        TINY_BCLIBC_V3dT vr = TINY_BCLIBC_V3dT_make(vel.x - wind.x, vel.y - wind.y, vel.z - wind.z);

        real_t time = REAL_C(0.0);
        *out_reason = TINY_BCLIBC_TERM_NO_TERMINATE;

        while (*out_reason == TINY_BCLIBC_TERM_NO_TERMINATE)
        {
            if (pos.x >= ws.next_range)
                wind = TINY_BCLIBC_WindSock_vector_for_range(&ws, pos.x);

            real_t density_ratio, mach_fps;
            TINY_BCLIBC_Atmosphere_update_density_mach(&props->atmo,
                                                       props->alt0 + pos.y, &density_ratio, &mach_fps);

            real_t inv_mach = (mach_fps != REAL_C(0.0)) ? (REAL_C(1.0) / mach_fps) : REAL_C(1.0);
            real_t rel_speed = TINY_BCLIBC_SQRT(vr.x * vr.x + vr.y * vr.y + vr.z * vr.z);
            real_t cur_mach = rel_speed * inv_mach;

            TINY_BCLIBC_BaseTrajData pt;
            pt.time = time;
            pt.px = pos.x;
            pt.py = pos.y;
            pt.pz = pos.z;
            pt.vx = vr.x + wind.x;
            pt.vy = vr.y + wind.y;
            pt.vz = vr.z + wind.z;
            pt.mach = cur_mach;

            tiny_bclibc__stop_ctrl_check(&sc, &pt);
            if (*out_reason != TINY_BCLIBC_TERM_NO_TERMINATE)
                break;

            int32_t cb = on_step(&pt, ctx);
            if (cb != 0)
            {
                *out_reason = TINY_BCLIBC_TERM_HANDLER_STOP;
                break;
            }

            /* km + gravity/coriolis: frozen for this attempted step (and any of its
             * shrink-and-retry attempts below) in the default/PERSTAGE_DRAG variants;
             * PERSTAGE_ATMO ignores km/density_ratio/inv_mach here and recomputes
             * everything fresh per-stage instead -- see TINY_BCLIBC_CK_F above. */
            real_t km = density_ratio * TINY_BCLIBC_ShotProps_drag_by_mach(props, cur_mach);
            TINY_BCLIBC_V3dT gpc = gravity;
            if (!props->coriolis.flat_fire_only)
            {
                TINY_BCLIBC_V3dT ca;
                TINY_BCLIBC_Coriolis_acceleration_local(&props->coriolis, TINY_BCLIBC_V3dT_make(pt.vx, pt.vy, pt.vz), &ca);
                gpc.x += ca.x;
                gpc.y += ca.y;
                gpc.z += ca.z;
            }

            TINY_BCLIBC_V3dT vr5, pos5;
            real_t err_norm = REAL_C(0.0);
            real_t dt_used = dt;
            int32_t attempt;
            for (attempt = 0; attempt < TINY_BCLIBC_CASHKARP_MAX_RETRY; attempt++)
            {
                dt_used = dt;
                tiny_bclibc__CkDeriv k1 = TINY_BCLIBC_CK_F(vr, pos);

                TINY_BCLIBC_V3dT vr2 = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * REAL_C(0.2) * k1.dvr.x,
                    vr.y + dt * REAL_C(0.2) * k1.dvr.y,
                    vr.z + dt * REAL_C(0.2) * k1.dvr.z);
                TINY_BCLIBC_V3dT pos2 = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * REAL_C(0.2) * k1.dp.x,
                    pos.y + dt * REAL_C(0.2) * k1.dp.y,
                    pos.z + dt * REAL_C(0.2) * k1.dp.z);
                tiny_bclibc__CkDeriv k2 = TINY_BCLIBC_CK_F(vr2, pos2);

                TINY_BCLIBC_V3dT vr3 = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dvr.x + REAL_C(9.0) / REAL_C(40.0) * k2.dvr.x),
                    vr.y + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dvr.y + REAL_C(9.0) / REAL_C(40.0) * k2.dvr.y),
                    vr.z + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dvr.z + REAL_C(9.0) / REAL_C(40.0) * k2.dvr.z));
                TINY_BCLIBC_V3dT pos3 = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dp.x + REAL_C(9.0) / REAL_C(40.0) * k2.dp.x),
                    pos.y + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dp.y + REAL_C(9.0) / REAL_C(40.0) * k2.dp.y),
                    pos.z + dt * (REAL_C(3.0) / REAL_C(40.0) * k1.dp.z + REAL_C(9.0) / REAL_C(40.0) * k2.dp.z));
                tiny_bclibc__CkDeriv k3 = TINY_BCLIBC_CK_F(vr3, pos3);

                TINY_BCLIBC_V3dT vr4 = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * (REAL_C(0.3) * k1.dvr.x - REAL_C(0.9) * k2.dvr.x + REAL_C(1.2) * k3.dvr.x),
                    vr.y + dt * (REAL_C(0.3) * k1.dvr.y - REAL_C(0.9) * k2.dvr.y + REAL_C(1.2) * k3.dvr.y),
                    vr.z + dt * (REAL_C(0.3) * k1.dvr.z - REAL_C(0.9) * k2.dvr.z + REAL_C(1.2) * k3.dvr.z));
                TINY_BCLIBC_V3dT pos4 = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * (REAL_C(0.3) * k1.dp.x - REAL_C(0.9) * k2.dp.x + REAL_C(1.2) * k3.dp.x),
                    pos.y + dt * (REAL_C(0.3) * k1.dp.y - REAL_C(0.9) * k2.dp.y + REAL_C(1.2) * k3.dp.y),
                    pos.z + dt * (REAL_C(0.3) * k1.dp.z - REAL_C(0.9) * k2.dp.z + REAL_C(1.2) * k3.dp.z));
                tiny_bclibc__CkDeriv k4 = TINY_BCLIBC_CK_F(vr4, pos4);

                TINY_BCLIBC_V3dT vr5s = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dvr.x + REAL_C(2.5) * k2.dvr.x - REAL_C(70.0) / REAL_C(27.0) * k3.dvr.x + REAL_C(35.0) / REAL_C(27.0) * k4.dvr.x),
                    vr.y + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dvr.y + REAL_C(2.5) * k2.dvr.y - REAL_C(70.0) / REAL_C(27.0) * k3.dvr.y + REAL_C(35.0) / REAL_C(27.0) * k4.dvr.y),
                    vr.z + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dvr.z + REAL_C(2.5) * k2.dvr.z - REAL_C(70.0) / REAL_C(27.0) * k3.dvr.z + REAL_C(35.0) / REAL_C(27.0) * k4.dvr.z));
                TINY_BCLIBC_V3dT pos5s = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dp.x + REAL_C(2.5) * k2.dp.x - REAL_C(70.0) / REAL_C(27.0) * k3.dp.x + REAL_C(35.0) / REAL_C(27.0) * k4.dp.x),
                    pos.y + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dp.y + REAL_C(2.5) * k2.dp.y - REAL_C(70.0) / REAL_C(27.0) * k3.dp.y + REAL_C(35.0) / REAL_C(27.0) * k4.dp.y),
                    pos.z + dt * (REAL_C(-11.0) / REAL_C(54.0) * k1.dp.z + REAL_C(2.5) * k2.dp.z - REAL_C(70.0) / REAL_C(27.0) * k3.dp.z + REAL_C(35.0) / REAL_C(27.0) * k4.dp.z));
                tiny_bclibc__CkDeriv k5 = TINY_BCLIBC_CK_F(vr5s, pos5s);

                TINY_BCLIBC_V3dT vr6 = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dvr.x + REAL_C(175.0) / REAL_C(512.0) * k2.dvr.x + REAL_C(575.0) / REAL_C(13824.0) * k3.dvr.x + REAL_C(44275.0) / REAL_C(110592.0) * k4.dvr.x + REAL_C(253.0) / REAL_C(4096.0) * k5.dvr.x),
                    vr.y + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dvr.y + REAL_C(175.0) / REAL_C(512.0) * k2.dvr.y + REAL_C(575.0) / REAL_C(13824.0) * k3.dvr.y + REAL_C(44275.0) / REAL_C(110592.0) * k4.dvr.y + REAL_C(253.0) / REAL_C(4096.0) * k5.dvr.y),
                    vr.z + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dvr.z + REAL_C(175.0) / REAL_C(512.0) * k2.dvr.z + REAL_C(575.0) / REAL_C(13824.0) * k3.dvr.z + REAL_C(44275.0) / REAL_C(110592.0) * k4.dvr.z + REAL_C(253.0) / REAL_C(4096.0) * k5.dvr.z));
                TINY_BCLIBC_V3dT pos6 = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dp.x + REAL_C(175.0) / REAL_C(512.0) * k2.dp.x + REAL_C(575.0) / REAL_C(13824.0) * k3.dp.x + REAL_C(44275.0) / REAL_C(110592.0) * k4.dp.x + REAL_C(253.0) / REAL_C(4096.0) * k5.dp.x),
                    pos.y + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dp.y + REAL_C(175.0) / REAL_C(512.0) * k2.dp.y + REAL_C(575.0) / REAL_C(13824.0) * k3.dp.y + REAL_C(44275.0) / REAL_C(110592.0) * k4.dp.y + REAL_C(253.0) / REAL_C(4096.0) * k5.dp.y),
                    pos.z + dt * (REAL_C(1631.0) / REAL_C(55296.0) * k1.dp.z + REAL_C(175.0) / REAL_C(512.0) * k2.dp.z + REAL_C(575.0) / REAL_C(13824.0) * k3.dp.z + REAL_C(44275.0) / REAL_C(110592.0) * k4.dp.z + REAL_C(253.0) / REAL_C(4096.0) * k5.dp.z));
                tiny_bclibc__CkDeriv k6 = TINY_BCLIBC_CK_F(vr6, pos6);

                /* 5th-order solution (b1=37/378, b3=250/621, b4=125/594, b6=512/1771) --
                 * standard Numerical Recipes `rkck` Cash-Karp tableau. */
                const real_t b1 = REAL_C(37.0) / REAL_C(378.0), b3 = REAL_C(250.0) / REAL_C(621.0),
                             b4 = REAL_C(125.0) / REAL_C(594.0), b6 = REAL_C(512.0) / REAL_C(1771.0);
                /* error coefficients (b_i - b_i*, 4th-order embedded solution) */
                const real_t d1 = b1 - REAL_C(2825.0) / REAL_C(27648.0);
                const real_t d3 = b3 - REAL_C(18575.0) / REAL_C(48384.0);
                const real_t d4 = b4 - REAL_C(13525.0) / REAL_C(55296.0);
                const real_t d5 = REAL_C(0.0) - REAL_C(277.0) / REAL_C(14336.0);
                const real_t d6 = b6 - REAL_C(0.25);

                TINY_BCLIBC_V3dT vr_out = TINY_BCLIBC_V3dT_make(
                    vr.x + dt * (b1 * k1.dvr.x + b3 * k3.dvr.x + b4 * k4.dvr.x + b6 * k6.dvr.x),
                    vr.y + dt * (b1 * k1.dvr.y + b3 * k3.dvr.y + b4 * k4.dvr.y + b6 * k6.dvr.y),
                    vr.z + dt * (b1 * k1.dvr.z + b3 * k3.dvr.z + b4 * k4.dvr.z + b6 * k6.dvr.z));
                TINY_BCLIBC_V3dT pos_out = TINY_BCLIBC_V3dT_make(
                    pos.x + dt * (b1 * k1.dp.x + b3 * k3.dp.x + b4 * k4.dp.x + b6 * k6.dp.x),
                    pos.y + dt * (b1 * k1.dp.y + b3 * k3.dp.y + b4 * k4.dp.y + b6 * k6.dp.y),
                    pos.z + dt * (b1 * k1.dp.z + b3 * k3.dp.z + b4 * k4.dp.z + b6 * k6.dp.z));

                TINY_BCLIBC_V3dT err_v = TINY_BCLIBC_V3dT_make(
                    dt * (d1 * k1.dvr.x + d3 * k3.dvr.x + d4 * k4.dvr.x + d5 * k5.dvr.x + d6 * k6.dvr.x),
                    dt * (d1 * k1.dvr.y + d3 * k3.dvr.y + d4 * k4.dvr.y + d5 * k5.dvr.y + d6 * k6.dvr.y),
                    dt * (d1 * k1.dvr.z + d3 * k3.dvr.z + d4 * k4.dvr.z + d5 * k5.dvr.z + d6 * k6.dvr.z));
                TINY_BCLIBC_V3dT err_p = TINY_BCLIBC_V3dT_make(
                    dt * (d1 * k1.dp.x + d3 * k3.dp.x + d4 * k4.dp.x + d5 * k5.dp.x + d6 * k6.dp.x),
                    dt * (d1 * k1.dp.y + d3 * k3.dp.y + d4 * k4.dp.y + d5 * k5.dp.y + d6 * k6.dp.y),
                    dt * (d1 * k1.dp.z + d3 * k3.dp.z + d4 * k4.dp.z + d5 * k5.dp.z + d6 * k6.dp.z));

                real_t err_v_mag = TINY_BCLIBC_SQRT(err_v.x * err_v.x + err_v.y * err_v.y + err_v.z * err_v.z);
                real_t err_p_mag = TINY_BCLIBC_SQRT(err_p.x * err_p.x + err_p.y * err_p.y + err_p.z * err_p.z);
                real_t v_mag = TINY_BCLIBC_SQRT(vr_out.x * vr_out.x + vr_out.y * vr_out.y + vr_out.z * vr_out.z);
                real_t p_mag = TINY_BCLIBC_SQRT(pos_out.x * pos_out.x + pos_out.y * pos_out.y + pos_out.z * pos_out.z);

                real_t scale_v = TINY_BCLIBC_CASHKARP_ATOL_V + TINY_BCLIBC_CASHKARP_RTOL * v_mag;
                real_t scale_p = TINY_BCLIBC_CASHKARP_ATOL_P + TINY_BCLIBC_CASHKARP_RTOL * p_mag;
                real_t nv = err_v_mag / scale_v;
                real_t np_ = err_p_mag / scale_p;
                err_norm = (nv > np_) ? nv : np_;

                if (err_norm <= REAL_C(1.0) || dt <= min_dt * REAL_C(1.0001))
                {
                    vr5 = vr_out;
                    pos5 = pos_out;
                    tiny_bclibc__g_ck_accepted++;
                    /* grow for next step */
                    real_t grow = (err_norm > REAL_C(1.89e-4))
                                      ? TINY_BCLIBC_CASHKARP_SAFETY * TINY_BCLIBC_POW(err_norm, REAL_C(-0.20))
                                      : REAL_C(5.0);
                    if (grow > REAL_C(5.0))
                        grow = REAL_C(5.0);
                    if (grow < REAL_C(1.0))
                        grow = REAL_C(1.0); /* never shrink on an accepted step */
                    dt = dt * grow;
                    if (dt > max_dt)
                        dt = max_dt;
                    break;
                }
                else
                {
                    tiny_bclibc__g_ck_rejected++;
                    real_t shrink = TINY_BCLIBC_CASHKARP_SAFETY * TINY_BCLIBC_POW(err_norm, REAL_C(-0.25));
                    if (shrink < REAL_C(0.1))
                        shrink = REAL_C(0.1);
                    if (shrink > REAL_C(0.9))
                        shrink = REAL_C(0.9); /* must actually shrink */
                    dt = dt * shrink;
                    if (dt < min_dt)
                        dt = min_dt;
                    /* retry with smaller dt, same km/gpc/wind */
                }
            }

            time += dt_used;
            vr = vr5;
            pos = pos5;
        }

        /* final point */
        {
            real_t density_ratio, mach_fps;
            TINY_BCLIBC_Atmosphere_update_density_mach(&props->atmo,
                                                       props->alt0 + pos.y, &density_ratio, &mach_fps);
            real_t inv_mach = (mach_fps != REAL_C(0.0)) ? REAL_C(1.0) / mach_fps : REAL_C(1.0);
            real_t rel_speed = TINY_BCLIBC_SQRT(vr.x * vr.x + vr.y * vr.y + vr.z * vr.z);
            TINY_BCLIBC_BaseTrajData fin;
            fin.time = time;
            fin.px = pos.x;
            fin.py = pos.y;
            fin.pz = pos.z;
            fin.vx = vr.x + wind.x;
            fin.vy = vr.y + wind.y;
            fin.vz = vr.z + wind.z;
            fin.mach = rel_speed * inv_mach;
            on_step(&fin, ctx);
        }
        return TINY_BCLIBC_OK;
    }

#if defined(TINY_BCLIBC_USE_CASHKARP)
#define TINY_BCLIBC_RUN_ENGINE tiny_bclibc__run_cashkarp
#else
#define TINY_BCLIBC_RUN_ENGINE tiny_bclibc__run_rk4
#endif

/* ──────────────────────────────── END SPLICE ────────────────────────────── */
