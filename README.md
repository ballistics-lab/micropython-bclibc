# tiny_bclibc MicroPython module

> [!WARNING]
> **Experimental feature.** This repository and the underlying `tiny_bclibc` C99 engine
> are experimental. APIs, binary format, and build system may change without notice in
> future releases. Do not use in production firmware without thorough validation on your
> specific target.

This repository provides three integration modes for using `tiny_bclibc` from
MicroPython — choose the one that fits your target and deployment constraints:

| Approach | Location | Architectures | Module deployment |
|----------|----------|--------------|-------------------|
| **natmod** (`.mpy`) | `natmod/` | x64, x86, armv6m–armv7emdp, xtensa, rv32/64imc | Copy `.mpy` to device filesystem |
| **usermod** (baked-in) | `usermod/` | any port with `USER_C_MODULES` support | Built into firmware — no file to copy |
| **FFI** (`libtiny_bclibc.so`) | `ffimod/` | any unix port arch | `import _tiny_bclibc` from `ffimod/` |

All three expose the same Python API: `Shot`, `Request`, `Wind`, `Config`,
`integrate`, `integrate_stream`, `find_zero_angle`, `find_apex`, `find_max_range`,
and all flag / index constants.

---

## Project structure

```
.
├── src/                        # Shared C + Python source
│   ├── tiny_bclibc_mp.c        # MicroPython C extension (natmod + usermod)
│   ├── tiny_bclibc.py          # Python API wrapper (frozen into firmware)
│   ├── drag_tables.h           # Built-in G1/G7 drag curve tables
│   └── math_shim.c             # math shim for x64/x86 natmod builds
│
├── natmod/                     # Native module (.mpy) build
│   ├── Makefile                # make x64 / armv6m / esp32c3 / …
│   ├── ci/run_qemu.py          # QEMU UART bridge for natmod CI tests
│   ├── examples/               # Usage examples
│   └── patches/                # MicroPython patches (if any)
│
├── usermod/                    # Usermod (baked-into-firmware) build
│   ├── Makefile                # make x64 / armhf / mipsel / rp2040 / …
│   ├── micropython.mk          # Picked up by py.mk via USER_C_MODULES
│   ├── micropython.cmake       # CMake entry point for RP2040 / pico-sdk
│   ├── manifest.py             # Freezes tiny_bclibc.py into firmware
│   ├── Dockerfile.x86          # Ubuntu 22.04 + gcc-multilib (x86 builds)
│   ├── Dockerfile.armhf        # Ubuntu 22.04 + gcc-arm-linux-gnueabihf
│   ├── Dockerfile.armv7m       # Ubuntu 22.04 + gcc-arm-none-eabi + qemu-system-arm
│   ├── Dockerfile.mipsel       # Ubuntu 22.04 + gcc-mipsel-linux-gnu
│   └── ci/run_qemu.py          # QEMU UART bridge for usermod CI tests
│
├── ffimod/                     # FFI-based access (any unix arch)
│   ├── _tiny_bclibc.py         # MicroPython ffi wrapper for libtiny_bclibc.so
│   ├── ffi.py                  # ffi helpers
│   └── uctypes.py              # uctypes shim for CPython test runner
│
├── tests/                      # Test suite (shared across all modes)
│   ├── test_bclibc.py          # Main test suite (natmod / usermod)
│   ├── test_ffi.py             # FFI backend tests
│   ├── tiny_bclibc_bench.py    # Benchmark script
│   ├── precision_compare.py    # float32 vs float64 comparison (CPython runner)
│   └── precision_run.py        # MicroPython worker for precision comparison
│
├── benchmarks/                 # Extended benchmark results and scripts
│
├── bclibc/                     # Git submodule → github.com/ballistics-lab/bclibc
│                               # Contains tiny_bclibc C99 engine (include/, src/)
│
├── version.h.in                # Version template (filled by Makefile)
├── CHANGELOG.md
└── LICENSE
```

---

## natmod (`.mpy` native module)

Native module (`.mpy`) produced by `mpy_ld.py`. Deploy by copying `.mpy` files to the
device filesystem (or embedding them into firmware via `FROZEN_MANIFEST`).

Supported only on architectures that `mpy_ld.py` can link:

| Approach | Architectures | Requires |
|----------|--------------|---------|
| Native `.mpy` natmod | x64, x86, armv6m–armv7emdp, xtensa, rv32/64imc | `mpy_ld.py` linker support |
| FFI (`libtiny_bclibc.so`) | **any** unix port arch (aarch64, mipsel, …) | `libffi`, shared library build |

