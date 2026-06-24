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
# PRECISION=double → _dp suffix  (default on x64/x86)
# PRECISION=single → _sp suffix  (default on MCU)
#
ifeq ($(ARCH),$(filter $(ARCH),x64 x86))
PRECISION ?= double
else
PRECISION ?= single
endif

ifeq ($(PRECISION),single)
_PREC_SUFFIX := _sp
else
_PREC_SUFFIX := _dp
endif

MOD         = _tiny_bclibc_$(ARCH)$(_PREC_SUFFIX)
BCLIBC_ROOT = ../bclibc
SRC_DIR     = ../src
BUILD       = build/$(ARCH)$(_PREC_SUFFIX)
MPY_CROSS  ?= $(MPY_DIR)/mpy-cross/build/mpy-cross
VERSION_H   = generated/bclibc_mp/version.h
VERSION_IN  = ../version.h.in

# Use vpath so that local sources (tiny_bclibc_mp.c, math_shim.c, mem_shim.c)
# are found by filename only.  dynruntime.mk then computes the object as
# $(BUILD)/tiny_bclibc_mp.o (arch-specific), not $(BUILD)/../src/tiny_bclibc_mp.o
# (shared across all arches, which causes "incompatible arch" when x64 and x86
# builds share the same object file).
vpath %.c $(SRC_DIR)

SRC = tiny_bclibc_mp.c

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
ifeq ($(PRECISION),single)
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

else
# ARM + Xtensa: newlib libm.a is self-contained and provides both precisions.
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

ifeq ($(PRECISION),single)
CFLAGS_EXTRA += -DTINY_BCLIBC_SINGLE_PRECISION -DMP_BCLIBC_SINGLE_PRECISION -DTINY_BCLIBC_FAST_ZERO_FIND
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

# ── RISC-V: add libgcc.a for soft-float builtins ─────────────────────────────
# Must be after include so CROSS and CFLAGS_ARCH are set by dynruntime.mk.
ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc))
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

# ── Convenience aliases ────────────────────────────────────────────────────────
.PHONY: submodules x64 x64sp x86 x86sp aarch64 aarch64sp rp2040 rp2350 stm32f4 armv7m stm32h7 stm32h7dp esp32s3 esp32 esp32c3 esp32c6 rv64 dist clean

submodules:
	git submodule update --init --recursive

x64:
	$(MAKE) ARCH=x64 PRECISION=double dist

x64sp:
	$(MAKE) ARCH=x64 PRECISION=single dist

aarch64:
	$(MAKE) ARCH=aarch64 PRECISION=double dist

aarch64sp:
	$(MAKE) ARCH=aarch64 PRECISION=single dist

x86:
	$(MAKE) ARCH=x86 PRECISION=double dist

x86sp:
	$(MAKE) ARCH=x86 PRECISION=single dist

rp2040:
	$(MAKE) ARCH=armv6m PRECISION=single dist

armv7m:
	$(MAKE) ARCH=armv7m PRECISION=single dist

rp2350 stm32f4:
	$(MAKE) ARCH=armv7emsp PRECISION=single dist

stm32h7:
	$(MAKE) ARCH=armv7emdp PRECISION=single dist

stm32h7dp:
	$(MAKE) ARCH=armv7emdp PRECISION=double dist

esp32s3:
	$(MAKE) ARCH=xtensawin PRECISION=single dist

esp32:
	$(MAKE) ARCH=xtensa PRECISION=single dist

esp32c3 esp32c6:
	$(MAKE) ARCH=rv32imc PRECISION=single dist

rv64:
	$(MAKE) ARCH=rv64imc PRECISION=single dist

dist: all
	$(Q)mv $(MOD).mpy $(BUILD)/_tiny_bclibc.mpy
	$(ECHO) "  MPY   $(BUILD)/tiny_bclibc.mpy"
	$(Q)$(MPY_CROSS) -march=$(ARCH) $(SRC_DIR)/tiny_bclibc.py -o $(BUILD)/tiny_bclibc.mpy
	$(ECHO) "  →  $(BUILD)/_tiny_bclibc.mpy"
	$(ECHO) "  →  $(BUILD)/tiny_bclibc.mpy"

clean:
	rm -rf build generated
