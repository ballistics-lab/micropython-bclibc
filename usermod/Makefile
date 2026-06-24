# usermod/Makefile
# Build MicroPython with tiny_bclibc baked in as a USER_C_MODULE.
#
#   make x64        — x64 double    → build/x64_dp/micropython
#   make x64sp      — x64 single    → build/x64_sp/micropython
#   make x86        — x86 double    → build/x86_dp/micropython
#   make x86sp      — x86 single    → build/x86_sp/micropython
#   make aarch64    — AArch64 double → build/aarch64_dp/micropython
#   make aarch64sp  — AArch64 single → build/aarch64_sp/micropython
#   make armhf      — ARMv7hf double → build/armhf_dp/micropython
#   make armhfsp    — ARMv7hf single → build/armhf_sp/micropython
#   make mipsel     — MIPS LE double → build/mipsel_dp/micropython  (Docker)
#   make mipselsp   — MIPS LE single → build/mipsel_sp/micropython  (Docker)
#   make rp2040     — RP2040 single  → build/rp2040_sp/firmware.{elf,uf2}
#   make rp2040dp   — RP2040 double  → build/rp2040_dp/firmware.{elf,uf2}
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

# mipsel targets run inside Docker (Ubuntu 22.04) — MPY_DIR resolved to absolute path
DOCKER_IMAGE := micropython-mipsel-builder
_MPY_ABS     := $(abspath $(MPY_DIR))
_REPO_ABS    := $(abspath $(THIS_DIR)/..)

.PHONY: all submodules apt-deps x64 x64sp x86 x86sp \
        aarch64 aarch64sp armhf armhfsp mipsel mipselsp \
        rp2040 rp2040dp generated clean help

all: x64

help:
	@echo "Targets:                                         Output"
	@echo "  x64 / x64sp          — x64 host (dp / sp)     build/x64_{dp,sp}/micropython"
	@echo "  x86 / x86sp          — x86 32-bit (dp / sp)   build/x86_{dp,sp}/micropython"
	@echo "  aarch64 / aarch64sp  — AArch64 cross           build/aarch64_{dp,sp}/micropython"
	@echo "  armhf / armhfsp      — ARMv7hf cross           build/armhf_{dp,sp}/micropython"
	@echo "  mipsel / mipselsp    — MIPS LE (Docker)        build/mipsel_{dp,sp}/micropython"
	@echo "  rp2040 / rp2040dp    — RP2040 Pico (sp / dp)  build/rp2040_{sp,dp}/firmware.uf2"
	@echo "Set MPY_DIR= to point at a MicroPython source tree"
	@echo ""
	@echo "Setup targets:"
	@echo "  apt-deps             — install Debian/Ubuntu build deps (gcc-multilib etc.)"
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
	    TINY_BCLIBC_PRECISION=$(2)
endef

