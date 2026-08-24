# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### `usermod.yml` — Windows x86 / x64 / arm64, built and tested natively

A new `build-test-windows` matrix job builds `ports/windows` with
`USER_C_MODULES` under MSYS2 (MINGW32 for x86, MINGW64 for x64, CLANGARM64 for
arm64) and runs `tests/test_bclibc.py` on the machine that built it — x86 and x64
on `windows-latest` (WOW64 runs the 32-bit exe with no emulation layer), arm64 on
`windows-11-arm`. This is coverage `natmod.yml` cannot provide even in principle:
`ports/windows/mpconfigport.h` sets `MICROPY_EMIT_X64 (0)` and
`py/persistentcode.c` gates `.mpy` native-code loading on
`MICROPY_EMIT_MACHINE_CODE`, so a natmod `.mpy` has nothing to load into on this
port whatever ARCH it was built for.

The recipe (and in particular the four CLANGARM64 overrides — `LDFLAGS_ARCH`
because lld rejects `--cref`, `COMPILER_TARGET` because the gcc-compat wrapper's
`-dumpmachine` doesn't contain "mingw", `STRIP=""`/`SIZE="true"` because that
toolchain ships neither binary) is transplanted from `o-murphy/micropython-wasm3`
and `o-murphy/a7p`, which run this exact combination green. The arm64 row also
passes `CFLAGS_EXTRA=-Wno-error`, because MicroPython's *own* `py/binary.c` and
`shared/runtime/gchelper_generic.c` do not survive the port's gcc-tuned `-Werror`
warning set under clang. Nothing of this repo's is exempted by that: the x86/x64
rows keep `-Werror`, and `src/tiny_bclibc_mp.c` plus the `bclibc` sources were
separately confirmed to compile clean under the port's exact set
(`-Wall -Wpointer-arith -Wdouble-promotion -Werror`, double precision).

### Changed

#### `usermod.yml` — unix and Windows builds now delegate to shared actions

