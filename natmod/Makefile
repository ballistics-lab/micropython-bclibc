# ── Arch selection ─────────────────────────────────────────────────────────────
#
#   make                       → x64 (double, default)
#   make ARCH=x86              → x86 32-bit (double, default)
#   make ARCH=aarch64          → AArch64 Linux host (double, default)
#   make ARCH=armv6m           → RP2040 / Cortex-M0+
#   make ARCH=armv7m           → Cortex-M3
#   make ARCH=armv7emsp        → Cortex-M4F / M7 single-precision FPU
#   make ARCH=armv7emdp        → Cortex-M7 double-precision FPU
#   make ARCH=xtensawin        → ESP32 / ESP32-S3 (Xtensa windowed)
#   make ARCH=xtensa           → ESP8266 (Xtensa no-window)
#   make ARCH=rv32imc          → ESP32-C3 / ESP32-C6 (RISC-V 32)
#   make ARCH=rv64imc          → RISC-V 64
#
ARCH    ?= x64
MPY_DIR ?= micropython

# ── Precision ─────────────────────────────────────────────────────────────────
# Derived from ARCH's actual FPU, not a separate knob you need to remember:
# there's no point building (let alone shipping) a "double" variant for a
# target with no double-precision FPU, or a "single" variant for one that
# has one. Override with MP_BCLIBC_PRECISION= only if you specifically need
# the other precision for your own build (e.g. testing) -- CI never does.
#
#   armv7emdp        → double (Cortex-M7, double-precision FPU -- the "dp" in
#                       the ARCH name)
#   x64/x86/aarch64   → double (host/dev target, no MCU FPU constraint)
#   everything else   → single (armv6m/armv7m/armv7emsp/xtensa/xtensawin/
#                       rv32imc/rv64imc: either no FPU at all, or single-
#                       precision only)
ifeq ($(ARCH),armv7emdp)
MP_BCLIBC_PRECISION ?= double
else ifeq ($(ARCH),$(filter $(ARCH),x64 x86 aarch64))
MP_BCLIBC_PRECISION ?= double
else
MP_BCLIBC_PRECISION ?= single
endif

ifeq ($(MP_BCLIBC_PRECISION),single)
_PREC_SUFFIX := _sp
else
_PREC_SUFFIX := _dp
endif

MOD         = tiny_bclibc_$(ARCH)$(_PREC_SUFFIX)
BCLIBC_ROOT = ../bclibc
SRC_DIR     = ../src
BUILD       = build/$(ARCH)$(_PREC_SUFFIX)
VERSION_H   = generated/bclibc_mp/version.h
VERSION_IN  = ../version.h.in

# Use vpath so that local sources (tiny_bclibc_mp.c, math_shim.c, mem_shim.c)
# are found by filename only.  dynruntime.mk then computes the object as
# $(BUILD)/tiny_bclibc_mp.o (arch-specific), not $(BUILD)/../src/tiny_bclibc_mp.o
# (shared across all arches, which causes "incompatible arch" when x64 and x86
# builds share the same object file). Covers .py too, now that tiny_bclibc.py
# is part of SRC (mpy-cross output is arch-specific bytecode, same reasoning).
vpath %.c $(SRC_DIR)
vpath %.py $(SRC_DIR)

# tiny_bclibc.py alongside the .c sources -- dynruntime.mk's own SRC_MPY/
# --merge rule mpy-cross-compiles it and merges it with the native part into
# one tiny_bclibc.mpy (see docs/develop/natmod.rst "Defining a native
# module", and a7p's natmod/Makefile for the same pattern). tiny_bclibc.py's
# own top-level code runs in the same globals namespace the native part
# populates -- no `import _tiny_bclibc` finds anything on this path, which is
# why tiny_bclibc.py's own try/except ImportError fallback captures the bare
# globals mpy_init() left behind instead.
SRC = tiny_bclibc_mp.c tiny_bclibc.py

# ── Shared math-library sources ───────────────────────────────────────────────
#
# fdlibm (single-precision, BSD types) — used on x64/x86 single and RISC-V.
# fdlibm.h uses BSD __int32_t → alias with -D and -include stdint.h.
#
_FDLIBM_DIR   := $(MPY_DIR)/lib/libm
_FDLIBM_SRCS  := $(_FDLIBM_DIR)/sf_sin.c      \
                 $(_FDLIBM_DIR)/sf_cos.c      \
                 $(_FDLIBM_DIR)/kf_sin.c      \
                 $(_FDLIBM_DIR)/kf_cos.c      \
                 $(_FDLIBM_DIR)/ef_rem_pio2.c \
                 $(_FDLIBM_DIR)/kf_rem_pio2.c \
                 $(_FDLIBM_DIR)/atan2f.c      \
                 $(_FDLIBM_DIR)/atanf.c       \
                 $(_FDLIBM_DIR)/ef_sqrt.c     \
                 $(_FDLIBM_DIR)/math.c
