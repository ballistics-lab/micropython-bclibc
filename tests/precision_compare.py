#!/usr/bin/env python3
# ruff: noqa
"""
precision_compare.py — compare float32 vs float64 trajectory deviation up to 3000 m.

Usage (from repo root or ):
    python3 tests/precision_compare.py

Requires (relative to natmod/):
    natmod/build/x64_sp/   (single precision, PRECISION=single)
    natmod/build/x64_dp/   (double precision, PRECISION=double)
    micropython in PATH
"""

import subprocess
import shutil
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_MPY = shutil.which("micropython") or "micropython"
_NATIVE_LINK = os.path.join(_HERE, "_tiny_bclibc.mpy")
_BYTECODE_LINK = os.path.join(_HERE, "tiny_bclibc.mpy")
_WORKER = os.path.join(_HERE, "precision_run.py")

_FT_TO_CM = 30.48
_FPS_TO_MPS = 0.3048


def _run(build_dir: str) -> dict:
    shutil.copy(os.path.join(_HERE, build_dir, "_tiny_bclibc.mpy"), _NATIVE_LINK)
    shutil.copy(os.path.join(_HERE, build_dir, "tiny_bclibc.mpy"), _BYTECODE_LINK)
    try:
        result = subprocess.run(
            [_MPY, _WORKER],
            cwd=_HERE,
            capture_output=True,
            text=True,
            timeout=60,
        )
    finally:
        for p in (_NATIVE_LINK, _BYTECODE_LINK):
            try:
                os.remove(p)
            except OSError:
                pass

    if result.returncode != 0:
        print("ERROR running", build_dir, file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    out = {"meta": {}, "zero_angle": None, "rows": []}
    lines = result.stdout.strip().splitlines()
    data_started = False

    for line in lines:
        if line.startswith("meta\t"):
            parts = line.split("\t")
            out["meta"] = {
                "version": parts[1] if len(parts) > 1 else "?",
                "impl": parts[2] if len(parts) > 2 else "?",
                "float_bits": parts[3] if len(parts) > 3 else "?",
            }
        elif line.startswith("zero_angle\t"):
            out["zero_angle"] = float(line.split("\t")[1])
        elif line.startswith("dist_m\t"):
            data_started = True
        elif data_started and line:
            vals = line.split("\t")
            headers = ["dist_m", "vel_fps", "height_ft", "mach", "time_s", "windage_ft"]
            out["rows"].append({h: float(v) for h, v in zip(headers, vals)})

    return out


def _align(rows_f, rows_d):
    d_map = {round(r["dist_m"]): r for r in rows_d}
    return [
        (rf, d_map[round(rf["dist_m"])])
        for rf in rows_f
        if round(rf["dist_m"]) in d_map
    ]


def _sep(w):
    print("-" * w)


def main():
    print("Running double-precision trajectory (../natmod/build/x64_dp)…")
    data_d = _run("../natmod/build/x64_dp")
    print("Running single-precision trajectory (../natmod/build/x64_sp)…")
    data_f = _run("../natmod/build/x64_sp")

    pairs = _align(data_f["rows"], data_d["rows"])
    if not pairs:
        print("No matching rows — check natmod output.", file=sys.stderr)
        sys.exit(1)

    meta_d = data_d["meta"]
    meta_f = data_f["meta"]

    # ── Header ─────────────────────────────────────────────────────────────────
    W = 92
    print()
    print("=" * W)
    print(
        "  float32 vs float64 trajectory deviation  (f32 − f64; positive = f32 higher/faster)"
    )
    print("=" * W)
    print('  Shot:  G7  BC=0.310  168 gr  dia=0.308"  len=1.2"  mv=2750 fps')
    print('         sight=0.125 ft  twist=11"  T=15°C  P=1013.25 hPa  RH=0.5  alt=0 ft')
    print("  Range: 0–3000 m  step=25 m  ({} points)".format(len(pairs)))
    print(
        "  Host:  MicroPython {}  float={}-bit".format(
            meta_d.get("version", "?"), meta_d.get("float_bits", "?")
        )
    )
    print(
        "  NOTE:  range_step is output sampling only; RK4 internal step is controlled by"
    )
    print("         step_multiplier (default 0.5) and is independent of output step.")
    print()

    # ── Zero angle comparison ───────────────────────────────────────────────────
    za_d = data_d["zero_angle"]
    za_f = data_f["zero_angle"]
    if za_d is not None and za_f is not None:
        import math

        diff_rad = za_f - za_d
        diff_mrad = diff_rad * 1000.0
        diff_deg = math.degrees(diff_rad)
        print("  find_zero_angle (300 m zero):")
        print("    f64 = {:.10f} rad  ({:.7f}°)".format(za_d, math.degrees(za_d)))
        print("    f32 = {:.10f} rad  ({:.7f}°)".format(za_f, math.degrees(za_f)))
        print(
            "    Δ   = {:+.4e} rad  ({:+.4f} mrad  {:+.6f}°)".format(
                diff_rad, diff_mrad, diff_deg
            )
        )
        print()

    # ── Trajectory deviation table ──────────────────────────────────────────────
    col = "{:>9}"
    hdr = (
        col.format("dist_m")
        + col.format("Δdrop_cm")
        + col.format("Δvel_fps")
        + col.format("Δmach_e5")
        + col.format("Δtime_ms")
        + col.format("Δwnd_cm")
        + "    height_f32 (ft)  height_f64 (ft)"
    )
    print(hdr)
    _sep(W)

    max_drop_cm = 0.0
    max_vel_fps = 0.0
    max_mach = 0.0
    worst_dist = 0.0

    for rf, rd in pairs:
        dist_m = rd["dist_m"]
        d_height = (rf["height_ft"] - rd["height_ft"]) * _FT_TO_CM
        d_vel = rf["vel_fps"] - rd["vel_fps"]
        d_mach = rf["mach"] - rd["mach"]
        d_time_ms = (rf["time_s"] - rd["time_s"]) * 1000.0
        d_wind_cm = (rf["windage_ft"] - rd["windage_ft"]) * _FT_TO_CM

        if abs(d_height) > abs(max_drop_cm):
            max_drop_cm = d_height
            worst_dist = dist_m
        max_vel_fps = max(max_vel_fps, abs(d_vel))
        max_mach = max(max_mach, abs(d_mach))

        print(
            col.format("{:.0f}".format(dist_m))
            + col.format("{:+.4f}".format(d_height))
            + col.format("{:+.5f}".format(d_vel))
            + col.format("{:+.3f}".format(d_mach * 1e5))
            + col.format("{:+.4f}".format(d_time_ms))
            + col.format("{:+.4f}".format(d_wind_cm))
            + "    {:.7f}  {:.7f}".format(rf["height_ft"], rd["height_ft"])
        )

    _sep(W)
    print("  Max |Δdrop|  : {:+.4f} cm  at {:.0f} m".format(max_drop_cm, worst_dist))
    print(
        "  Max |Δvel|   : {:.5f} fps  ({:.5f} m/s)".format(
            max_vel_fps, max_vel_fps * _FPS_TO_MPS
        )
    )
    print("  Max |Δmach|  : {:.2e}".format(max_mach))
    print("=" * W)
    print()
    print("  Reference: f64 (double precision, build/x64_dp)")
    print("  f32 = float32 (build/x64_sp, PRECISION=single)")
    print("  Δdrop_cm > 0 → f32 trajectory is higher than f64 at that distance.")
    print("  Δmach_e5 column = (f32_mach − f64_mach) × 10⁵")


if __name__ == "__main__":
    main()