`build-test-unix` and `build-test-windows` no longer carry their own
apt/cross-compile/deplibs/MSYS2 recipe inline — both now call
`build-usermod-unix` and `build-usermod-windows` from
[`ballistics-lab/micropython-native-ci`](https://github.com/ballistics-lab/micropython-native-ci),
the same repo `natmod.yml`'s own per-arch dispatch already used. The unix
action already existed there but had never actually been wired up from any
consuming repo; the Windows one is new, extracted from this exact recipe
(including the four CLANGARM64 overrides). No behavior change: matrix
arches, runners, `MP_BCLIBC_PRECISION=double`, and every build path stay
exactly what they were — this is CI plumbing catching up to an action that
already existed, not a new capability.

#### `usermod.yml` — wasm build now delegates to a shared action too

`build-test-wasm` no longer carries its own inline emsdk-install/build
recipe — it now calls `build-usermod-webassembly` from
[`ballistics-lab/micropython-native-ci`](https://github.com/ballistics-lab/micropython-native-ci),
same as the unix/Windows jobs already did. The job also switched its
checkout from `clone-micropython` (`submodules: lib/micropython-lib`) to
`fetch-micropython`: `o-murphy/micropython-wasm3`'s own webassembly job
proved, green, on the exact combined-manifest change below, that the
release tarball already vendors what the `pyscript` variant's default
manifest needs — the submodule clone was carried over from this job's
original Docker-based recipe and was never actually load-bearing. The
"Write combined FROZEN_MANIFEST" step (see Fixed, below) stays
caller-side, same as every other consumer of this action.

#### `usermod.yml` — rp2040 checkout simplified to fetch-micropython

`build-test-rp2040` no longer checks out MicroPython via `clone-micropython`
with an explicit submodule list plus `pico_sdk_submodules: "true"` — plain
`fetch-micropython` now suffices. The earlier "Cannot find source file:
.../lib/mbedtls/library/aes.c" failure that justified the original
submodule list was against an *incomplete* `clone-micropython` `submodules:`
value, not evidence a git clone was ever required — the release tarball
already vendors every `lib/` this port's `CMakeLists.txt` needs.
`pico_sdk_submodules` was never load-bearing either:
`ports/rp2/CMakeLists.txt` explicitly redirects
`PICO_TINYUSB_PATH`/`PICO_LWIP_PATH`/`PICO_BTSTACK_PATH`/
`PICO_CYW43_DRIVER_PATH` at `${MICROPY_DIR}/lib/<name>` (MicroPython's own
top-level submodules) rather than pico-sdk's own nested vendored copies, so
pico-sdk's internal submodule tree is never actually touched by this build.
`o-murphy/micropython-wasm3`'s own rp2 row proved this, green, on the same
`BOARD=RPI_PICO` with plain `fetch-micropython` and no submodule handling
at all.

#### `usermod.yml` — rp2040 build now delegates to a shared action too

`build-test-rp2040` no longer carries its own inline toolchain-install/
mpy-cross/port-build recipe — it now calls `build-usermod-rp2040` from
[`ballistics-lab/micropython-native-ci`](https://github.com/ballistics-lab/micropython-native-ci),
same as the unix/Windows/wasm jobs above. No behavior change: `board`,
`user_c_modules` and `frozen_manifest` all already matched the action's
own defaults exactly, so this job's call needs no input overrides at all.

#### `usermod.yml` — qemu-armv7m build now delegates to a shared action too

`build-test-qemu-armv7m` no longer carries its own inline arm-none-eabi
toolchain-install/mpy-cross/port-build recipe — it now calls
`build-usermod-qemu-armv7m` from
[`ballistics-lab/micropython-native-ci`](https://github.com/ballistics-lab/micropython-native-ci),
same as the unix/Windows/wasm/rp2040 jobs above. `qemu-system-arm` and
`pyserial` stay caller-side: neither is a build dependency (QEMU only
runs the resulting firmware), same split the rp2040 action already uses
for the rp2040py emulator. `build_dir: build-MPS2_AN385` keeps the
resulting path exactly where the Run tests step already expects it — no
`BUILD=` override in the plain `make` invocation this replaces either.

#### `natmod.yml` — ARM natmods now run on real ARM silicon, not only emulators

A new `test-arm-linux` matrix job on `ubuntu-24.04-arm` builds a 32-bit armhf
`ports/unix` interpreter and loads the `armv7emsp` and `armv7emdp` natmod
`.mpy`s into it, running the full `tests/test_bclibc.py` on each. Until now
every ARM natmod leg was emulated: `armv7m` under `qemu-system-arm`, `armv6m`
under rp2040py.

It works because `py/persistentcode.h` gives a Thumb-2 host with a
double-precision FPU `MPY_FEATURE_ARCH = MP_NATIVE_ARCH_ARMV7EMDP`, and
`MPY_FEATURE_ARCH_TEST` is a *range* (`ARMV6M <= x <= that`), not an equality —
so every ARM natmod ARCH clears the header check on an armhf host. Read back
off the built binary rather than assumed: `sys.implementation._mpy >> 10` is 8.

It covers only two of the four ARM ARCHes because the arch check says nothing
about the **float ABI**. `armv6m` and `armv7m` get no `-mfloat-abi=hard` from
`py/dynruntime.mk`, so their floats arrive in core registers while an armhf
host reads them from VFP registers per AAPCS-VFP. Measured, not predicted:
those `.mpy`s load and then return nonsense — `find_zero_angle` gave `984.252`
rad, the range in feet, instead of `0.002502`. Silently wrong, never a crash,
so those two ARCHes are deliberately excluded and keep their emulator legs.
`armv7emsp` and `armv7emdp` are hard-float and line up, each against a host
built with its own `MICROPY_FLOAT_IMPL` (`-DMICROPY_FLOAT_IMPL=` on the command
line for the single-precision one; `mpconfigvariant_common.h` guards its double
default with `#ifndef`).

This does not replace the QEMU or rp2040py legs. Those exercise the firmware
environment — no OS, the port's own libc, real flash layout. This runs
Cortex-M code inside a Linux process, proving the native module and its
relocations are correct on real ARM silicon, and nothing beyond that.

#### `usermod.yml` — x64/x86 rows, and an ESP32 build

`build-test-unix` gained `x64` and `x86` rows. Both duplicate ARCHes
`natmod.yml` already builds and runs, which this workflow's header explicitly
calls out as not its job — they are here anyway because the two build modes
fail in different ways. A usermod links against the port's own libc and its
globals live in firmware `.bss`; a natmod links against dynruntime and carries
its own. "x64 natmod passes" says nothing about the usermod path on the same
machine, and these are the only rows here where a failure is unambiguously this
repo's code rather than a toolchain or an emulator. `x86` uses
`MICROPY_FORCE_32BIT=1` with `gcc-multilib` and `libffi-dev:i386`, the same
recipe `natmod.yml`'s own x86 leg uses.

A new `build-esp32` job builds `ports/esp32` (`BOARD=ESP32_GENERIC`) with
`USER_C_MODULES` under ESP-IDF v5.5.1 — the version `ports/esp32/README.md`
names as recommended for this MicroPython release. **Build-only**, and not as a
shortcut: there is no esp32 emulator to hand a firmware image to the way
rp2040py takes a `.uf2`. It proves `tiny_bclibc` compiles and links into a real
esp32 firmware under a compiler, libc and config unlike anything else here; it
proves nothing runs.

It is not a duplicate of `natmod.yml`'s `xtensawin` leg despite the shared ISA.
That one builds a `.mpy` against dynruntime and only borrows the compiler out of
esp-idf, deliberately skipping IDF's submodules. A usermod is compiled into the
firmware, so this job clones esp-idf `--recursive`.

Written CI-first rather than verified locally, which is unusual here and worth
recording: `dl.espressif.com` and `components-file.espressif.com` are both
refused by the development environment's egress policy, so neither the toolchain
nor the IDF managed components (`espressif/mdns` always, `espressif/lan867x` for
target esp32) can be fetched there. What is known to work on the runner is
esp-idf's own `install.sh` — `natmod.yml`'s xtensawin leg has been doing exactly
that, green. The open question this job settles is whether the
managed-component fetch and the full port build follow.

#### `usermod.yml` — the aarch64 row is a plain dynamic build again

`build-test-unix-static` is now `build-test-unix`, and `MICROPY_STANDALONE=1
LDFLAGS_EXTRA=-static` applies to the `armhf` and `mipsel` rows only. On those
two it is load-bearing: the arm64 runner carries no armhf glibc and no
`/lib/ld-linux-armhf.so.3`, and `qemu-user` runs mipsel with no sysroot, so a
dynamically linked binary cannot start. `aarch64` has neither problem — it
executes natively on the machine that builds it.

The deployability argument that put it there originally does not hold up:
`release.yml` calls `natmod.yml` alone, so the usermod binary is a CI artifact
and never a release asset, and a static glibc's `dlopen` still needs the
matching shared libraries at run time. Measured rather than inferred:
`ffi.open("libm.so.6")` in a static build works on a machine carrying that
glibc — which is the machine that did not need a static binary — and is exactly
what stops working on the minimal board that did. This repo has an `ffimod/`
route that loads `libtiny_bclibc.so` through `ffi`, so that is not hypothetical.

The row now installs `libffi-dev`/`pkg-config` and links against the system
libffi, matching `o-murphy/micropython-wasm3`'s aarch64 usermod row, which has
always been built that way.

#### `usermod.yml` — armhf moved off qemu-user onto a real AArch32 runner

The `armhf` row of `build-test-unix-static` now runs on `ubuntu-24.04-arm`
instead of `ubuntu-latest`: the arm64 runner cross-builds the 32-bit binary
and then executes it on its own CPU, with no emulator and no binfmt handler
involved. That is measured, not assumed — `o-murphy/micropython-wasm3` carried
a probe job that built a statically linked, freestanding AArch32 binary and
ran it there ("RESULT: AArch32 IS supported on this runner", that repo's
usermod run #18). `mipsel` keeps `qemu-user-static`; GitHub has no mips runner.

The move is also why armhf switched from `arm-linux-gnueabi-` to
`arm-linux-gnueabihf-`. Under qemu the ABI choice was nearly free — the
emulator implements whatever ARMv5 asks for. On real ARMv8 hardware it is not:
`gnueabi` is soft-float and baselines at ARMv5TE, whose SWP/SWPB atomics ARMv8
removed outright, surviving only through the kernel's opt-in
`ARMV8_DEPRECATED` emulation. `gnueabihf` is the toolchain the probe binary was
built with, and it is what this row has always been called. `mipsel` is
untouched.

#### `natmod.yml` / `usermod.yml` — added a `push` trigger

Both workflows now run on `push` as well as `pull_request`, with the same path
filter and no branch restriction, so a plain `git push` to a work branch runs
the matrix without needing an open PR or a `workflow_dispatch` (the latter
requires `actions: write`, which not every actor pushing here has). A branch
that is also the head of an open PR gets both runs: the concurrency group keys
on `github.ref`, which differs between `refs/heads/<branch>` and
`refs/pull/<n>/merge`, so the two do not cancel each other. `release.yml` is
unchanged — it already triggers on `push` of `v*` tags.

#### `natmod.yml` / `usermod.yml` — rp2040py 0.2.4 → 0.3.1

`natmod.yml`'s `mklittlefs` step was failing outright on this branch: rp2040py's
file argument only accepted `.py`/`.js` before 0.2.5, so handing it
`natmod/build/armv6m_sp/tiny_bclibc.mpy` died with *"File must have one of the
following extensions: .py, .js"* (exit 2). 0.2.5 added `.mpy`; 0.3.1 is the
current release and the action's own inputs (`version`, `python_version`) are
unchanged across the range, as are the `mklittlefs -o` and `micropython --image`
command lines both workflows use.

### Removed

#### `usermod/patches/micropython/ports/webassembly/` — dead patches, never applied

Three patches (`0001-main.c-fix-external-call-depth-unused`,
`0002-library.js-fix-interrupt-char-abi`, `0003-api.js-fix-runpython-async`) were
added alongside the first `usermod` wasm target, back when it still built the
default `standard` variant. Nothing ever applied them: there is no `git apply` /
`patch -p` step in `usermod.yml`, `natmod.yml` or `release.yml`, and the wasm job
switched to `VARIANT=pyscript` — which doesn't use `-s ASYNCIFY` and so hits none
of the three bugs. Two of them are moot upstream anyway: `main.c`'s
`external_call_depth` is now guarded by `#if MICROPY_GC_SPLIT_HEAP_AUTO`, and
`library.js`'s `mp_hal_get_interrupt_char` ccall already passes `[], []` on master.
Only the `api.js` `runPython` async fix is still open upstream, and it only matters
for `VARIANT=standard`, which this project does not build — bclibc is pure
computation, no `await`/REPL/stack-switching, so ASYNCIFY buys it nothing but a
bigger, slower `.wasm`. The rationale for `pyscript` and the upstream tracking link
([micropython/micropython#19380](https://github.com/micropython/micropython/issues/19380))
stay documented in `README.md` and in the `build-test-wasm` job comment.

### Fixed

#### `usermod.yml` — the uploaded wasm build was missing `asyncio` and 24 stdlib modules

`build-test-wasm` passed `FROZEN_MANIFEST=usermod/manifest.py` alone.
`usermod/manifest.py`'s own `try`/`except` around
`include("$(PORT_DIR)/boards/manifest.py")` only ever probes that one path,
which doesn't exist for `ports/webassembly` (it has `variants/`, not
`boards/`) — so the `except` silently swallowed it, and the port's real
default, `variants/pyscript/manifest.py`, never got included. That default
provides `asyncio` (backed by a custom JS-runtime scheduler) plus a
`require()` list of 24 stdlib/utility modules (`base64`, `collections`,
`gzip`, `os`, `pathlib`, `unittest`, `zlib`, and others). `tests/test_bclibc.py`
never imports any of them, so the gap never showed up as a test failure —
but the `.mjs`/`.wasm` this job uploads is a real build artifact, not just a
test fixture, and anyone importing `asyncio`/`os`/etc. against it hit a
plain `ImportError`. The job now writes a combined manifest
(`variants/pyscript/manifest.py` + this project's own `usermod/manifest.py`)
and passes that instead, the same pattern `o-murphy/a7p`'s own webassembly
job already uses for this exact port.

## [1.2.1] - 2026-07-28

### Fixed

#### `release.yml` — concurrency group collided with its own `natmod.yml` call

Both workflows used `group: ${{ github.workflow }}-${{ github.ref }}`. Inside a
`workflow_call`ed workflow, `github.workflow` resolves to the *caller's* name, not
the called file's own — so `natmod.yml`, when invoked from `release.yml`, computed
the exact same concurrency group as `release.yml` itself (`release-<ref>`).
`release.yml`'s `cancel-in-progress: false` meant the called workflow could never
enter its own caller's group, and the job never even started (0 jobs, run marked
failure). Switched both to a literal `natmod-`/`release-` prefix instead of the
dynamic `${{ github.workflow }}`, so the two groups can never collide regardless of
which one calls the other.

#### `natmod/Makefile` — `aarch64` was documented but never actually buildable

The `ARCH=` help comment, precision-selection, and math-library-selection blocks
all listed `aarch64` alongside `x64`/`x86`, but `dynruntime.mk` (as of MicroPython
<=v1.28) has no `ARCH=aarch64` branch at all — `make ARCH=aarch64 dist` has always
failed with `architecture 'aarch64' not supported`, regardless of anything in this
project's own Makefile. Removed the dead references; `aarch64` is already covered
separately via `usermod` (links straight into the port's build, no `dynruntime.mk`
involved) and `ffimod` (`libtiny_bclibc.so` via the `ffi` module).

### Added

#### `tools/nmip.py` — bootstrap installer for testing the tagged `package.json` scheme today

A drop-in copy of the micropython-lib#1144 branch's `mip`, installed under a
different name (`nmip`) so it doesn't collide with (or need to replace) the
frozen, unpatched `mip` already on stock firmware. Lets anyone try the per-entry
native-code compatibility tag scheme
([micropython/micropython#19532](https://github.com/micropython/micropython/pull/19532),
[micropython/micropython-lib#1144](https://github.com/micropython/micropython-lib/pull/1144))
against this project's real multi-arch release right now, without rebuilding
firmware, while the upstream PRs are still under review — see the new
"Install a released build via `mip`" section in the README.

### Changed

#### `tools/build_release_assets.py` — `--repo` is now optional; relative URLs by default

Without `--repo`, `package.json`'s `urls` entries are now bare asset filenames
instead of full `https://github.com/...` links. `mip` resolves relative URLs
against wherever it fetched `package.json` from
(`base_url = package_json_url.rpartition("/")[0]` in `_install_json`), and every
asset a GitHub release publishes — `package.json` included — lives under the same
`.../releases/download/<tag>/` path, so this stays correct across forks and repo
renames without needing to know the repo name at all. `release.yml` no longer
passes `--repo`. Pass it explicitly to get the old absolute-URL behavior back.

## [1.2.0] - 2026-07-28

#### natmod now builds a single merged `tiny_bclibc.mpy` (was two files)

`natmod/Makefile` now lists `src/tiny_bclibc.py` in `SRC` alongside the native `.c` sources,
so `dynruntime.mk`'s own merge rule produces one `tiny_bclibc.mpy` per architecture instead
of a separate `_tiny_bclibc.mpy` (native) + `tiny_bclibc.mpy` (bytecode wrapper) pair —
matching the approach already used by [a7p's own natmod build](https://github.com/o-murphy/a7p).
One file is simpler to deploy (`mip install` / copy to device / attach as a release asset).

`src/tiny_bclibc.py` gained a `try: from _tiny_bclibc import ... / except ImportError:`
fallback (mirroring a7p's `_a7p` pattern) to handle the merged build, where there's no
separate `_tiny_bclibc` module to import — the native part's `mpy_init()` already left its
functions and constants as bare globals of this same module. The usermod build (real,
separately-compiled `_tiny_bclibc` module) is unaffected.

CI (`natmod.yml`), `natmod/ci/run_qemu.py`, and `tests/precision_compare.py` updated to the
single-file layout.

#### Precision flag unified across all build systems

The precision selection is now controlled by a **single** environment / make variable:
`MP_BCLIBC_PRECISION=single|double`. This replaces the previous fragmented approach:

- `natmod/Makefile`: `PRECISION` → `MP_BCLIBC_PRECISION`
- `usermod/Makefile`: `TINY_BCLIBC_PRECISION` → `MP_BCLIBC_PRECISION`
- `usermod/micropython.cmake`: `TINY_BCLIBC_DOUBLE_PRECISION` → `MP_BCLIBC_PRECISION`
- `usermod/micropython.mk`: `MP_BCLIBC_PRECISION` kept (already aligned)
- `ffimod/_tiny_bclibc.py`: now uses `MP_BCLIBC_PRECISION` to select correct C struct layout.

All targets now consistently accept `MP_BCLIBC_PRECISION=single` or `=double`; the default
remains `double` on x64/x86 and `single` on MCU architectures. This eliminates the need
to remember different flags for different build modes and makes the user experience
uniform across the entire project.

### Fixed

#### `natmod/Makefile` — `dist` left build junk behind instead of a single `tiny_bclibc.mpy`

`dist`'s cleanup step tried to remove `$(BUILD)/$(MOD).native.mpy` — a filename
`dynruntime.mk` never actually produces. The real intermediate native-only artifact is
`$(BUILD)/$(MOD).mpy`, so `rm -f` silently removed nothing, and every build dir kept its
`.o` files, `.config.h`, and that raw native `.mpy` sitting alongside the real merged
`tiny_bclibc.mpy` output. `dist` now removes the correct file plus `$(SRC_O)`/`$(CONFIG_H)`
(the actual `dynruntime.mk` variables, not hardcoded names) — `build/<arch>_<precision>/`
now contains exactly the one file it's meant to.

#### `src/tiny_bclibc_mp.c` — `-Wdouble-promotion` in wasm_sp (Emscripten/Clang)

Emscripten adds `-Wdouble-promotion` to the compiler flags *after* `CFLAGS_USERMOD`, so
`-Wno-double-promotion` in `micropython.mk` had no effect.  When `real_t=float` the call
`mp_obj_new_float(real_t)` implicitly promotes `float → double` (because `mp_float_t` is
`double` on wasm), which triggered the error in CI.

Fixed in the usermod branch of `tiny_bclibc_mp.c` (mirroring the existing natmod fix):

```c
#undef  mp_obj_new_float
#define mp_obj_new_float(v) mp_obj_new_float_from_d((double)(v))
```

The explicit cast is a no-op for `real_t=double`; it silences the warning for
`real_t=float` without disabling the diagnostic globally.

#### `usermod/Makefile` — Docker targets failed with `:ro` volume mounts

`mpy-cross` (`make -C /mpy/mpy-cross`) writes its build output into the source tree,
and `libtoolize --copy` writes into `lib/libffi/m4/`.  Both failed when `/mpy` was
mounted read-only.

Fixed by copying the entire MicroPython tree to a writable `/mpy_build` at container
startup (`cp -r /mpy /mpy_build`) and running all in-container commands against
`/mpy_build`.  Applied to all six Docker-based targets (x86, x86sp, armhf, armhfsp,
mipsel, mipselsp, wasm, wasmsp, qemu-armv7m).

### Added

#### New `release.yml` workflow — automated GitHub Releases for natmod

Pushing a `v*` tag now builds every natmod arch (by calling `natmod.yml` as a reusable
workflow via its new `workflow_call` trigger, instead of duplicating the 10-arch matrix)
and publishes a GitHub Release with:

- One `tiny_bclibc_<arch>.native.mpy` asset per architecture.
- A `package.json` that `mip`/`mpremote mip install` can install directly, using the
  optional per-entry native-code compatibility tag schema proposed upstream
  ([micropython/micropython#19532](https://github.com/micropython/micropython/pull/19532),
  [micropython/micropython-lib#1144](https://github.com/micropython/micropython-lib/pull/1144)):
  `["tiny_bclibc.mpy", "<asset url>", <tag>]` per arch, so a given board only pulls the
  variant that matches it.

`tools/build_release_assets.py` reads each built `.mpy`'s own on-disk header (version,
sub-version, arch, and — if present — the RISC-V extension-flags vuint) to compute that
tag directly, mirroring the exact validation `mp_raw_code_load()` does in
`py/persistentcode.c` — no dependency on build-directory naming, and no running
MicroPython interpreter needed. Standalone script, stdlib only.

The assembled assets + `package.json` are also uploaded as a `tiny-bclibc-release-<tag>`
workflow artifact, independent of whether the GitHub Release itself gets created.

#### `usermod/` — RP2040 emulator testing via rp2040js

CI now runs `test_bclibc.py` on the actual RP2040 firmware (single-precision) in the
[wokwi/rp2040js](https://github.com/wokwi/rp2040js) JavaScript emulator — no physical
hardware required.

- `usermod/manifest_test.py`: CI-only frozen manifest.  Extends `manifest.py` with
  `tests/test_bclibc.py` so that `import test_bclibc` works from the REPL.  Release
  firmware (`rp2040_sp`, `rp2040_dp`) is unaffected.
- `usermod/Makefile` `rp2040test` target: builds RP2040 single-precision firmware with
  `manifest_test.py` into `build/rp2040_sp_test/firmware.uf2`.  Separate `BUILD` dir
  keeps release and test artifacts independent.
- `usermod/ci/micropython-run.ts`: rp2040js test runner.  Options: `--image <uf2>`,
  `--exec <python>` (single-line injection), `--run <file>` (rate-limited file send via
  `exec("""...""")`), `--expect-text <text>` (exit 0 on match), `--timeout <sec>`.
  Exits 1 if the captured output contains `"FAILED"` (matches `"N test(s) FAILED"` from
  the test suite).
- `.github/workflows/usermod.yml` `build-rp2040` job (renamed to "build + test"):
  added `make rp2040test`, rp2040js clone + patch step, and test step:
  `npx tsx demo/micropython-run.ts --exec "import test_bclibc" --timeout 120`.

#### `usermod/` — WebAssembly target (`wasm` / `wasmsp`)

- New `wasm` / `wasmsp` Makefile targets build MicroPython `ports/webassembly` with `USER_C_MODULES` + `FROZEN_MANIFEST` baked in via Emscripten.
- Runs entirely inside Docker (`emscripten/emsdk:latest`); no Emscripten toolchain required on the host.
- Outputs `micropython.mjs` + `micropython.wasm` in `usermod/build/wasm_{dp,sp}/`.
- `node` tests execute inside the container immediately after the build (same pattern as `qemu-armv7m`).
- `usermod/Dockerfile.webassembly`: `emscripten/emsdk:latest` base image (`git` + `python3` added on top).
- `.github/workflows/usermod.yml` `build-test-wasm` job: clones MicroPython with `lib/micropython-lib`, builds `wasm` + `wasmsp` via Docker, uploads `micropython.mjs` + `micropython.wasm` for both precisions as the `tiny-bclibc-usermod-wasm` artifact.

### Changed

####
- Pin `bclibc` to `v1.1.7`

#### `.github/` — `fetch-micropython` and `clone-micropython` composite actions

Repeated inline steps extracted into reusable composite actions:

- `.github/actions/fetch-micropython/action.yml` — downloads and extracts a MicroPython release tarball, exports `MPY_DIR` into `$GITHUB_ENV`. Input: `mpy_tag`. Replaced 9 identical inline steps across `natmod.yml` (4) and `usermod.yml` (5).
- `.github/actions/clone-micropython/action.yml` — shallow-clones MicroPython and initialises the specified submodules, exports `MPY_DIR`. Inputs: `mpy_tag`, `submodules` (space-separated list), `pico_sdk_submodules` (`'true'` to also run `git -C lib/pico-sdk submodule update --init`). Replaced 3 clone variants in `usermod.yml`.

#### `usermod/` — x86, armhf, armv7m builds moved inside Docker

All targets that require standalone libffi (`autoreconf` + `deplibs`) or a bare-metal
toolchain are now fully self-contained inside pinned Ubuntu 22.04 Docker images.
This eliminates `autotools` version sensitivity (Ubuntu 24.04+ breaks libffi's
`configure.ac` from MicroPython v1.28) and removes all host-side toolchain requirements
beyond Docker itself.

| Target                | Dockerfile          | What runs inside                                  |
| --------------------- | ------------------- | ------------------------------------------------- |
| `x86` / `x86sp`       | `Dockerfile.x86`    | mpy-cross, autoreconf, deplibs, main build        |
| `armhf` / `armhfsp`   | `Dockerfile.armhf`  | mpy-cross, autoreconf, deplibs, main build, strip |
| `qemu-armv7m`         | `Dockerfile.armv7m` | mpy-cross, firmware build, QEMU test              |
| `mipsel` / `mipselsp` | `Dockerfile.mipsel` | mpy-cross, submodules, deplibs, main build, strip |

- `usermod/Dockerfile.x86`: Ubuntu 22.04 + `gcc-multilib g++-multilib` + autotools.
- `usermod/Dockerfile.armhf`: Ubuntu 22.04 + `gcc-arm-linux-gnueabihf` + autotools.
- `usermod/Dockerfile.armv7m`: Ubuntu 22.04 + `gcc-arm-none-eabi libnewlib-arm-none-eabi qemu-system-arm python3-serial`.
- New `make qemu-armv7m` target: runs the full Cortex-M3 build **and** test inside Docker via `usermod/ci/run_qemu.py`.
- `apt-deps` Makefile target removed (superseded by Docker).
- `.github/workflows/usermod.yml`:
  - `build-test-x86`: removed `Install deps` and `Build mpy-cross` steps; single `make x86 / make x86sp` step.
  - `build-test-armhf`: runner changed `ubuntu-22.04` → `ubuntu-26.04-arm`; removed `Install cross-compiler`, `Build mpy-cross`, `Build standalone libffi` steps; build step is now `make armhf`; only `Install QEMU` + test remain on the host.
  - `build-test-qemu-armv7m`: runner changed `ubuntu-latest` → `ubuntu-26.04-arm`; all 5 steps (toolchain install, mpy-cross, version header, firmware build, test) replaced with a single `make qemu-armv7m`.

#### `usermod/Makefile` — mipsel builds inside Docker
- `mipsel` / `mipselsp` targets now run inside a Docker container (Ubuntu 22.04 + `gcc-mipsel-linux-gnu`) instead of requiring the toolchain on the host. Docker image is built automatically on first run from `usermod/Dockerfile.mipsel` and reused on subsequent builds.
- `usermod/Dockerfile.mipsel`: Ubuntu 22.04, `libtool-bin` included for `autoreconf`/`deplibs`; no host toolchain install needed for mipsel.
- Build sequence inside container: `mpy-cross` → `submodules` → `deplibs` → main build. Output lands on the host at `usermod/build/mipsel_{dp,sp}/micropython` via Docker volume mount.
- `.github/workflows/usermod.yml` `build-mipsel` job simplified: toolchain install, mpy-cross, and deplibs steps removed; replaced with a single `make mipsel MPY_DIR=...` step.

---

### Added (initial extraction from bclibc)

#### `usermod/` — MicroPython USER_C_MODULE (baked-in firmware module)

A second integration mode alongside natmod: `tiny_bclibc` compiled directly into the
MicroPython firmware via `USER_C_MODULES`. No `.mpy` file to deploy — the module is
available as a built-in at every boot.

- `usermod/Makefile`: cross-compile targets for all supported platforms:

  | Target                  | Precision       | Host/cross              | Notes                               |
  | ----------------------- | --------------- | ----------------------- | ----------------------------------- |
  | `x64` / `x64sp`         | double / single | native x64              | unix port, dynamic                  |
  | `x86` / `x86sp`         | double / single | 32-bit                  | unix port, standalone static        |
  | `aarch64` / `aarch64sp` | double / single | `aarch64-linux-gnu-`    | unix port, standalone static        |
  | `armhf` / `armhfsp`     | double / single | `arm-linux-gnueabihf-`  | unix port, standalone static        |
  | `mipsel` / `mipselsp`   | double / single | `mipsel-linux-gnu-`     | unix port, coverage variant, static |
  | `rp2040`                | single          | cmake (`arm-none-eabi`) | RP2040 firmware                     |
  | `rp2040dp`              | double          | cmake (`arm-none-eabi`) | RP2040 firmware, DP FPU             |

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

  | Job                      | Runner             | Approach                                                       |
  | ------------------------ | ------------------ | -------------------------------------------------------------- |
  | `build-armhf`            | ubuntu-latest      | Cross-compile, `MICROPY_STANDALONE=1 -static`, artifact upload |
  | `test-armhf`             | ubuntu-latest      | Download artifact, run under `qemu-arm`                        |
  | `build-mipsel`           | ubuntu-latest      | Cross-compile (coverage variant), static, artifact upload      |
  | `test-mipsel`            | ubuntu-latest      | Download artifact, run under `qemu-mipsel`                     |
  | `build-test-aarch64`     | ubuntu-24.04-arm64 | Native build + test + artifact upload                          |
  | `build-test-qemu-armv7m` | ubuntu-latest      | Build MPS2_AN385 QEMU firmware + test via `run_qemu.py`        |

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


[Unreleased]: https://github.com/ballistics-lab/micropython-bclibc/compare/v1.2.1...HEAD
[1.2.1]: https://github.com/ballistics-lab/micropython-bclibc/compare/v1.2.0...v1.2.1
[1.2.0]: https://github.com/ballistics-lab/micropython-bclibc/compare/v1.1.3...v1.2.0
[1.1.3]: https://github.com/ballistics-lab/bclibc/compare/v1.1.2...v1.1.3
