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
#   make mipsel     — MIPS LE double → build/mipsel_dp/micropython
#   make mipselsp   — MIPS LE single → build/mipsel_sp/micropython
#   make rp2040     — RP2040 single  → build/rp2040_sp/firmware.{elf,uf2}
#   make rp2040dp   — RP2040 double  → build/rp2040_dp/firmware.{elf,uf2}
#
# Set MPY_DIR= to override (default: ../natmod/micropython symlink).

MPY_DIR      ?= micropython
THIS_DIR     := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
# make-based ports: USER_C_MODULES must be a directory.
# py.mk searches $(USER_C_MODULES)/*/micropython.mk — we point to 
# so that usermod/micropython.mk is found as the module descriptor.
MAKE_MODULES := $(abspath ../)
# cmake-based ports (rp2040, esp32): pass the .cmake file.
CMAKE_MODULE := $(THIS_DIR)/micropython.cmake
MANIFEST     := $(THIS_DIR)/manifest.py
VERSION_H    := $(THIS_DIR)/generated/bclibc_mp/version.h
VERSION_IN   := $(abspath ../version.h.in)
BCLIBC_ROOT  := $(abspath ../..)
_BUILD       := $(THIS_DIR)/build

.PHONY: all x64 x64sp x86 x86sp \
        aarch64 aarch64sp armhf armhfsp mipsel mipselsp \
        rp2040 rp2040dp generated clean help

all: x64

help:
	@echo "Targets:                                         Output"
	@echo "  x64 / x64sp          — x64 host (dp / sp)     build/x64_{dp,sp}/micropython"
	@echo "  x86 / x86sp          — x86 32-bit (dp / sp)   build/x86_{dp,sp}/micropython"
	@echo "  aarch64 / aarch64sp  — AArch64 cross           build/aarch64_{dp,sp}/micropython"
	@echo "  armhf / armhfsp      — ARMv7hf cross           build/armhf_{dp,sp}/micropython"
	@echo "  mipsel / mipselsp    — MIPS LE cross            build/mipsel_{dp,sp}/micropython"
	@echo "  rp2040 / rp2040dp    — RP2040 Pico (sp / dp)  build/rp2040_{sp,dp}/firmware.uf2"
	@echo "Set MPY_DIR= to override MicroPython source"

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
# Precision is passed as TINY_BCLIBC_PRECISION, picked up by micropython.mk.
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
endef

# ── x64 ───────────────────────────────────────────────────────────────────────
x64: $(VERSION_H)
	$(call unix_build,,double,x64_dp)

x64sp: $(VERSION_H)
	$(call unix_build,,single,x64_sp)

# ── x86 — standalone (MICROPY_STANDALONE=1 avoids system 32-bit libffi) ─────
# Requires: gcc-multilib + one-time setup:
#   make -C $MPY_DIR/ports/unix MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 submodules deplibs
x86: $(VERSION_H)
	$(call unix_build,MICROPY_FORCE_32BIT=1 MICROPY_STANDALONE=1 LDFLAGS_EXTRA="-static",double,x86_dp)

x86sp: $(VERSION_H)
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

# ── MIPS LE (cross) — coverage variant required for MIPS ─────────────────────
mipsel: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=coverage \
	    BUILD="$(_BUILD)/mipsel_dp" \
	    CROSS_COMPILE=mipsel-linux-gnu- \
	    MICROPY_STANDALONE=1 \
	    LDFLAGS_EXTRA="-static" \
	    USER_C_MODULES="$(MAKE_MODULES)" \
	    FROZEN_MANIFEST="$(MANIFEST)" \
	    TINY_BCLIBC_PRECISION=double

mipselsp: $(VERSION_H)
	$(MAKE) -C "$(MPY_DIR)/ports/unix" VARIANT=coverage \
	    BUILD="$(_BUILD)/mipsel_sp" \
	    CROSS_COMPILE=mipsel-linux-gnu- \
	    MICROPY_STANDALONE=1 \
	    LDFLAGS_EXTRA="-static" \
	    USER_C_MODULES="$(MAKE_MODULES)" \
	    FROZEN_MANIFEST="$(MANIFEST)" \
	    TINY_BCLIBC_PRECISION=single

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
clean:
	rm -rf build/ generated/