## Prerequisites

### Python tooling

```bash
pip install pyelftools ar      # required by mpy_ld.py
```

### MicroPython source

The build system needs MicroPython v1.28 (for `dynruntime.mk`, `mpy-cross`,
and `lib/libm`).  Pass `MPY_DIR` explicitly or place it at `../micropython-1.28.0`:

```bash
wget https://github.com/micropython/micropython/releases/download/v1.28.0/micropython-1.28.0.tar.xz
tar xf micropython-1.28.0.tar.xz
export MPY_DIR=$(pwd)/micropython-1.28.0
```

### Cross-compilers

| Target | Package (Debian/Ubuntu) |
|--------|-------------------------|
| x64 | `gcc` (host compiler, already installed) |
| x86 | `gcc-multilib` |
| RP2040 / Cortex-M | `gcc-arm-none-eabi libnewlib-arm-none-eabi` |
| ESP32-C3/C6 (RISC-V 32/64) | `gcc-riscv64-unknown-elf picolibc-riscv64-unknown-elf` |
| ESP32 / ESP32-S3 | `xtensa-esp32{s3}-elf-gcc` (from ESP-IDF) |

```bash
sudo apt-get install gcc-arm-none-eabi libnewlib-arm-none-eabi \
                     gcc-multilib gcc-riscv64-unknown-elf
```

## Build

All commands are run from `natmod/` unless noted otherwise.

Precision suffix: `_dp` = double, `_sp` = single.
Default precision: **double** for x64/x86 host, **single** for all MCU targets.

```bash
make x64        # x64 double           → natmod/build/x64_dp/
make x64sp      # x64 single           → natmod/build/x64_sp/
make x86        # x86 double           → natmod/build/x86_dp/
make x86sp      # x86 single           → natmod/build/x86_sp/
make rp2040     # armv6m    single     → natmod/build/armv6m_sp/    — Raspberry Pi Pico
make armv7m     # armv7m    single     → natmod/build/armv7m_sp/    — Cortex-M3
make rp2350     # armv7emsp single     → natmod/build/armv7emsp_sp/ — RP2350
make stm32f4    # armv7emsp single     → natmod/build/armv7emsp_sp/ — STM32F4
make stm32h7    # armv7emdp single     → natmod/build/armv7emdp_sp/ — STM32H7
make stm32h7dp  # armv7emdp double     → natmod/build/armv7emdp_dp/ — STM32H7 (DP FPU)
make esp32s3    # xtensawin single     → natmod/build/xtensawin_sp/ — ESP32-S3
make esp32      # xtensa    single     → natmod/build/xtensa_sp/    — ESP32
make esp32c3    # rv32imc   single     → natmod/build/rv32imc_sp/   — ESP32-C3 / C6
make rv64       # rv64imc   single     → natmod/build/rv64imc_sp/   — RISC-V 64
```

Output per target: `natmod/build/<arch>_<sp|dp>/_tiny_bclibc.mpy` + `natmod/build/<arch>_<sp|dp>/tiny_bclibc.mpy`

`bc.version()` returns `"1.1.3-sp"` or `"1.1.3-dp"`.

```bash
make clean      # rm -rf natmod/build/ natmod/generated/
```

### Custom MPY_DIR or precision

```bash
make ARCH=armv6m MPY_DIR=/path/to/micropython-1.28.0
make ARCH=armv7emdp PRECISION=double   # double on Cortex-M7  → build/armv7emdp_dp/
make ARCH=x64 PRECISION=single         # single on host       → build/x64_sp/
```

## Test (x64 / x86 host)

```bash
# Build MicroPython unix binary (must match the .mpy version)
make -C "$MPY_DIR/ports/unix" VARIANT=standard
MPY="$MPY_DIR/ports/unix/build-standard/micropython"

# Build natmod (from natmod/)
make x64        # → natmod/build/x64_dp/_tiny_bclibc.mpy  natmod/build/x64_dp/tiny_bclibc.mpy

# Symlink .mpy files into tests/ so test_bclibc.py can import them
ln -sf ../natmod/build/x64_dp/_tiny_bclibc.mpy tests/_tiny_bclibc.mpy
ln -sf ../natmod/build/x64_dp/tiny_bclibc.mpy  tests/tiny_bclibc.mpy

# Run tests (natmod)
$MPY tests/test_bclibc.py

# Run tests (ffi — calls libtiny_bclibc.so directly, no .mpy needed)
python3 tests/test_ffi.py        # CPython
$MPY   tests/test_ffi.py         # MicroPython unix
```

