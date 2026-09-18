# Attempt: true-velocity Hermite for ZERO-crossing interpolation

Follow-up to the Cash-Karp prototype (`tiny_bclibc_cashkarp.h`/`README.md` in
this directory). Tries the "narrower fix candidate" idea from `BACKLOG.md`'s
Cash-Karp section: instead of `tiny_bclibc_interpolate3pt`'s finite-difference
PCHIP slopes across 3 raw points, use `tiny_bclibc_hermite()` directly with
the **true** velocity (exact derivative) at the two raw points bracketing an
event, found via bisection on time. Tested against the real bclibc submodule
checkout (scratch, reverted afterward — not committed to that repo), same
toolchain/methodology as the main prototype.

**Status: promising direction, real bug found, not fixed — reverted, not
merged.** Saving this so whoever picks it up next doesn't repeat the same
mistake.

## What was patched

Only the `ZERO_UP`/`ZERO_DOWN` crossing-interpolation block in
`tiny_bclibc__integrate_on_step()` (`engine.h`) — the specific code path
identified as the source of the 7.5-yard `ZERO_UP` miss in the main
Cash-Karp report. Not touched: `TINY_BCLIBC_KEY_POS_X`-keyed RANGE-step
interpolation, `TINY_BCLIBC_KEY_TIME`-keyed interpolation, or the generic
`TINY_BCLIBC_BaseTrajData_interpolate()` — all of those still use
`tiny_bclibc_interpolate3pt()` unchanged. A full fix would need the same
treatment applied to each of those, with the derivative chain-ruled
appropriately for whichever field is the query axis (e.g. for
`KEY_POS_X`-keyed queries, `d(time)/d(px) == 1/vx`, `d(py)/d(px) == vy/vx` —
not just "swap in vx/vy/vz directly", since px itself is the axis there, not
time).

```c
/* Bracket whichever pair of raw points straddles the sign change, then
 * bisect on time using slant(t) reconstructed from an exact-derivative
 * cubic Hermite (dpx/dt==vx, dpy/dt==vy — no finite-difference estimate). */
{
    const TINY_BCLIBC_BaseTrajData *a, *b;
    real_t sa;
    if ((s0 <= REAL_C(0.0)) != (s1 <= REAL_C(0.0))) { a = &c->win[0]; b = &c->win[1]; sa = s0; }
    else { a = &c->win[1]; b = &c->win[2]; sa = s1; }
    real_t ta = a->time, tb = b->time, t_mid = ta;
    int32_t bi;
    for (bi = 0; bi < 30; bi++)
    {
        t_mid = REAL_C(0.5) * (ta + tb);
        real_t px_m = tiny_bclibc_hermite(t_mid, a->time, b->time, a->px, b->px, a->vx, b->vx);
        real_t py_m = tiny_bclibc_hermite(t_mid, a->time, b->time, a->py, b->py, a->vy, b->vy);
        real_t s_mid = py_m * la_cos - px_m * la_sin;
        if ((s_mid <= REAL_C(0.0)) == (sa <= REAL_C(0.0))) { ta = t_mid; sa = s_mid; }
        else { tb = t_mid; }
    }
    r.time = t_mid;
    r.px = tiny_bclibc_hermite(t_mid, a->time, b->time, a->px, b->px, a->vx, b->vx);
    r.py = tiny_bclibc_hermite(t_mid, a->time, b->time, a->py, b->py, a->vy, b->vy);
    r.pz = tiny_bclibc_hermite(t_mid, a->time, b->time, a->pz, b->pz, a->vz, b->vz);
}
```

(`r.vx`/`vy`/`vz`/`mach` left on the original `interpolate3pt` path —
out of scope for this attempt.)

## Results (375-test pytest suite, double precision)

| Build | Failed | Notes |
|---|---:|---|
| Stock RK4 (baseline) | 0 | |
| **Hermite fix alone (stock RK4, no Cash-Karp)** | **1** | new: `test_hitresult.py::test_tiny_step` — expects 6 rows, got 7 (see bug below) |
| Cash-Karp alone (per-stage drag+atmo, from the main prototype) | 5 | the floor this attempt was trying to lower |
| **Cash-Karp + Hermite fix together** | **9** | worse, not better — 4 *new* failures beyond Cash-Karp's own 5 (`test_danger_space`, `test_tiny_step`, both `TestIssue204::test_find_zero_angle` cases) |

## The bug (diagnosed, not fixed)

`test_tiny_step` fails with an **extra row** (7 instead of 6), not a wrong
value — the bisected crossing time is numerically different (almost
certainly *more* accurate, not less) from what `interpolate3pt` used to
produce, but that shift is enough to fall outside whatever time-delta
tolerance the row-coalescing logic (`_SEPARATE_ROW_TIME_DELTA`-equivalent in
this filter) uses to merge a ZERO-crossing row onto an adjacent RANGE-step
row that used to land at nearly the same instant. Previously the (less
accurate) shared interpolation method happened to produce close-enough times
for both events to coalesce; now they don't. **This is very likely a
tolerance/coalescing interaction, not an error in the Hermite math itself**
— worth checking first before assuming the interpolation is wrong.

The 4 additional failures that only show up combined with Cash-Karp
(`test_danger_space`, both `test_find_zero_angle` cases) suggest the same
coalescing issue is more exposed under sparse/irregular step spacing (fewer
candidate raw points near the crossing means less chance of an accidental
near-tie), rather than a second, independent bug — not confirmed, just the
more likely explanation given the pattern (isolated Hermite fix ⇒ 1 new
failure; combined with sparse stepping ⇒ several more of the same *shape*
of failure).

## Next steps, if picked up again

1. Check the actual coalescing tolerance value and whether it should simply
   be widened, or whether row coalescing should key off something more
   robust than a raw time-delta once interpolation is more accurate (e.g.
   coalesce based on which raw *step interval* two events fall into, not on
   how close their interpolated times happen to land).
2. Only then extend the same true-derivative approach to the
   `TINY_BCLIBC_KEY_POS_X` (RANGE-step) and generic
   `TINY_BCLIBC_BaseTrajData_interpolate()` paths, with correct chain-rule
   derivatives for whichever field is the query axis — this attempt only
   covered the ZERO-crossing path.
3. Re-run against the *single*-precision engine and real hardware (RP2350)
   once double-precision is clean — not done here.
