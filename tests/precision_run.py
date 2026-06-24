# ruff: noqa
"""
precision_run.py — worker for precision comparison.

Runs a 3000 m trajectory and prints results to stdout.
Invoked by precision_compare.py; not meant to be run directly.

Output format:
  Line 1:  "meta\t<micropython_version>\t<float_impl>\t<float_size>"
  Line 2:  "zero_angle\t<elev_rad>"
  Line 3+: TSV header + data rows
            dist_m  vel_fps  height_ft  mach  time_s  windage_ft
"""

import sys

_HERE = __file__.rsplit("/", 1)[0] if "/" in __file__ else "."
sys.path.append(_HERE)

import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, DRAG_G7

SHOT = Shot(
    bc=0.310,
    weight_grain=168.0,
    diameter_inch=0.308,
    length_inch=1.2,
    muzzle_velocity_fps=2750.0,
    sight_height_ft=0.125,  # 1.5 in = 0.125 ft
    twist_inch=11.0,
    temp_c=15.0,
    pressure_hpa=1013.25,
    altitude_ft=0.0,
    humidity=0.5,
    drag_type=DRAG_G7,
)

_FT_PER_M = 3.28084
STEP_M = 25.0
LIMIT_M = 3000.0
ZERO_M = 300.0

# ── Meta info ─────────────────────────────────────────────────────────────────
import micropython as _mp  # noqa: E402 — present only in MicroPython

_ver = sys.version
_fimpl = getattr(_mp, "const", None)  # proxy: const exists → float is platform-native
# Detect float byte-size via struct
import struct as _struct

_fsz = _struct.calcsize("f")  # always 4
_dsz = _struct.calcsize("d")  # 4 on some embedded builds, 8 on host
_float_bits = _dsz * 8  # 32 or 64

print(
    "meta\t{}\t{}\t{}".format(
        sys.version.split(";")[0].strip(), sys.implementation.name, _float_bits
    )
)

# ── find_zero_angle ────────────────────────────────────────────────────────────
zero_dist_ft = ZERO_M * _FT_PER_M
elev_rad = bc.find_zero_angle(SHOT, zero_dist_ft)
print("zero_angle\t{:.10f}".format(elev_rad))

# ── Trajectory integration ─────────────────────────────────────────────────────
REQUEST = Request(
    range_limit_ft=LIMIT_M * _FT_PER_M,
    range_step_ft=STEP_M * _FT_PER_M,
    filter_flags=bc.TRAJ_FLAG_RANGE,
)

rows, _reason = bc.integrate(SHOT, REQUEST)

# row layout: (time_s, dist_ft, vel_fps, mach, height_ft, windage_ft, ...)
print("dist_m\tvel_fps\theight_ft\tmach\ttime_s\twindage_ft")
for r in rows:
    time_s, dist_ft, vel_fps, mach, height_ft, windage_ft = (
        r[0],
        r[1],
        r[2],
        r[3],
        r[4],
        r[5],
    )
    dist_m = dist_ft / _FT_PER_M
    print(
        "{:.2f}\t{:.9f}\t{:.9f}\t{:.9f}\t{:.9f}\t{:.9f}".format(
            dist_m, vel_fps, height_ft, mach, time_s, windage_ft
        )
    )