Expected output ends with `=== done ===` and all lines read `PASS`.

---

## Usermod (baked into firmware)

`usermod/` compiles `tiny_bclibc` directly into the MicroPython firmware via
`USER_C_MODULES`. No `.mpy` file needs to be copied to the device — the module is always
available as a built-in. Use this approach when:

- you own the firmware build (RP2040, ESP32, custom STM32 …)
- you want zero-overhead import (no filesystem read, no bytecode loading)
- you need a fully static / standalone unix binary for deployment or CI

### Build targets

All commands are run from `usermod/`.

```bash
make x64          # x64 double (default)
make x64sp        # x64 single
make x86          # x86 double           [Docker — no host toolchain needed]
make x86sp        # x86 single           [Docker]
make aarch64      # AArch64 double  (cross: aarch64-linux-gnu-, static)
make aarch64sp    # AArch64 single
make armhf        # ARMv7hf double       [Docker — no host toolchain needed]
make armhfsp      # ARMv7hf single       [Docker]
make mipsel       # MIPS LE double       [Docker]
make mipselsp     # MIPS LE single       [Docker]
make qemu-armv7m  # Cortex-M3 build + test [Docker]
make rp2040       # RP2040 single (cmake, pico-sdk)
make rp2040dp     # RP2040 double
```

Output for unix targets: `usermod/build/<target>/micropython`
Output for rp2040: `$MPY_DIR/ports/rp2/build-RPI_PICO/firmware.uf2`

Precision is passed as `TINY_BCLIBC_PRECISION=single|double` for make-based ports and
`TINY_BCLIBC_DOUBLE_PRECISION=1` for cmake-based ports.

### Prerequisites

```bash
# x64 / x64sp — host gcc only (already installed)

# aarch64 / aarch64sp — cross-compiler on host
sudo apt-get install gcc-aarch64-linux-gnu

# x86, armhf, mipsel, qemu-armv7m — Docker only, no host toolchain needed:
#   Docker images are built automatically on first run from usermod/Dockerfile.*

# rp2040 / rp2040dp — bare-metal ARM toolchain
sudo apt-get install gcc-arm-none-eabi libnewlib-arm-none-eabi
```

`MPY_DIR` must be set explicitly or default to `micropython` (local symlink at repo root).

### Test (unix host)

```bash
cd usermod
make x64 MPY_DIR=/path/to/micropython-1.28.0
build/x64_dp/micropython tests/test_bclibc.py
```

### Test (RP2040)

```bash
make rp2040 MPY_DIR=/path/to/micropython-1.28.0
# flash build-RPI_PICO/firmware.uf2 to the board
# then from the REPL:
# >>> import tiny_bclibc; tiny_bclibc.version()
# '1.1.3-sp'
```

If the filesystem was not yet formatted after flashing custom firmware, format it once:

```python
import vfs, rp2
bdev = rp2.Flash()
vfs.VfsLfs2.mkfs(bdev)
vfs.mount(bdev, '/')
```

### Test (QEMU Cortex-M3 / armv7m_sp)

Runs entirely inside Docker — no host toolchain needed:

```bash
cd usermod
make qemu-armv7m MPY_DIR=/path/to/micropython-1.28.0
```

The `qemu-armv7m` target builds the Docker image on first run, then inside the container:
mpy-cross → version header → MPS2_AN385 firmware → `ci/run_qemu.py` test.

### Test (armhf / qemu-arm)

```bash
cd usermod
make armhf MPY_DIR=/path/to/micropython-1.28.0
qemu-arm build/armhf_dp/micropython ../tests/test_bclibc.py
```

The build runs inside Docker (`Dockerfile.armhf`). Only `qemu-arm` is needed on the host:

```bash
sudo apt-get install qemu-user
```

### natmod vs usermod comparison

| | natmod | usermod |
|--|--------|---------|
| Module delivery | `.mpy` file on filesystem | Built into firmware |
| Firmware re-flash needed | No | Yes (per build) |
| Architectures | mpy_ld.py supported only | Any port with `USER_C_MODULES` |
| Memory at import | Filesystem read + bytecode load | Instant (already in flash) |
| RP2040 support | armv6m `.mpy` | cmake `USER_C_MODULES` |
| Unix port support | Yes | Yes (also produces a micropython binary) |