_FDLIBM_FLAGS := -I$(MPY_DIR)/lib    \
                 -include stdint.h   \
                 -D__int32_t=int32_t \
                 -D__uint32_t=uint32_t \
                 -D__uint8_t=uint8_t

# libm_dbl (double-precision, musl-derived) — used on x64/x86 double.
# math_shadow/math.h intercepts <math.h> to prevent glibc/__sin conflict.
# floor.c is needed by __rem_pio2_large.c.
#
_LIBM_DBL_DIR   := $(MPY_DIR)/lib/libm_dbl
_LIBM_DBL_SRCS  := $(_LIBM_DBL_DIR)/sin.c              \
                   $(_LIBM_DBL_DIR)/cos.c              \
                   $(_LIBM_DBL_DIR)/sqrt.c             \
                   $(_LIBM_DBL_DIR)/atan2.c            \
                   $(_LIBM_DBL_DIR)/atan.c             \
                   $(_LIBM_DBL_DIR)/exp.c              \
                   $(_LIBM_DBL_DIR)/pow.c              \
                   $(_LIBM_DBL_DIR)/log.c              \
                   $(_LIBM_DBL_DIR)/__sin.c            \
                   $(_LIBM_DBL_DIR)/__cos.c            \
                   $(_LIBM_DBL_DIR)/__rem_pio2.c       \
                   $(_LIBM_DBL_DIR)/__rem_pio2_large.c \
                   $(_LIBM_DBL_DIR)/__expo2.c          \
                   $(_LIBM_DBL_DIR)/scalbn.c           \
                   $(_LIBM_DBL_DIR)/frexp.c            \
                   $(_LIBM_DBL_DIR)/floor.c
_LIBM_DBL_FLAGS := -I$(MPY_DIR)/lib/libm_dbl \
                   -I $(SRC_DIR)/math_shadow

# ── Math library selection ────────────────────────────────────────────────────
ifeq ($(ARCH),$(filter $(ARCH),x64 x86 aarch64))
# Host (Linux): glibc libm.a uses IFUNC internals that can't be linked in a natmod.
# GCC -O2 merges sin()+cos() → sincos() (GNU ext) → math_shim.c provides it.
ifeq ($(MP_BCLIBC_PRECISION),single)
SRC          += $(_FDLIBM_SRCS) math_shim.c
CFLAGS_EXTRA += $(_FDLIBM_FLAGS)
else
SRC          += $(_LIBM_DBL_SRCS) math_shim.c
CFLAGS_EXTRA += $(_LIBM_DBL_FLAGS)
endif
ifeq ($(ARCH),x86)
CFLAGS_EXTRA += -msse2 -mfpmath=sse
endif

else ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc))
# RISC-V: picolibc libc.a triggers a mpy_ld.py bug (.srodata sections not
# recognised + absolute LO12 relocation unhandled).  Use fdlibm + libgcc
# soft-float directly until the upstream fix lands.
# See RISC-V_picolibc.md (same directory as this Makefile) for details and the patch.
SRC          += $(_FDLIBM_SRCS) mem_shim.c
CFLAGS_EXTRA += $(_FDLIBM_FLAGS)

else ifeq ($(ARCH),$(filter $(ARCH),xtensa xtensawin))
# Xtensa: the xtensa-lx106/esp32 toolchains' own newlib libm.a pulls in
# lib_a-s_lib_ver.o (fdlibm's _LIB_VERSION control global) to satisfy
# atan2f/etc, and that object has a non-empty .data section -- mpy_ld.py
# hard-rejects any .data in a linked native module (confirmed by a real CI
# failure: "LinkError: .../libm.a:lib_a-s_lib_ver.o: .data non-empty").
# Same fdlibm-from-source route as RISC-V above sidesteps it entirely.
SRC          += $(_FDLIBM_SRCS) mem_shim.c
CFLAGS_EXTRA += $(_FDLIBM_FLAGS)

else
# ARM (Cortex-M): newlib libm.a is self-contained and, unlike the Xtensa
# toolchains above, doesn't pull in a non-empty .data object for the
# trig functions this project uses.
LINK_RUNTIME  = 1
SRC          += mem_shim.c
endif

