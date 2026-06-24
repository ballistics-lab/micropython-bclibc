# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

#### `usermod/Makefile` — mipsel builds inside Docker
- `mipsel` / `mipselsp` targets now run inside a Docker container (Ubuntu 20.04 + `gcc-mipsel-linux-gnu`) instead of requiring the toolchain on the host. Docker image is built automatically on first run from `usermod/Dockerfile.mipsel` and reused on subsequent builds.
- `usermod/Dockerfile.mipsel`: Ubuntu 20.04, `libtool-bin` included for `autoreconf`/`deplibs`; no host toolchain install needed for mipsel.
- Build sequence inside container: `mpy-cross` → `submodules` → `deplibs` → main build. Output lands on the host at `usermod/build/mipsel_{dp,sp}/micropython` via Docker volume mount.
- `.github/workflows/usermod.yml` `build-mipsel` job simplified: toolchain install, mpy-cross, and deplibs steps removed; replaced with a single `make mipsel MPY_DIR=...` step.

---

### Added (initial extraction from bclibc)

#### `usermod/` — MicroPython USER_C_MODULE (baked-in firmware module)

A second integration mode alongside natmod: `tiny_bclibc` compiled directly into the
MicroPython firmware via `USER_C_MODULES`. No `.mpy` file to deploy — the module is
available as a built-in at every boot.

- `usermod/Makefile`: cross-compile targets for all supported platforms:

  | Target | Precision | Host/cross | Notes |
  |--------|-----------|-----------|-------|
  | `x64` / `x64sp` | double / single | native x64 | unix port, dynamic |
  | `x86` / `x86sp` | double / single | 32-bit | unix port, standalone static |
  | `aarch64` / `aarch64sp` | double / single | `aarch64-linux-gnu-` | unix port, standalone static |
  | `armhf` / `armhfsp` | double / single | `arm-linux-gnueabihf-` | unix port, standalone static |
  | `mipsel` / `mipselsp` | double / single | `mipsel-linux-gnu-` | unix port, coverage variant, static |
  | `rp2040` | single | cmake (`arm-none-eabi`) | RP2040 firmware |
  | `rp2040dp` | double | cmake (`arm-none-eabi`) | RP2040 firmware, DP FPU |

  Build output: `usermod/build/<target>/micropython` (unix) or
  `$MPY_DIR/ports/rp2/build-RPI_PICO/firmware.{elf,uf2}` (rp2040).

- `usermod/micropython.mk`: `USER_C_MODULES` descriptor for make-based
  ports (unix, qemu, stm32, …). Points `MAKE_MODULES` to `` so py.mk
  finds `usermod/micropython.mk`. Precision via `TINY_BCLIBC_PRECISION=single|double`.

- `usermod/micropython.cmake`: `USER_C_MODULES` descriptor for cmake-based
  ports (rp2, esp32). Generates `generated/bclibc_mp/version.h` at cmake configure time if
  not already present. Precision via `TINY_BCLIBC_DOUBLE_PRECISION=1`.

- `usermod/manifest.py`: freezes `tiny_bclibc.py` into the firmware. For
  embedded ports (rp2, qemu) also includes the board's default manifest
  (`$(PORT_DIR)/boards/manifest.py`) so that `_boot.py` and the filesystem mount code are
  preserved; the include is silently skipped for unix port builds where it doesn't exist.

- `usermod/ci/run_qemu.py`: QEMU pty test runner for usermod firmware.
  Unlike the natmod variant, no `.mpy` injection is needed — `_tiny_bclibc` is a built-in
  and `tiny_bclibc.py` is frozen, so the runner just sends `test_bclibc.py` directly to
  the QEMU UART via `pyboard`.

#### `.github/workflows/usermod.yml` — CI for usermod builds

  | Job | Runner | Approach |
  |-----|--------|---------|
  | `build-armhf` | ubuntu-latest | Cross-compile, `MICROPY_STANDALONE=1 -static`, artifact upload |
  | `test-armhf` | ubuntu-latest | Download artifact, run under `qemu-arm` |
  | `build-mipsel` | ubuntu-latest | Cross-compile (coverage variant), static, artifact upload |
  | `test-mipsel` | ubuntu-latest | Download artifact, run under `qemu-mipsel` |
  | `build-test-aarch64` | ubuntu-24.04-arm64 | Native build + test + artifact upload |
  | `build-test-qemu-armv7m` | ubuntu-latest | Build MPS2_AN385 QEMU firmware + test via `run_qemu.py` |

  `workflow_dispatch` input `mpy_tag` to test against any MicroPython release.