---

## FFI-based access (any unix architecture)

On architectures where `mpy_ld.py` does not yet support native modules (aarch64, mipsel,
and others), MicroPython's built-in `ffi` module can call `libtiny_bclibc.so` directly.
Two entry points are available:

| Module | Location | Description |
|--------|----------|-------------|
| `_tiny_bclibc.py` | `ffimod/` | Drop-in module with the full public API |
| `test_ffi.py` | `tests/` | Runs full test suite against the FFI backend |

```bash
# 1. Build libtiny_bclibc.so for the target platform (native or cross)
cmake -B ../tiny_bclibc/build-shared \
      -S ../tiny_bclibc \
      -DTINY_BCLIBC_BUILD_SHARED=ON \
      -DCMAKE_BUILD_TYPE=Release
cmake --build ../tiny_bclibc/build-shared

# 2. Build MicroPython unix port for the target (with ffi support)
make -C "$MPY_DIR/ports/unix" VARIANT=standard

MPY="$MPY_DIR/ports/unix/build-standard/micropython"

# 3. Run full test suite via the FFI module (sp or dp)
TINY_BCLIBC_SO=../tiny_bclibc/build-shared/libtiny_bclibc.so \
TINY_BCLIBC_PRECISION=double \
$MPY tests/test_ffi.py
```

Both skip automatically on 32-bit platforms (pointer size ≠ 8 bytes).

`ffimod/_tiny_bclibc.py` supports both `single` and `double` precision via
`TINY_BCLIBC_PRECISION` and provides the same API as the natmod: `Shot`, `Request`,
`Wind`, `Config`, `integrate`, `integrate_stream`, `find_zero_angle`, `find_apex`,
`find_max_range`, and all flag / index constants.

## Test (QEMU — Cortex-M3 / armv7m)

```bash
sudo apt-get install qemu-system-arm
pip install pyserial

# Build MicroPython cross-compiler and QEMU firmware (one-time)
make -C "$MPY_DIR/mpy-cross"
make -C "$MPY_DIR/ports/qemu" BOARD=MPS2_AN385

# Build natmod
make armv7m
ln -sf ../natmod/build/armv7m_sp/_tiny_bclibc.mpy tests/_tiny_bclibc.mpy
ln -sf ../natmod/build/armv7m_sp/tiny_bclibc.mpy  tests/tiny_bclibc.mpy

# Run tests through the QEMU pty bridge
python3 natmod/ci/run_qemu.py \
    "$MPY_DIR/ports/qemu/build-MPS2_AN385/firmware.elf" \
    tests/
```

## Test (QEMU — Cortex-M0 / armv6m)

Uses MicroPython's `MICROBIT` QEMU board (nRF51 SOC, `cortex-m0`).

```bash
sudo apt-get install qemu-system-arm
pip install pyserial

# Build MicroPython cross-compiler and QEMU firmware (one-time)
make -C "$MPY_DIR/mpy-cross"
make -C "$MPY_DIR/ports/qemu" BOARD=MICROBIT

# Build natmod
make rp2040
ln -sf ../natmod/build/armv6m_sp/_tiny_bclibc.mpy tests/_tiny_bclibc.mpy
ln -sf ../natmod/build/armv6m_sp/tiny_bclibc.mpy  tests/tiny_bclibc.mpy

# Run tests through the QEMU pty bridge
python3 natmod/ci/run_qemu.py \
    "$MPY_DIR/ports/qemu/build-MICROBIT/firmware.elf" \
    tests/ \
    --machine microbit \
    --qemu-extra "-global nrf51-soc.flash-size=1048576 -global nrf51-soc.sram-size=262144"
```

## Module API