# ── Arch-specific cross-compiler prefix ───────────────────────────────────────
ifeq ($(ARCH),xtensawin)
CROSS = xtensa-esp32s3-elf-
else ifeq ($(ARCH),xtensa)
CROSS = xtensa-esp32-elf-
endif

# ── Common flags ──────────────────────────────────────────────────────────────
CFLAGS_EXTRA += \
    -I$(BCLIBC_ROOT)/tiny_bclibc/include \
    -Igenerated \
    -DTINY_BCLIBC_NO_THREAD_LOCAL \
    -DTINY_BCLIBC_NO_ERR_BUF \
    -DBCLIBC_BUILD_NATMOD

ifeq ($(MP_BCLIBC_PRECISION),single)
CFLAGS_EXTRA += -DTINY_BCLIBC_SINGLE_PRECISION -DTINY_BCLIBC_FAST_ZERO_FIND
endif

# Guard the include so 'make clean' works without MPY_DIR.
# dynruntime.mk has no -MMD so header changes are not auto-tracked; see below.
ifeq ($(wildcard $(MPY_DIR)/py/dynruntime.mk),)
ifeq ($(filter clean,$(MAKECMDGOALS)),clean)
# clean only — dynruntime.mk not needed
else
$(error MPY_DIR="$(MPY_DIR)" — set MPY_DIR=/path/to/micropython)
endif
else
include $(MPY_DIR)/py/dynruntime.mk
endif

# ── Header dependency tracking ────────────────────────────────────────────────
# dynruntime.mk compiles with no -MMD, so .o files only depend on .c.
# Force a rebuild of all object files when any tiny_bclibc header changes.
_TINY_HEADERS := $(wildcard $(BCLIBC_ROOT)/tiny_bclibc/include/tiny_bclibc/*.h)
$(SRC_O): $(_TINY_HEADERS)

# ── RISC-V + Xtensa: add libgcc.a for soft-float builtins ────────────────────
# Must be after include so CROSS and CFLAGS_ARCH are set by dynruntime.mk.
# Both use the fdlibm-from-source route above (no LINK_RUNTIME, which used
# to pull libgcc in implicitly via the toolchain's own libm.a) -- without
# this, xtensa fails with "undefined symbol: __lesf2" (a real CI failure):
# fdlibm's single-precision comparisons lower to libgcc soft-float calls on
# a target with no hardware FPU (xtensa-lx106/esp32 have none for this).
ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc xtensa xtensawin))
MPY_LD_FLAGS += -l$(realpath $(shell $(CROSS)gcc $(CFLAGS_ARCH) --print-libgcc-file-name))
endif

# ── Version header ─────────────────────────────────────────────────────────────
$(VERSION_H): $(VERSION_IN)
	$(ECHO) "  GEN   $@"
	$(Q)mkdir -p $(dir $@)
	$(eval _TAG  := $(shell git describe --tags --always 2>/dev/null || echo v0.0.0))
	$(eval _MAJ  := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?([0-9]+)\..*/\1/;t;s/.*/0/'))
	$(eval _MIN  := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?[0-9]+\.([0-9]+)\..*/\1/;t;s/.*/0/'))
	$(eval _PAT  := $(shell printf '%s' '$(_TAG)' | sed -E 's/^v?[0-9]+\.[0-9]+\.([0-9]+).*/\1/;t;s/.*/0/'))
	$(eval _VER  := $(shell printf '%s' '$(_TAG)' | sed 's/^v//'))
	$(Q)sed -e 's/@MP_BCLIBC_VERSION_MAJOR@/$(_MAJ)/g' \
	        -e 's/@MP_BCLIBC_VERSION_MINOR@/$(_MIN)/g' \
	        -e 's/@MP_BCLIBC_VERSION_PATCH@/$(_PAT)/g' \
	        -e 's/@MP_BCLIBC_VERSION@/$(_VER)/g' \
	        $< > $@

$(BUILD)/tiny_bclibc_mp.o: $(VERSION_H)

.PHONY: submodules dist clean

submodules:
	git submodule update --init --recursive

dist: all
	$(Q)mv $(MOD).mpy $(BUILD)/tiny_bclibc.mpy
	$(Q)rm -f $(BUILD)/$(MOD).native.mpy
	$(ECHO) "  →  $(BUILD)/tiny_bclibc.mpy"

clean:
	rm -rf build generated