# ── Cross-compile macro ────────────────────────────────────────────────────────
# $(1) = CROSS_COMPILE prefix, e.g. arm-linux-gnueabihf-
# $(2) = precision: single | double
# $(3) = output subdirectory, e.g. armhf_dp
define cross_build
	$(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=standard \
	    BUILD="$(_BUILD)/$(3)" \
	    CROSS_COMPILE=$(1) \
	    MICROPY_STANDALONE=1 \
	    LDFLAGS_EXTRA="-static" \
	    USER_C_MODULES="$(MAKE_MODULES)" \
	    FROZEN_MANIFEST="$(MANIFEST)" \
	    TINY_BCLIBC_PRECISION=$(2)
	$(1)strip -s "$(_BUILD)/$(3)/micropython"
endef

submodules:
	git submodule update --init --recursive

# Install host packages required to build x86 targets (Debian/Ubuntu).
apt-deps:
	sudo apt-get install -y \
	    gcc-multilib g++-multilib \
	    texinfo autoconf automake libtool

# ── x64 ───────────────────────────────────────────────────────────────────────
x64: $(VERSION_H)
	$(call unix_build,,double,x64_dp)

x64sp: $(VERSION_H)
	$(call unix_build,,single,x64_sp)

# ── x86 — standalone (MICROPY_STANDALONE=1 avoids system 32-bit libffi) ─────
# deplibs builds lib32/libffi.a into BUILD; autoreconf is needed when the
# libffi configure script is absent (fresh clone / first build).
define x86_deplibs
	test -f "$(abspath $(MPY_DIR)/lib/libffi/configure.ac)" || \
	    $(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=standard \
	        BUILD="$(_BUILD)/$(1)" \
	        MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	        submodules
	test -f "$(abspath $(MPY_DIR)/lib/libffi/configure)" || \
	    ( cd "$(abspath $(MPY_DIR)/lib/libffi)" && libtoolize --copy --force && autoreconf -fvi )
	$(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=standard \
	    BUILD="$(_BUILD)/$(1)" \
	    MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	    deplibs
endef

x86: $(VERSION_H)
	$(call x86_deplibs,x86_dp)
	$(call unix_build,MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static",double,x86_dp)

x86sp: $(VERSION_H)
	$(call x86_deplibs,x86_sp)
	$(call unix_build,MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static",single,x86_sp)

# ── AArch64 (cross) ───────────────────────────────────────────────────────────
aarch64: $(VERSION_H)
	$(call cross_build,aarch64-linux-gnu-,double,aarch64_dp)

aarch64sp: $(VERSION_H)
	$(call cross_build,aarch64-linux-gnu-,single,aarch64_sp)

# ── ARMv7hf (cross) ───────────────────────────────────────────────────────────
armhf: $(VERSION_H)
	$(call cross_build,arm-linux-gnueabihf-,double,armhf_dp)

armhfsp: $(VERSION_H)
	$(call cross_build,arm-linux-gnueabihf-,single,armhf_sp)

# ── MIPS LE — builds inside Docker (Ubuntu 22.04 + gcc-mipsel-linux-gnu) ─────
# MPY_DIR is mounted read-write (deplibs writes into it); output lands in build/mipsel_{dp,sp}.
# Image is built once and reused; rebuild manually with: docker rmi $(DOCKER_IMAGE)
mipsel: $(VERSION_H)
	docker image inspect $(DOCKER_IMAGE) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE) -f $(THIS_DIR)/Dockerfile.mipsel $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy" \
	    $(DOCKER_IMAGE) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); ulimit -n 1024; \
	        make -j$$J -C /mpy/mpy-cross; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            submodules; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            deplibs; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_dp \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            TINY_BCLIBC_PRECISION=double; \
	        mipsel-linux-gnu-strip -s /workspace/usermod/build/mipsel_dp/micropython'

mipselsp: $(VERSION_H)
	docker image inspect $(DOCKER_IMAGE) >/dev/null 2>&1 || \
	    docker build -t $(DOCKER_IMAGE) -f $(THIS_DIR)/Dockerfile.mipsel $(THIS_DIR)
	docker run --rm \
	    -v "$(_REPO_ABS):/workspace" \
	    -v "$(_MPY_ABS):/mpy" \
	    $(DOCKER_IMAGE) \
	    bash -exc '\
	        git config --global --add safe.directory "*"; \
	        J=$$(nproc); ulimit -n 1024; \
	        make -j$$J -C /mpy/mpy-cross; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            submodules; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            deplibs; \
	        make -j$$J -C /mpy/ports/unix \
	            CROSS_COMPILE=mipsel-linux-gnu- VARIANT=coverage \
	            MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static" \
	            BUILD=/workspace/usermod/build/mipsel_sp \
	            USER_C_MODULES=/workspace \
	            FROZEN_MANIFEST=/workspace/usermod/manifest.py \
	            TINY_BCLIBC_PRECISION=single; \
	        mipsel-linux-gnu-strip -s /workspace/usermod/build/mipsel_sp/micropython'

# ── RP2040 (CMake via pico-sdk) ───────────────────────────────────────────────
rp2040: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" BOARD=RPI_PICO submodules
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" \
	    BUILD="$(_BUILD)/rp2040_sp" \
	    BOARD=RPI_PICO \
	    USER_C_MODULES="$(CMAKE_MODULE)" \
	    FROZEN_MANIFEST="$(MANIFEST)"

rp2040dp: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" BOARD=RPI_PICO submodules
	TINY_BCLIBC_DOUBLE_PRECISION=1 \
	$(MAKE) -C "$(MPY_DIR)/ports/rp2" \
	    BUILD="$(_BUILD)/rp2040_dp" \
	    BOARD=RPI_PICO \
	    USER_C_MODULES="$(CMAKE_MODULE)" \
	    FROZEN_MANIFEST="$(MANIFEST)"

# ── Clean ─────────────────────────────────────────────────────────────────────
.PHONY: clean
clean:
	rm -rf "$(_BUILD)" generated/