```python
import tiny_bclibc as bc
from tiny_bclibc import Shot, Request, Wind, Config, DRAG_G1, DRAG_G7, DRAG_CUSTOM

bc.version()              # → "1.2.3"

# ── Constructors ──────────────────────────────────────────────────────────────
shot = Shot(bc=0.310, weight_grain=168.0, muzzle_velocity_fps=2750.0)
req  = Request(range_limit_ft=3000.0, range_step_ft=100.0)

# Wind: field access via ._s (zero-copy uctypes struct backed by ._buf)
w = Wind(velocity_fps=10.0, direction_from_rad=1.57)
w._s.velocity_fps        # read field
w._s.direction_from_rad  # read/write field

# Config: same pattern
cfg = Config(max_iterations=100)
cfg._s.step_multiplier   # read/write field

# Shot with winds and custom config
shot = Shot(
    bc=0.310, weight_grain=168.0, muzzle_velocity_fps=2750.0,
    winds=[Wind(10.0, 0.0)],
    config=Config(max_iterations=50),
)

# ── Trajectory integration — buffered ────────────────────────────────────────
rows, stop_reason = bc.integrate(shot, req)
# rows: list of 16-tuples — use T_* indices to access fields

# ── Trajectory integration — streaming (no per-point allocation) ─────────────
def on_point(row):
    # called once per filtered output point; return truthy to stop early
    print(row[bc.T_DISTANCE], row[bc.T_VELOCITY])
total, stop_reason = bc.integrate_stream(shot, req, on_point)

# ── Zero-angle search ─────────────────────────────────────────────────────────
elevation_rad = bc.find_zero_angle(shot, zero_distance_ft)

# ── Maximum range (golden-section search over [low_rad, high_rad]) ────────────
range_ft, angle_rad = bc.find_max_range(shot, low_rad, high_rad)

# ── Single-point interpolation ────────────────────────────────────────────────
raw, full = bc.integrate_at(shot, bc.INTERP_POS_X, distance_ft)
# raw: 8-tuple (time, px, py, pz, vx, vy, vz, mach)
# full: same 16-tuple as integrate() rows

# ── Apex ──────────────────────────────────────────────────────────────────────
apex = bc.find_apex(shot)   # → single trajectory row 16-tuple

# ── Trajectory flag constants ─────────────────────────────────────────────────
tiny_bclibc.TRAJ_FLAG_NONE       # 0
tiny_bclibc.TRAJ_FLAG_ZERO_UP    # 1  — rising zero crossing
tiny_bclibc.TRAJ_FLAG_ZERO_DOWN  # 2  — falling zero crossing
tiny_bclibc.TRAJ_FLAG_ZERO       # 3  — any zero crossing
tiny_bclibc.TRAJ_FLAG_MACH       # 4  — Mach 1 crossing
tiny_bclibc.TRAJ_FLAG_RANGE      # 8  — range-step output
tiny_bclibc.TRAJ_FLAG_APEX       # 16 — apex
tiny_bclibc.TRAJ_FLAG_ALL        # 31
tiny_bclibc.TRAJ_FLAG_MRT        # 32 — max range trajectory

# ── Interpolation key constants ───────────────────────────────────────────────
tiny_bclibc.INTERP_TIME          # 0
tiny_bclibc.INTERP_MACH          # 1
tiny_bclibc.INTERP_POS_X         # 2  — horizontal distance
tiny_bclibc.INTERP_POS_Y         # 3  — height
tiny_bclibc.INTERP_POS_Z         # 4  — lateral
tiny_bclibc.INTERP_VEL_X         # 5
tiny_bclibc.INTERP_VEL_Y         # 6
tiny_bclibc.INTERP_VEL_Z         # 7

# ── Trajectory tuple field indices ────────────────────────────────────────────
tiny_bclibc.T_TIME           # 0  — time (s)
tiny_bclibc.T_DISTANCE       # 1  — horizontal distance (ft)
tiny_bclibc.T_VELOCITY       # 2  — total velocity (fps)
tiny_bclibc.T_MACH           # 3  — Mach number
tiny_bclibc.T_HEIGHT         # 4  — height (ft)
tiny_bclibc.T_SLANT_HEIGHT   # 5  — height relative to look angle (ft)
tiny_bclibc.T_DROP_ANGLE     # 6  — trajectory angle minus look angle (rad)
tiny_bclibc.T_WINDAGE        # 7  — windage + spin drift (ft)
tiny_bclibc.T_WINDAGE_ANGLE  # 8  — windage angle (rad)
tiny_bclibc.T_SLANT_DISTANCE # 9  — slant distance (ft)
tiny_bclibc.T_ANGLE          # 10 — trajectory angle (rad)
tiny_bclibc.T_DENSITY_RATIO  # 11
tiny_bclibc.T_DRAG           # 12 — drag coefficient
tiny_bclibc.T_ENERGY         # 13 — kinetic energy (ft·lbf)
tiny_bclibc.T_OGW            # 14 — optimal game weight (lb)
tiny_bclibc.T_FLAG           # 15 — TRAJ_FLAG_* bitmask
```