#### `ffimod/` — standalone MicroPython FFI module
- `ffimod/_tiny_bclibc.py`: drop-in replacement for `tiny_bclibc` on unix MicroPython (x64 / aarch64), backed by `libtiny_bclibc.so` via the built-in `ffi` module — no native `.mpy` required
  - Same public API as the natmod (`Shot`, `Request`, `Wind`, `Config`, `integrate`, `integrate_stream`, `find_zero_angle`, `find_apex`, `find_max_range`, all constants)
  - Selects `float` or `double` C struct layout at runtime via `TINY_BCLIBC_PRECISION=single|double`
  - `.so` path overridable via `TINY_BCLIBC_SO` env var; default resolves relative to the module file
  - 64-bit only (`struct.calcsize("P") != 8` guard; 32-bit pointer layout is not supported)
- `ffimod/uctypes.py`, `ffi.py`: CPython shims for MicroPython's built-in `uctypes` and `ffi` modules — allow running `ffimod/_tiny_bclibc.py` under CPython without changes
- `tests/test_ffi.py`: injects `tiny_bclibc_mp_ffi` as `sys.modules["tiny_bclibc"]` and executes the full `tests/test_bclibc.py` suite against the FFI backend; runs under both CPython and MicroPython

#### `tiny_bclibc_integrate_stream` — zero-allocation streaming integration
- New public API: `tiny_bclibc_integrate_stream(props, req, cb, cb_ctx, out_total, out_reason)`
  - Calls a C callback `tiny_bclibc_StreamCb` once per filtered output point instead of writing to a heap buffer
  - Callback returns `TINY_BCLIBC_TERM_HANDLER_STOP` (or any non-zero) to abort integration early
  - No intermediate `TrajectoryData` buffer allocated — suitable for RAM-constrained MCUs
  - Shares 100 % of the filtering logic with `tiny_bclibc_integrate` via the existing `tiny_bclibc__integrate_on_step` path; no code duplication
- New public typedef: `tiny_bclibc_StreamCb` — `int32_t (*)(const TINY_BCLIBC_TrajectoryData *, void *)`
- **natmod**: `tiny_bclibc.integrate_stream(shot_buf, req_buf, callback)` — Python callable receives one 16-tuple per point; return truthy to stop; returns `(total_count, stop_reason)`
- `test_bclibc.py`, `examples/tiny_bclibc_natmod_test_2core.py`: tests for both collect-all and early-stop cases

#### `MPY_DIR` default and documentation
- `natmod/Makefile`: `MPY_DIR ?= micropython` — documents the local-symlink convention
- `README.md`: updated MicroPython source setup section to use `git clone / git checkout v1.28.0` instead of a tarball download

#### Drag tables extracted to separate header
- `src/drag_tables.h`: G1 and G7 built-in drag tables extracted from `bclibc_mp.c` into a standalone header with include guard

### Fixed

- `src/tiny_bclibc_mp.c`: added `_RAISE_BCLIBC_ERROR` compatibility macro.
  `dynruntime.h` (natmod) defines `mp_raise_msg(type, const char *)` while the standard
  runtime (usermod) takes `mp_rom_error_text_t`; the macro dispatches to
  `mp_raise_msg_varg(&mp_type_ValueError, MP_ERROR_TEXT("%s"), msg)` in usermod mode.
- `src/tiny_bclibc_mp.c`: removed explicit `(double)` cast from
  `mp_obj_new_float()` calls. On single-precision builds `mp_float_t = float`; passing a
  `double` triggered `-Werror=float-conversion` on armv7m (QEMU MPS2_AN385 build).
- `usermod/micropython.cmake`: fixed include path for `version.h`.
  Was `-I${_USERMOD_DIR}/generated` — caused a double `generated/generated/bclibc_mp/version.h`
  lookup. Corrected to `-I${_USERMOD_DIR}` to match `micropython.mk` behaviour.
- `natmod/Makefile`: added `vpath %.c $(SRC_DIR)` so object files land in
  `$(BUILD)/tiny_bclibc_mp.o` (arch-specific) instead of the shared
  `$(BUILD)/src/tiny_bclibc_mp.o`, which caused "incompatible arch" link errors when
  building x64 after x86 (or vice versa).
- `natmod/Makefile`: each unix-port target now passes an absolute
  `BUILD=<path>/<target>` so output directories are isolated (`build/x64/`,
  `build/x86/`, …) instead of all sharing `ports/unix/build-standard/`.

### Changed

