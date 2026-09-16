# Cash-Karp adaptive RK45 prototype for `tiny_bclibc` — reference artifact

**Status: unwired prototype, not production-ready, not integrated into any build.**
This directory exists only to preserve hard-won investigation results for whoever
picks up the follow-on work. Nothing here is referenced by `micropython-bclibc`'s
own build (`usermod/manifest.py`, `micropython.mk`, `natmod/`) and nothing in the
real `ballistics-lab/bclibc` submodule was modified to produce it — see
"Provenance" below.

## What this is

A prototype `tiny_bclibc__run_cashkarp()` — a 6-stage Cash-Karp embedded RK45
adaptive-step integrator — as a drop-in alternative to `tiny_bclibc`'s existing
fixed-step `tiny_bclibc__run_rk4()`, explored as an alternative/complement to
simply raising `cStepMultiplier` (see `BACKLOG.md`'s Epic 2 RK4 step-size
investigation for that baseline). The code is in `tiny_bclibc_cashkarp.h` in this
directory, written to be spliced into `tiny_bclibc/include/tiny_bclibc/engine.h`
(see the comment header in that file for exact instructions).

**Bottom line: the adaptive-integration core works and is a bigger speed win than
raising `cStepMultiplier` — but it is not accuracy-safe to ship, because of a
structural problem in a *different* part of `tiny_bclibc` (event-crossing
interpolation) that the integrator swap exposes but doesn't cause.**

## Numerical Recipes `rkck` tableau and step control used

