# usermod/Makefile
# Build MicroPython with tiny_bclibc baked in as a USER_C_MODULE.
#
#   make x64        — x64 double     → build/x64_dp/micropython
#   make x64sp      — x64 single     → build/x64_sp/micropython
#   make x86        — x86 double     → build/x86_dp/micropython       (Docker)
#   make x86sp      — x86 single     → build/x86_sp/micropython       (Docker)
#   make aarch64    — AArch64 double  → build/aarch64_dp/micropython
#   make aarch64sp  — AArch64 single  → build/aarch64_sp/micropython
#   make armhf      — ARMv7hf double  → build/armhf_dp/micropython   (Docker)
#   make armhfsp    — ARMv7hf single  → build/armhf_sp/micropython   (Docker)
#   make mipsel     — MIPS LE double  → build/mipsel_dp/micropython  (Docker)
#   make mipselsp   — MIPS LE single  → build/mipsel_sp/micropython  (Docker)
#   make wasm       — WebAssembly double → build/wasm_dp/micropython.{mjs,wasm}  (Docker)
#   make wasmsp     — WebAssembly single → build/wasm_sp/micropython.{mjs,wasm}  (Docker)
#   make rp2040     — RP2040 single   → build/rp2040_sp/firmware.{elf,uf2}
#   make rp2040dp   — RP2040 double   → build/rp2040_dp/firmware.{elf,uf2}
#   make rp2040test — RP2040 single + frozen tests → build/rp2040_sp_test/firmware.uf2  (CI only)
#
# Set MPY_DIR= to point at a MicroPython source tree (required for all targets).

MPY_DIR      ?= micropython
THIS_DIR     := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
# py.mk scans $(USER_C_MODULES)/*/micropython.mk — repo root lets it find usermod/micropython.mk
MAKE_MODULES := $(abspath ../)
CMAKE_MODULE := $(THIS_DIR)/micropython.cmake
MANIFEST     := $(THIS_DIR)/manifest.py
VERSION_H    := $(THIS_DIR)/generated/bclibc_mp/version.h
VERSION_IN   := $(abspath ../version.h.in)
BCLIBC_ROOT  := $(abspath $(THIS_DIR)/..)
_BUILD       := $(THIS_DIR)/build

# x86, armhf, armv7m, and mipsel targets run inside Docker (Ubuntu 22.04) — MPY_DIR resolved to absolute path
DOCKER_IMAGE       := micropython-mipsel-builder
DOCKER_IMAGE_X86   := micropython-x86-builder
DOCKER_IMAGE_ARMHF := micropython-armhf-builder
DOCKER_IMAGE_ARMV7M := micropython-armv7m-builder
DOCKER_IMAGE_WASM  := micropython-wasm-builder
_MPY_ABS          := $(abspath $(MPY_DIR))
_REPO_ABS         := $(abspath $(THIS_DIR)/..)
HOST_UID          := $(shell id -u)
HOST_GID          := $(shell id -g)

.PHONY: all submodules x64 x64sp x86 x86sp \
        aarch64 aarch64sp armhf armhfsp mipsel mipselsp \
        qemu-armv7m wasm wasmsp rp2040 rp2040dp rp2040test generated clean help

all: x64

help:
	@echo "Targets:                                         Output"
	@echo "  x64 / x64sp          — x64 host (dp / sp)     build/x64_{dp,sp}/micropython"
	@echo "  x86 / x86sp          — x86 32-bit (Docker)      build/x86_{dp,sp}/micropython"
	@echo "  aarch64 / aarch64sp  — AArch64 cross           build/aarch64_{dp,sp}/micropython"
	@echo "  armhf / armhfsp      — ARMv7hf (Docker)        build/armhf_{dp,sp}/micropython"
	@echo "  qemu-armv7m          — Cortex-M3 QEMU (Docker, build+test)"
	@echo "  mipsel / mipselsp    — MIPS LE (Docker)        build/mipsel_{dp,sp}/micropython"
	@echo "  wasm / wasmsp        — WebAssembly (Docker)    build/wasm_{dp,sp}/micropython.{mjs,wasm}"
	@echo "  rp2040 / rp2040dp    — RP2040 Pico (sp / dp)  build/rp2040_{sp,dp}/firmware.uf2"
	@echo "Set MPY_DIR= to point at a MicroPython source tree"
	@echo "  submodules           — init git submodules"