- `src/tiny_bclibc.py` refactored as a thin zero-copy wrapper: `Shot`, `Request`, `Wind`, `Config` constructors return namedtuples (`_Shot(buf, s, holder)`, `_Request(buf, s, traj)`) backed by `uctypes` structs; field access goes directly through `._s` without copying
- `natmod/ci/run_qemu.py` now injects both `_tiny_bclibc.mpy` (native) and `tiny_bclibc.mpy` (bytecode wrapper) from RAM via a custom dual-VFS, so QEMU tests run without filesystem access on the emulated target
- `natmod/Makefile` exposes named targets (`x64`, `x64sp`, `x86`, `x86sp`, `rp2040`, `armv7m`, `rp2350`, `stm32f4`, `stm32h7`, `stm32h7dp`, `esp32`, `esp32s3`, `esp32c3`, `rv64`) in addition to raw `ARCH=…` variables; output artifacts placed in `build/<arch>_<sp|dp>/`
- `.github/workflows/natmod.yml`: build steps use named Makefile targets; artifact names follow the `tiny-bclibc-<arch>_<sp|dp>` scheme

## [1.1.3] - 2026-06-22

### Fixed
- `tiny_bclibc`: `TINY_BCLIBC_FAST_ZERO_FIND` returned wrong zero angle (~0.078° instead of ~0.143° for a 300 m zero).
  Root cause: `acc = 0.01` (a height tolerance in feet) was also used for the Ridder's angle-bracket
  convergence checks (`|next_angle − mid_angle|` and `|high_angle − low_angle|`).  With `acc = 0.01 rad =
  0.573°`, the bracket triggered premature convergence before the true zero angle (~0.0025 rad) was reached.
  Fix: introduce a separate `angle_tol = 1e-5 rad` for the angle-difference checks; `acc` now governs only
  height-error convergence (`|f_mid|`, `|f_next|`) as intended.
- `bclibc` (C++ engine): same units mismatch in `find_zero_angle` — `cZeroFindingAccuracy` (height in ft) was
  used for Ridder's angle-bracket convergence.  Introduced `kRiddersAngleTol = 1e-5 rad` to decouple them.
  No observable regression at the default accuracy (`0.001`), but protects against incorrect results if a
  larger accuracy value is supplied.
- `test_bclibc.py` now asserts `find_zero_angle` returns within 1e-4 rad of the reference value
  (0.002502 rad = 0.1434° for G7 BC=0.310, 168 gr, 2750 fps, 1.5 in sight, 300 m zero).
  The test exits with a non-zero code when any assertion fails, making CI catch value regressions.

### Added

#### Experimental status
- `tiny_bclibc` (C99 engine) and this repository and `tiny_bclibc` are now explicitly marked **experimental**
  in all `README.md` files (`tiny_bclibc/README.md`, `README.md`, root
  `README.md`). APIs, binary layout, and build system may change without notice until
  the features are stabilised.

#### Float32 vs Float64 precision comparison (natmod)
- Added `precision_run.py` (MicroPython worker) and `precision_compare.py` (CPython runner)
  to `` for measuring accumulated trajectory deviation between the
  `float32` (`-DTINY_BCLIBC_USE_FLOAT`) and `float64` natmod builds.
- Test conditions: G7, BC=0.310, 168 gr, mv=2750 fps, T=15°C, P=1013.25 hPa, RH=0.5,
  0–3000 m, output step=25 m (120 sample points), MicroPython v1.26 unix x64.
  `range_step_ft` is the output sampling step only; internal RK4 sub-step is controlled
  independently by `step_multiplier` (default 0.5).
- Results (f32 − f64, double as reference):
  - Max vertical drop deviation: **0.108 cm** at 2975 m
  - Max velocity deviation: **0.0015 fps** (0.0005 m/s)
  - Max Mach deviation: **1.32 × 10⁻⁶**
  - `find_zero_angle` (300 m zero): **5 × 10⁻¹⁰ rad** (< 0.001 mrad)
  - Float32 is sufficient for all supported MCU targets over distances up to 3000 m.
- Documentation with full methodology added to `README.md`,
  `tiny_bclibc/README.md`, and root `README.md`.