See [src/tiny_bclibc.py](src/tiny_bclibc.py) for `Shot`, `Wind`, `Config`, `Request` constructors.

## Usage examples

### 1. Basic trajectory

```python
import tiny_bclibc as bc

shot = bc.Shot(
    bc=0.310,
    weight_grain=168.0,
    muzzle_velocity_fps=2750.0,
    diameter_inch=0.308,
    twist_inch=11.0,
    sight_height_ft=0.125,   # 1.5 inch
)
req = bc.Request(range_limit_ft=3280.84, range_step_ft=328.084)  # 1000 m / 100 m steps

rows, stop_reason = bc.integrate(shot, req)
for row in rows:
    print(f"{row[bc.T_DISTANCE]:.0f} ft  {row[bc.T_VELOCITY]:.1f} fps  {row[bc.T_HEIGHT]:.3f} ft")
```

### 2. Zero + corrections

`find_zero_angle` returns the barrel elevation in radians but does **not** store it in the
shot automatically. You must write it to `shot._s.barrel_elevation_rad` before calling
`integrate`. Without this step the shot flies with 0° barrel elevation.

```python
import tiny_bclibc as bc
import math

shot = bc.Shot(
    bc=0.310, weight_grain=168.0, muzzle_velocity_fps=2750.0,
    diameter_inch=0.308, twist_inch=11.0, sight_height_ft=0.125,
)

# Step 1 — find zero angle at 100 m
zero_dist_ft = 100 / 0.3048           # 100 m → ft
zero_angle = bc.find_zero_angle(shot, zero_dist_ft)

# Step 2 — store in shot (equivalent to set_weapon_zero in py_ballisticcalc)
shot._s.barrel_elevation_rad = zero_angle

# Step 3 — integrate to target distance
req = bc.Request(range_limit_ft=500 / 0.3048, range_step_ft=500 / 0.3048)
rows, _ = bc.integrate(shot, req)

# Step 4 — read correction from the last row
row = rows[-1]
# T_DROP_ANGLE = trajectory angle − look_angle (rad); negate to get hold/dial value
elev_mrad = -row[bc.T_DROP_ANGLE] * 1000      # positive → aim higher
wind_mrad = -row[bc.T_WINDAGE_ANGLE] * 1000   # positive → aim right
print(f"Elevation: {elev_mrad:.2f} mrad  Windage: {wind_mrad:.2f} mrad")
```

`T_DROP_ANGLE` is the ready-to-use angular correction — negate it to get the hold or
dial value. `T_SLANT_HEIGHT` gives the same information in linear units (ft above/below
the look-angle line).

### 3. look_angle + hold (uphill / different distance)

`barrel_elevation_rad` is the **total** absolute angle from horizontal. When the target
is uphill or you apply a hold for a different distance, add to `zero_angle`:

```python
look_angle_rad  = math.radians(15)       # target 15° uphill
hold_rad        = 0.003                  # +3 mrad hold for 500 m
shot._s.look_angle_rad       = look_angle_rad
shot._s.barrel_elevation_rad = look_angle_rad + zero_angle + hold_rad
```

`zero_angle` stays constant (computed once at zeroing distance). Only
`look_angle_rad` and `hold_rad` change per shot — the same decomposition used
by py_ballisticcalc's `look_angle + zero_elevation + relative_angle`.

### 4. Single point (`integrate_at`)

Cheaper than a full trajectory when only one distance matters:

```python
_raw, point = bc.integrate_at(shot, bc.INTERP_POS_X, 500 / 0.3048)
print(f"At 500 m: {point[bc.T_VELOCITY]:.1f} fps  drop={-point[bc.T_DROP_ANGLE]*1000:.2f} mrad")
```

### 5. Streaming (RAM-constrained MCU)

`integrate_stream` delivers one row at a time with no heap allocation for the trajectory:

```python
def on_row(row):
    energy = row[bc.T_ENERGY]
    print(f"{row[bc.T_DISTANCE]:.0f} ft  {energy:.0f} ft·lbf")
    if energy < 500:
        return True   # stop early

total, stop_reason = bc.integrate_stream(shot, req, on_row)
```

### `integrate` vs `integrate_stream`