# ── Version header ─────────────────────────────────────────────────────────────
$(VERSION_H): $(VERSION_IN)
	@mkdir -p $(dir $@)
	$(eval _TAG := $(shell git -C "$(BCLIBC_ROOT)" describe --tags --always 2>/dev/null || echo v0.0.0))
	$(eval _MAJ := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?([0-9]+)\..*/\1/;t;s/.*/0/'))
	$(eval _MIN := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?[0-9]+\.([0-9]+)\..*/\1/;t;s/.*/0/'))
	$(eval _PAT := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?[0-9]+\.[0-9]+\.([0-9]+).*/\1/;t;s/.*/0/'))
	$(eval _VER := $(shell printf '%s' '$(_TAG)' | sed 's/^v//'))
	@sed -e 's/@MP_BCLIBC_VERSION_MAJOR@/$(_MAJ)/g' \
	     -e 's/@MP_BCLIBC_VERSION_MINOR@/$(_MIN)/g' \
	     -e 's/@MP_BCLIBC_VERSION_PATCH@/$(_PAT)/g' \
	     -e 's/@MP_BCLIBC_VERSION@/$(_VER)/g' \
	     $(VERSION_IN) > $@
	@echo "  GEN   $@"

generated: $(VERSION_H)

# ── Unix port macro (make-based) ──────────────────────────────────────────────
# $(1) = extra make vars (e.g. MICROPY_FORCE_32BIT=1)
# $(2) = precision: single | double
# $(3) = output subdirectory, e.g. x64_dp, armhf_sp
define unix_build
	$(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=standard \
	    BUILD="$(_BUILD)/$(3)" \
	    $(1) \
	    USER_C_MODULES="$(MAKE_MODULES)" \
	    FROZEN_MANIFEST="$(MANIFEST)" \
	    MP_BCLIBC_PRECISION=$(2)
endef

# ── ARMhf — builds inside Docker (Ubuntu 22.04 + gcc-arm-linux-gnueabihf) ─────
# $(1) = output subdir (armhf_dp / armhf_sp), $(2) = MP_BCLIBC_PRECISION value
define armhf_docker_build
	docker image inspect $(DOCKER_IMAGE_ARMHF) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE_ARMHF) -f $(THIS_DIR)/Dockerfile.armhf $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE_ARMHF) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); \
	        cp -r /mpy /mpy_build; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        test -f /mpy_build/lib/libffi/configure || \
	            ( cd /mpy_build/lib/libffi && libtoolize --copy --force && autoreconf -fvi ); \
	        make -j$$J -C /mpy_build/ports/unix VARIANT=standard \
	            CROSS_COMPILE=arm-linux-gnueabihf- \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/$(1) \
	            deplibs; \
	        make -j$$J -C /mpy_build/ports/unix VARIANT=standard \
	            CROSS_COMPILE=arm-linux-gnueabihf- \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/$(1) \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=$(2); \
	        arm-linux-gnueabihf-strip -s /workspace/usermod/build/$(1)/micropython; \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/build && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/build/$(1)'
endef

submodules:
	git submodule update --init --recursive

# ── x64 ───────────────────────────────────────────────────────────────────────
x64: $(VERSION_H)
	$(call unix_build,,double,x64_dp)

x64sp: $(VERSION_H)
	$(call unix_build,,single,x64_sp)

# ── x86 — builds inside Docker (Ubuntu 22.04 + gcc-multilib) ─────────────────
# autoreconf on ubuntu-latest (24.04+) breaks libffi configure.ac from MPY v1.28;
# Docker pins the toolchain to a known-good Ubuntu 22.04 environment.
# $(1) = precision suffix (x86_dp / x86_sp), $(2) = MP_BCLIBC_PRECISION value
define x86_docker_build
	docker image inspect $(DOCKER_IMAGE_X86) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE_X86) -f $(THIS_DIR)/Dockerfile.x86 $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE_X86) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); \
	        cp -r /mpy /mpy_build; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        test -f /mpy_build/lib/libffi/configure || \
	            ( cd /mpy_build/lib/libffi && libtoolize --copy --force && autoreconf -fvi ); \
	        make -j$$J -C /mpy_build/ports/unix VARIANT=standard \
	            MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/$(1) \
	            deplibs; \
	        make -j$$J -C /mpy_build/ports/unix VARIANT=standard \
	            MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/$(1) \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=$(2); \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/build && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/build/$(1)'
endef

x86: $(VERSION_H)
	$(call x86_docker_build,x86_dp,double)

x86sp: $(VERSION_H)
	$(call x86_docker_build,x86_sp,single)

# ── AArch64 (cross) ───────────────────────────────────────────────────────────
aarch64: $(VERSION_H)
	$(call cross_build,aarch64-linux-gnu-,double,aarch64_dp)

aarch64sp: $(VERSION_H)
	$(call cross_build,aarch64-linux-gnu-,single,aarch64_sp)

# ── ARMv7hf (Docker) ──────────────────────────────────────────────────────────
armhf: $(VERSION_H)
	$(call armhf_docker_build,armhf_dp,double)

armhfsp: $(VERSION_H)
	$(call armhf_docker_build,armhf_sp,single)