Standard Cash-Karp coefficients (Numerical Recipes' `rkck`), 6 stages:

- 5th-order solution weights: `b1=37/378, b3=250/621, b4=125/594, b6=512/1771`
  (`b2=b5=0`)
- Error estimate: `d_i = b_i - b_i*` where `b*` is the embedded 4th-order
  solution's weights (`2825/27648, 0, 18575/48384, 13525/55296, 277/14336, 1/4`)
- Step-control law (fairly standard embedded-RK shape, closely matching the
  `rk45-dev` reference below):
  - Accept if `err_norm <= 1`. Grow: `dt *= clamp(0.9 * err_norm^-0.2, 1.0, 5.0)`.
  - Reject and retry (same frozen step-start aux state): `dt *= clamp(0.9 *
    err_norm^-0.25, 0.1, 0.9)`.
  - `err_norm = max(|err_v|/(atol_v + rtol*|v|), |err_p|/(atol_p + rtol*|p|))`,
    i.e. a combined relative+absolute tolerance on both velocity and position,
    taking the worse of the two.
  - `dt` bounds: `[base_dt/64, base_dt*64]` where `base_dt = calc_step` (i.e.
    `0.0025 * cStepMultiplier`, same base the fixed-step RK4 uses).
  - `TINY_BCLIBC_CASHKARP_RTOL` is a compile-time `#define` (default `1e-4`) —
    override at build time to sweep tolerance, e.g.
    `-DTINY_BCLIBC_CASHKARP_RTOL=1e-6` (append `f` for a single-precision build).

State carried through the 6 stages is `(v_rel, pos)` rather than `(vel, pos)`:
since wind is piecewise-constant over a step (already true of the existing fixed
step RK4), `d(pos)/dt = v_rel + wind` and `d(v_rel)/dt == d(vel)/dt`, so `vel`
never needs to be tracked separately.

## The central finding: RK4's own memoization does not survive adaptive stepping

`tiny_bclibc__run_rk4` computes the drag coefficient
`km = density_ratio * drag_by_mach(mach)` **once** per fixed 1.25ms step and
reuses it across all 4 substages — a real approximation already in the existing
engine, cheap because the step is always tiny.

`tiny_bclibc_cashkarp.h` implements **three** variants of the per-stage
derivative function (`tiny_bclibc__ck_f`), selected by which of two macros is
defined at compile time, to make this comparison reproducible:

| Variant | Macro | What it does | Result (375-test py-ballisticcalc suite, double precision — RK4 baseline = 0 failures) |
|---|---|---|---|
| (a) frozen km | *(neither defined)* | Reuses RK4's own trick: km computed once, reused across all 6 stages | **26–36 failures, and does not improve as rtol tightens from 1e-4 to 1e-7 (1000x range)** |
| (b) per-stage drag | `TINY_BCLIBC_CASHKARP_PERSTAGE_DRAG` | Recomputes the drag *coefficient* fresh at each stage from that stage's own `\|v_rel\|`; atmosphere (density/speed of sound) still frozen at step-start | 8–10 failures |
| (c) per-stage drag+atmosphere | `TINY_BCLIBC_CASHKARP_PERSTAGE_ATMO` | Recomputes drag **and** atmosphere fresh at each stage's own intermediate altitude (requires tracking intermediate `pos` through all 6 stages, not just `v_rel`) | **5-failure hard floor at rtol=1e-8** (does not improve further) |

Variant (a) is a dead end: sweeping tolerance across three orders of magnitude
doesn't change the failure count, because the embedded error estimator only
measures discretization error of the *frozen-km sub-problem* — it is blind to
the model error from km itself going stale as the step grows to 10-60x the
fixed-step size during smooth cruise. This directly falsifies the hope that
RK4's existing memoization could just be reused as-is for an embedded method.

Variant (c) is the one to use, and it wasn't just guessed at: it independently
matches (and was cross-checked against, mid-investigation) the
`o-murphy/py-ballisticcalc` branch `rk45-dev`'s unfinished RKF45 prototype for
the **full C++** bclibc engine
(`py_ballisticcalc.exts/py_ballisticcalc_exts/src/rk45.cpp`), which also
recomputes `drag_by_mach()` and the atmosphere sample fresh at every one of its
6 stages. Two independently-arrived-at implementations landing on the same
design is strong evidence this per-stage cost (6 drag+atmosphere lookups per
step instead of RK4's 1) is a *required* cost of any embedded RK method here,
not a matter of taste.

## The actual remaining blocker: event-crossing interpolation on sparse samples

Variant (c)'s 5-failure floor (double precision, rtol down to 1e-8) does **not**
improve with tighter tolerance — it is not an integration-accuracy problem.
Diagnosis: `tiny_bclibc`'s output filtering (`tiny_bclibc__integrate_on_step` in
`engine.h`, `BaseTrajData_interpolate`) detects/refines RANGE-step, APEX,
MACH-crossing, and ZERO-crossing events by fitting a curve through a **sliding
window of only 3 raw integration points**. That's accurate when raw points are
1.25ms apart (fixed-step RK4); it breaks down when Cash-Karp legitimately takes
few, large steps through smooth supersonic cruise (measured: ~60x fewer raw
points than the RK4 baseline for a 2000m G7 trajectory — see below), because the
window now spans a much wider, more curved arc of the real trajectory.

Concretely: `tests/test_hitresult.py::TestHitResult::test_flags` predicted the
ZERO_UP crossing at 40.5 yards vs. an expected 48.0 yards — a **7.5-yard miss**,
nowhere near floating-point noise. Two `TestTrajectoryDataFilter` cases fail
because a ZERO_DOWN event doesn't land on the same output row as its RANGE-step
neighbor (row-coalescing depends on event timing coincidence that no longer
holds with irregular step spacing).

**This is the actual blocker.** It is a structural mismatch between adaptive
stepping's sparsity (its whole value proposition) and infrastructure built
assuming dense, near-uniform raw samples — not something a tolerance knob can
fix.

## What finishing this would require

Two options, roughly in order of how invasive they are:

1. **Local step-size capping around detected events.** When the filter notices a
   sign change is imminent (a stage's velocity/altitude/mach crosses the
   relevant threshold), fall back to a bounded number of small sub-steps in that
   vicinity instead of accepting Cash-Karp's already-computed large step whole.
   Bounded, but adds complexity to the accept/reject loop and needs care not to
   defeat the speed win by capping too eagerly.
2. **Proper dense output / continuous extension.** Cash-Karp (and RK45 methods
   generally) support a continuous interpolant that can answer "what was the
   state at any point *within* the last accepted step" to full order accuracy,
   without extrapolating from neighboring steps. Replacing the 3-point window
   interpolation with a query into the last step's dense output would fix this
   at the root, but is more invasive — it changes the shape of the
   `on_step`/filter contract, not just the integrator.

Either way, this is bounded, understood work — not a rewrite — but it is a
**separate, second piece of work** from the integrator itself, which is already
proven out (see below).

## Speed numbers (x64, 200 reps/20 warmup; 2000m G7 Trajectory + Zero-to-2000m; flight time ≈6.19s)

| Config | Trajectory ms (speedup) | Zero ms (speedup) | Steps |
|---|---|---|---|
| RK4 single, `cStepMultiplier=0.5` (baseline) | 0.793 (1.0x) | 2.283 (1.0x) | ~4951 raw |
| RK4 single, `cStepMultiplier=2.0` | 0.450 (1.76x) | 0.903 (2.53x) | ~1238 raw |
| RK4 single, `cStepMultiplier=4.0` (known G7 accuracy regression) | 0.360 (2.20x) | 0.627 (3.64x) | ~619 raw |
| **Cash-Karp single, variant (c), rtol=1e-4** | **0.339 (2.34x)** | **0.521 (4.38x)** | **80 accepted, 0 rejected** |
| **Cash-Karp single, variant (c), rtol=1e-6** | **0.350 (2.27x)** | **0.542 (4.21x)** | **81 accepted, 0 rejected** |
| RK4 double, `cStepMultiplier=0.5` | 0.987 | 3.807 | ~4951 raw |
| Cash-Karp double, variant (c), rtol=1e-6 | 0.344 (2.87x) | 0.653 (5.83x) | 80 accepted, 0 rejected |
| Reference: real RP2350 hardware, RK4 `cStepMultiplier=2.0` (coordinator-supplied, already validated/shippable) | ~1.67x | — | — |

On a shorter G7 shot that crosses the transonic drag-curve kink (matching
`tests/test_trajectory.py::TestTrajectory::test_path_g7`'s 1000-yard fixture),
step telemetry showed **16 accepted + only 1 rejected step** — the "big steps in
smooth cruise, small steps only near the transition" hypothesis holds, with no
runaway step-rejection thrashing at the kink.

Cash-Karp beats even `cStepMultiplier=4.0` in wall-clock despite ~6x the
per-step drag/atmosphere lookup cost (variant (c)), because it needs ~62x fewer
total steps than the RK4 baseline (and ~8x fewer than `cStepMultiplier=4.0`) to
cover the same trajectory.

## Recommendation

**Pursue further, but as two separately-scoped pieces of work.** The
adaptive-RK integrator core (variant (c)) is proven: a bigger, real speedup than
the already-shipped `cStepMultiplier=2.0` (2.3-5.8x here vs. ~1.67x on real
hardware), and it doesn't hit the `cStepMultiplier=4.0` wall (no G7
trajectory-shape regression). But it currently trades RK4's known
float32-precision failures for a *different*, currently-unresolved set of
structural failures in event-crossing interpolation that persist even in double
precision and that no tolerance knob can fix. That needs its own bounded
follow-on effort (see "What finishing this would require" above) before this
could replace `tiny_bclibc__run_rk4` in production. If that follow-on isn't
budgeted, this isn't worth shipping over the already-validated,
zero-risk, one-line `cStepMultiplier=2.0` change.

## Provenance

Built and measured against a scratch (never committed, never pushed) copy of
the real `ballistics-lab/bclibc` submodule vendored at
`py-ballisticcalc/py_ballisticcalc.exts/py_ballisticcalc_exts/external/bclibc`,
using that repo's own `examples/tiny_bclibc` ctypes harness to run the real
375-test pytest suite and a benchmark script mirroring `scripts/benchmark.py`'s
Trajectory/Zero cases. That submodule checkout was reverted to pristine
(`git checkout --`, confirmed clean at commit `89132f5`) before this
investigation's session ended and has not been touched since. `tiny_bclibc_cashkarp.h`
in this directory is a reconstruction of that scratch code from the
investigating session's own record of its edits, preserved here purely as a
reference for follow-on work — not a live diff against any current checkout.

See `benchmark_cashkarp.py` in this directory for the A/B timing/step-count
harness used to produce the numbers above (adapt the `.so` paths at the top to
your own local build).