| | `integrate` | `integrate_stream` |
|---|---|---|
| Returns | `(list[tuple], reason)` | `(total_count, reason)` |
| Heap allocation | `N × 16 floats` per trajectory | None |
| Python call per point | No | Yes (1 `mp_call`) |
| Random access to all rows | Yes | No — one at a time |
| Early stop | No | Yes — return truthy from callback |
| Best for | Post-processing, sorting, slicing, display of full table | Tight RAM (MCU), streaming to UART/display, early-exit on threshold |

**Use `integrate`** when you need the full result set after integration — e.g. print a table, compare rows, pass to another function.

**Use `integrate_stream`** when RAM is limited (RP2040 has ~200 KB free heap) or you want to process each point as it arrives — e.g. write to a display row by row, stop when energy drops below a threshold, or log to a file without buffering the entire trajectory.

The Python overhead of `integrate_stream` (one `mp_call` per filtered point) is negligible compared to the integration step itself — on RP2040 the call overhead is ~1–3 µs vs ~120 ms per full trajectory.

## Architecture notes

| ARCH | Precision | Math library | BSS |
|------|-----------|-------------|-----|
| x64 / x86 | double (default) | musl libm_dbl (bundled in MicroPython) | 0 |
| x64 / x86 | float (optional) | fdlibm single (bundled in MicroPython) | 0 |
| armv6m | float only | newlib libm.a (via LINK_RUNTIME) | 0 |
| armv7m | float only | newlib libm.a (via LINK_RUNTIME) | 0 |
| armv7emsp | float only | newlib libm.a (via LINK_RUNTIME) | 0 |
| armv7emdp | float (default) / double | newlib libm.a (via LINK_RUNTIME) | 0 |
| xtensawin / xtensa | float only | newlib libm.a (via LINK_RUNTIME) | 0 |
| rv32imc / rv64imc | float only | fdlibm single + libgcc soft-float | 0 |

> **RISC-V note:** picolibc triggers a `mpy_ld.py` bug on current MicroPython.
> fdlibm is used as a workaround until the fix lands upstream.
> See [natmod/RISC-V_picolibc.md](natmod/RISC-V_picolibc.md) for details and the patch.

BSS must be 0 — MicroPython natmod ABI does not allow uninitialized static data.

### `find_zero_angle` performance (`TINY_BCLIBC_FAST_ZERO_FIND`)

`find_zero_angle` uses a Golden-Section Search (GSS) to bracket the max-range angle,
then Ridder's method to find the zero angle. Each GSS iteration runs a full RK4
trajectory, which is expensive on soft-float MCUs (Cortex-M0+, RISC-V without FPU).

`TINY_BCLIBC_FAST_ZERO_FIND` is automatically defined when building with `PRECISION=single`.
It applies two optimisations that do **not** affect the final angle accuracy:

| Parameter | Default | Fast |
|-----------|---------|------|
| GSS step multiplier | 1× | 8× coarser (fewer RK4 steps per trajectory) |
| GSS convergence `h` | `1e-5 rad` | `1e-2 rad` (~13 iterations vs ~25) |
| Ridder's `acc` | `0.001 ft` | `0.01 ft` (3 mm — more than sufficient for `float`) |

The bracket bound (`angle_at_max`) is used only to constrain Ridder's search interval;
its precision does not affect the output. Ridder's method always uses the original
`calc_step`.

To build without `FAST_ZERO_FIND` even on `PRECISION=single`, remove
`-DTINY_BCLIBC_FAST_ZERO_FIND` from `CFLAGS_EXTRA` in the Makefile.

See [src/sincosf_shim.md](src/sincosf_shim.md) for why `src/math_shim.c` is only compiled on x64/x86 and how to add it back for MCU targets if needed.

## Memory budget

Measured on x64 host, MicroPython v1.28, G7 drag, 168 gr @ 2750 fps.
Each output row costs ~**653 B** of heap (allocated by `tiny_bclibc.integrate()`).

| Range step | Rows (3 km) | Heap delta |
|-----------|-------------|------------|
| 100 m | 30 | ~19.5 KB |
| 50 m | 60 | ~39 KB |
| 25 m | 120 | ~78 KB |
| 10 m | 300 | ~197 KB |

### Per-platform recommendation