#### `tiny_bclibc` — Pure C99 ballistics engine
- New `tiny_bclibc/` subtree: header-only C99 port of the ballistics engine
  - `real_t` = `double` by default; `float` with `-DTINY_BCLIBC_USE_FLOAT`
  - Three usage modes: header-only (`static inline`), shared library, static library via single TU `src/tiny_bclibc_impl.c`
  - Public API: `tiny_bclibc_build_shot_props`, `tiny_bclibc_integrate`, `tiny_bclibc_integrate_at`, `tiny_bclibc_find_zero_angle`, `tiny_bclibc_find_apex`, `tiny_bclibc_find_max_range`, `tiny_bclibc_last_error`
  - CIPM-2007 atmosphere, PCHIP drag curves, Coriolis, spin drift, Ridder zero-finding, RK4 integration
  - Bare-metal / RTOS compatible: `TINY_BCLIBC_NO_THREAD_LOCAL`, `TINY_BCLIBC_NO_ERR_BUF`
  - CMake package with `tiny_bclibc::headers` / `tiny_bclibc::shared` / `tiny_bclibc::static` targets
  - Identity test suite (`tests/test_identity.cpp`) verifying numerical agreement with the C++ engine

#### `natmod/` — MicroPython native module
- New `` subtree: `.mpy` native module wrapping `tiny_bclibc`
  - Supports 11 architectures: x64, x86, armv6m, armv7m, armv7emsp, armv7emdp, xtensa, xtensawin, rv32imc, rv64imc (single and double precision variants)
  - Bundled math: `libm_dbl` (musl-derived, x64/x86 double), fdlibm (x64/x86 single, RISC-V); ARM/Xtensa uses newlib via `LINK_RUNTIME`
  - `math_shim.c`: `sincos`/`sincosf` shim for GCC `-O2` merge optimisation
  - `mem_shim.c`: `memset`/`memcpy` shim for bare-metal targets
  - `math_shadow/math.h`: intercepts glibc `<math.h>` to prevent `__sin`/`__cos` signature conflict with musl libm_dbl
  - `tiny_bclibc_types.py`: `Shot`, `Wind`, `Config`, `Request` data classes with `pack()`/`unpack()`
  - `test_bclibc.py`: full test suite (integrate, find_zero_angle, find_apex, integrate_at, RAM test)
  - `tests/test_ffi.py`: mirror test suite using MicroPython `ffi` module against `libtiny_bclibc.so` — works on any unix port architecture (aarch64, mipsel, …) without a native module
  - `ci/run_qemu.py`: QEMU pty bridge for running natmod tests on emulated MCU targets; supports `--machine` and `--qemu-extra` for any QEMU ARM board
- CI workflow `.github/workflows/natmod.yml`:
  - Builds all arch/precision matrix in parallel
  - Tests on x64 and x86 unix port (both precisions)
  - Tests on QEMU Cortex-M3 (`MPS2_AN385` / armv7m)
  - `workflow_dispatch` trigger with `mpy_tag` input to test against any MicroPython release
- `TINY_BCLIBC_FAST_ZERO_FIND` compile-time flag for `find_zero_angle` on soft-float MCUs (Cortex-M0+, RISC-V without FPU):
  - GSS bracket search uses 8× coarser RK4 step — reduces steps per trajectory ~8×
  - GSS convergence threshold relaxed to `1e-2 rad` (~13 iterations vs ~25) — halves trajectory count
  - Ridder's height-error tolerance `acc` relaxed to `0.01 ft` (3 mm) — within `float` precision floor; angle-bracket convergence uses a separate `1e-5 rad` constant, unchanged
  - Final angle is computed by Ridder's at full `calc_step`; output accuracy is unchanged
  - Enabled automatically by natmod `Makefile` when `USE_FLOAT=1`; independent of `TINY_BCLIBC_USE_FLOAT`
- `natmod/RISC-V_picolibc.md`: documents two `mpy_ld.py` bugs triggered by picolibc on RISC-V and the patch in `natmod/patches/micropython/mpy_ld_srodata.patch`
- `src/sincosf_shim.md`: documents why `src/math_shim.c` is compiled only for x64/x86

### Changed
- `README.md`: added repository structure overview; sections for `tiny_bclibc` and the MicroPython module
- Updated `Makefile`, `CMakeLists`, `build-libs` to be consistent and better structured
- natmod `math_shim.c` (`sincosf` shim) removed from RISC-V build — GCC does not generate `sincosf` calls on ARM/RISC-V with the flags used; saves 68 B of flash
- natmod armv6m QEMU test (`MICROBIT` board) removed — MICROBIT firmware does not support loading native `.mpy` for Cortex-M0; build verification in the `build` job is sufficient


[Unreleased]: https://github.com/ballistics-lab/micropython-bclibc/compare/v1.1.3...HEAD
[1.1.3]: https://github.com/ballistics-lab/bclibc/compare/v1.1.2...v1.1.3