# ── MIPS LE — builds inside Docker (Ubuntu 22.04 + gcc-mipsel-linux-gnu) ─────
# /mpy is mounted :ro; container copies to /mpy_build before building.
# Image is built once and reused; rebuild manually with: docker rmi $(DOCKER_IMAGE)
mipsel: $(VERSION_H)
	docker image inspect $(DOCKER_IMAGE) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE) -f $(THIS_DIR)/Dockerfile.mipsel $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); ulimit -n 1024; \
	        cp -r /mpy /mpy_build; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            submodules; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            deplibs; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=double; \
	        mipsel-linux-gnu-strip -s /workspace/usermod/build/mipsel_dp/micropython; \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/build && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/build/mipsel_dp'

mipselsp: $(VERSION_H)
	docker image inspect $(DOCKER_IMAGE) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE) -f $(THIS_DIR)/Dockerfile.mipsel $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); ulimit -n 1024; \
	        cp -r /mpy /mpy_build; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            submodules; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            deplibs; \
	        make -j$$J -C /mpy_build/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=single; \
	        mipsel-linux-gnu-strip -s /workspace/usermod/build/mipsel_sp/micropython; \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/build && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/build/mipsel_sp'

# ── ARMv7m — bare-metal QEMU Cortex-M3 (Docker, build + test) ────────────────
qemu-armv7m: $(VERSION_H)
	docker image inspect $(DOCKER_IMAGE_ARMV7M) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE_ARMV7M) -f $(THIS_DIR)/Dockerfile.armv7m $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE_ARMV7M) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); \
	        cp -r /mpy /mpy_build; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        make -C /workspace/usermod generated MPY_DIR=/mpy_build; \
	        make -j$$J -C /mpy_build/ports/qemu BOARD=MPS2_AN385 \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=single; \
	        python3 /workspace/usermod/ci/run_qemu.py \
	            /mpy_build/ports/qemu/build-MPS2_AN385/firmware.elf \
	            /workspace/tests/; \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/generated && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/generated'

# ── WebAssembly — builds + tests inside Docker (emscripten/emsdk) ────────────
# $(1) = output subdir (wasm_dp / wasm_sp), $(2) = MP_BCLIBC_PRECISION value
define wasm_docker_build
	docker image inspect $(DOCKER_IMAGE_WASM) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE_WASM) -f $(THIS_DIR)/Dockerfile.webassembly $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy:ro" \
	    $(DOCKER_IMAGE_WASM) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); \
	        cp -r /mpy /mpy_build; \
	        find /workspace/usermod/patches -name "*.patch" | sort | while read p; do patch -p1 -d /mpy_build < "$$p"; done; \
	        make -j$$J -C /mpy_build/mpy-cross; \
	        make -j$$J -C /mpy_build/ports/webassembly \
	            BUILD=/workspace/usermod/build/$(1) \
	            USER_C_MODULES=/workspace \
                MICROPY_MPYCROSS=/mpy_build/mpy-cross/build/mpy-cross \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            MP_BCLIBC_PRECISION=$(2); \
	        node /workspace/usermod/build/$(1)/micropython.mjs \
	            /workspace/tests/test_bclibc.py; \
	        chown $(HOST_UID):$(HOST_GID) /workspace/usermod/build && chown -R $(HOST_UID):$(HOST_GID) /workspace/usermod/build/$(1)'
endef

wasm: $(VERSION_H)
	$(call wasm_docker_build,wasm_dp,double)

wasmsp: $(VERSION_H)
	$(call wasm_docker_build,wasm_sp,single)

# ── RP2040 (CMake via pico-sdk) ───────────────────────────────────────────────
rp2040: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" BOARD=RPI_PICO submodules
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" \
	    BUILD="$(_BUILD)/rp2040_sp" \
	    BOARD=RPI_PICO \
	    USER_C_MODULES="$(CMAKE_MODULE)" \
	    FROZEN_MANIFEST="$(MANIFEST)" \
		MP_BCLIBC_PRECISION=single

rp2040dp: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" BOARD=RPI_PICO submodules
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" \
	    BUILD="$(_BUILD)/rp2040_dp" \
	    BOARD=RPI_PICO \
	    USER_C_MODULES="$(CMAKE_MODULE)" \
	    FROZEN_MANIFEST="$(MANIFEST)"

rp2040test: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" BOARD=RPI_PICO submodules
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" \
	    BUILD="$(_BUILD)/rp2040_sp_test" \
	    BOARD=RPI_PICO \
	    USER_C_MODULES="$(CMAKE_MODULE)" \
	    FROZEN_MANIFEST="$(THIS_DIR)/manifest_test.py"

# ── Clean ─────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf "$(_BUILD)" generated/