| Board | MCU | Arch | Usable heap¹ | Max step @ 3 km |
|-------|-----|------|-------------|-----------------|
| Raspberry Pi Pico | RP2040 | armv6m | ~192 KB | 10 m ✓ |
| Raspberry Pi Pico 2 | RP2350 | armv7emsp | ~480 KB | 10 m ✓ |
| STM32F401 (128 KB RAM) | Cortex-M4 | armv7emsp | ~64 KB | 50 m |
| STM32F405/F407 (192 KB RAM) | Cortex-M4 | armv7emsp | ~128 KB | 25 m |
| STM32H743 (1 MB RAM) | Cortex-M7 | armv7emdp | ~512 KB | 10 m ✓ |
| ESP32 | Xtensa LX6 | xtensa | ~200 KB | 25 m |
| ESP32-S3 | Xtensa LX7 | xtensawin | ~300 KB | 10 m ✓ |
| ESP32-S3 + PSRAM | Xtensa LX7 | xtensawin | ~8 MB | 1 m ✓ |
| ESP32-C3 | RISC-V | rv32imc | ~390 KB | 10 m ✓ |
| ESP32-C6 | RISC-V | rv32imc | ~490 KB | 10 m ✓ |

¹ Approximate free heap after MicroPython runtime starts. Actual value depends on
firmware variant, frozen modules, and Wi-Fi stack (ESP32).

For MCUs where the result list must fit in constrained RAM, stream results row by row
using `integrate_at()` + a range loop instead of storing the full trajectory.

## Float32 vs Float64 precision comparison

### Test methodology

The comparison runs the full trajectory integration twice — once with the float64 natmod
(`build/x64_dp/_tiny_bclibc.mpy`, `PRECISION=double`) and once with the float32
natmod (`build/x64_sp/_tiny_bclibc.mpy`, `PRECISION=single`) — and diffs the output
row by row. `find_zero_angle` is also compared between the two builds.

**Important:** `range_step_ft` in the `Request` is the *output sampling step* only.
The internal RK4 integrator uses its own sub-step controlled by `step_multiplier` (default
`0.5`) and is completely independent of the output step. Changing the output step does not
affect integration accuracy.

On the MicroPython unix port, Python `float` is 64-bit (double), so both natmods return
full-width Python floats. The float32 values have float32 precision (significant bits
truncated by the C layer), while float64 values have full double precision — the comparison
is numerically valid.

**Test conditions:**
- Shot: G7, BC=0.310, 168 gr, dia=0.308", mv=2750 fps, sight=0.125 ft (1.5"), twist=11"
- Atmosphere: T=15°C, P=1013.25 hPa, RH=0.5, alt=0 ft
- Range: 0–3000 m, output step=25 m (120 sample points)
- Internal RK4 step multiplier: 0.5 (default)
- Host: MicroPython v1.26 unix port, x64, Python float=64-bit

### Results

| Metric | Max deviation | At |
|--------|--------------|-----|
| Vertical drop (`height_ft`) | **0.108 cm** | 2975 m |
| Velocity | **0.0015 fps** (0.0005 m/s) | 1125 m |
| Mach number | **1.32 × 10⁻⁶** | — |
| `find_zero_angle` (300 m zero) | **5 × 10⁻¹⁰ rad** (< 0.001 mrad) | — |

Drop deviation grows slowly with distance and changes sign around 1200–1300 m (float32
overshoots slightly, then undershoots). At 3000 m the accumulated error is ≈ 0.1 cm —
negligible against any real-world uncertainty source (wind, BC spread, muzzle velocity
variation). Float32 is sufficient for all supported MCU targets.

### Reproduction

```bash
# Build both precision variants (from natmod/)
make x64     # → natmod/build/x64_dp/  (float64, default)
make x64sp   # → natmod/build/x64_sp/  (float32)

# Run comparison (from /, requires CPython 3.10+)
python3 tests/precision_compare.py
```

See [`tests/precision_compare.py`](tests/precision_compare.py) (CPython runner) and
[`tests/precision_run.py`](tests/precision_run.py) (MicroPython worker).

> [!WARNING]
>
> ## RISK NOTICE
>
> This library performs approximate simulations of complex physical processes.
> Therefore, the calculation results MUST NOT be considered as completely and reliably > reflecting actual behavior of projectiles. While these results may be used for educational purpose, they must NOT be considered as reliable for the areas where incorrect calculation may cause making a wrong decision, financial harm, or can put a human life at risk.
> 
> THE CODE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE MATERIALS OR THE USE OR OTHER DEALINGS IN THE MATERIALS.