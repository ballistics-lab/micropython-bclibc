# ── Arch selection ─────────────────────────────────────────────────────────────
#
#   make                       → x64
#   make ARCH=x86              → x86 32-bit
#   make ARCH=armv6m           → RP2040 / Cortex-M0+
#   make ARCH=armv7m           → Cortex-M3
#   make ARCH=armv7emsp        → Cortex-M4F / M7 single-precision FPU
#   make ARCH=armv7emdp        → Cortex-M7 double-precision FPU
#   make ARCH=xtensawin        → ESP32 / ESP32-S3 (Xtensa windowed)
#   make ARCH=xtensa           → ESP8266 (Xtensa no-window)
#   make ARCH=rv32imc          → ESP32-C3 / ESP32-C6 (RISC-V 32)
#   make ARCH=rv64imc          → RISC-V 64
#
# No aarch64 here: dynruntime.mk (as of MicroPython <=v1.28) has no ARCH=aarch64
# branch at all -- natmod can't target it, full stop, regardless of anything in
# this file. aarch64 is covered separately via ../usermod (which links straight
# into the port's own build instead of going through dynruntime.mk) and
# ../ffimod (libtiny_bclibc.so via the ffi module, no native .mpy needed).
#
ARCH    ?= x64
MPY_DIR ?= micropython

# ── Precision ─────────────────────────────────────────────────────────────────
# Always single -- no more per-ARCH double-precision variant, no more
# MP_BCLIBC_PRECISION knob, no more _dp/_sp split in MOD/BUILD. armv7emdp
# still exists as its own ARCH (distinct MP_NATIVE_ARCH_* identifier, real
# Cortex-M7 double-precision FPU hardware), but the library itself no
# longer builds a second, wider-precision variant for it or for x64/x86.
CFLAGS_EXTRA += -DTINY_BCLIBC_SINGLE_PRECISION -DTINY_BCLIBC_FAST_ZERO_FIND

MOD         = tiny_bclibc_$(ARCH)
BCLIBC_ROOT = ../bclibc
SRC_DIR     = ../src
BUILD       = build/$(ARCH)
# dist: below renames the merged native output to $(BUILD)/tiny_bclibc.mpy
# -- the exact path dynruntime.mk's own $(BUILD)/%.mpy: %.py rule also
# owns, for the compiled *facade* (../src/tiny_bclibc.py). A second build
# in this same $(BUILD) directory (e.g. cibuildmp run twice locally) finds
# that leftover, already-native file, treats it as the up-to-date facade
# compile, and mpy-tool.py then refuses to merge two files that both
# contain native code. A recipe-line `rm -f` in dist: is too late -- by
# the time dist:'s own recipe runs, `all` has already decided the stale
# file was fine. This has to happen before make resolves any rule, hence
# $(shell) at parse time, not a prerequisite.
$(shell rm -f $(BUILD)/tiny_bclibc.mpy 2>/dev/null)
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

# ── Math library selection ────────────────────────────────────────────────────
# No more libm_dbl (double-precision, musl-derived) branch here -- single
# precision only now (see the "Precision" section above), so x64/x86 uses
# the same fdlibm-from-source route every other arch already did.
ifeq ($(ARCH),$(filter $(ARCH),x64 x86))
# Host (Linux): glibc libm.a uses IFUNC internals that can't be linked in a natmod.
# GCC -O2 merges sin()+cos() → sincos() (GNU ext) → math_shim.c provides it.
SRC          += $(_FDLIBM_SRCS) math_shim.c
CFLAGS_EXTRA += $(_FDLIBM_FLAGS)
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

# ── armv7emsp float ABI: match RP2350, not dynruntime.mk's generic default ──
# dynruntime.mk's own armv7emsp branch hardcodes -mfpu=fpv4-sp-d16
# -mfloat-abi=hard (right for STM32/Cortex-M4F, which this project doesn't
# target). The only real armv7emsp target here is rp2's
# RPI_PICO2/RPI_PICO2_W (Cortex-M33), and pico-sdk's own toolchain file
# builds that whole firmware -mfloat-abi=softfp (see
# lib/pico-sdk/cmake/preload/toolchains/pico_arm_cortex_m33_gcc.cmake in the
# micropython tree). A natmod built hard against a softfp firmware still
# links and runs, but every float crossing the mp_fun_table boundary
# (mp_obj_new_float_from_d, mp_obj_get_float_to_d, float args/returns) is
# silently corrupted -- caught live on real RPI_PICO2 hardware:
# integrate_at() always raised "interception error" because the incoming
# target distance decoded as garbage.
#
# Just appending -mfloat-abi=softfp via CFLAGS_EXTRA (after dynruntime.mk's
# own -mfloat-abi=hard) is not enough: dynruntime.mk's own LINK_RUNTIME=1
# block (above) re-probes `$(CROSS)gcc $(CFLAGS) --print-libgcc-file-name`
# for the newlib libgcc.a/libm.a multilib variant to statically link in, and
# with *both* -mfloat-abi flags present that probe stops matching any
# thumb/v7e-m multilib at all and silently falls back to the base (non-thumb)
# variant -- confirmed by a real build: mpy_ld.py then aborts linking with
# "AssertionError: (28, '__ieee754_sqrtf', ...)" because that library's
# relocations don't fit the M-profile native module format.
# `filter-out` strips the conflicting flag from the *expanded* value, so
# there's exactly one -mfloat-abi in CFLAGS/CFLAGS_ARCH by the time the
# LINK_RUNTIME libgcc/libm probe (and every compile recipe) reads them --
# both already ran during the `include` above, so redo them here.
ifeq ($(ARCH),armv7emsp)
CFLAGS       := $(filter-out -mfloat-abi=hard,$(CFLAGS)) -mfloat-abi=softfp
CFLAGS_ARCH  := $(filter-out -mfloat-abi=hard,$(CFLAGS_ARCH)) -mfloat-abi=softfp
MPY_LD_FLAGS := $(filter-out -l$(LIBGCC_PATH) -l$(LIBM_PATH),$(MPY_LD_FLAGS))
LIBGCC_PATH  := $(realpath $(shell $(CROSS)gcc $(CFLAGS) --print-libgcc-file-name))
LIBM_PATH    := $(realpath $(shell $(CROSS)gcc $(CFLAGS) --print-file-name=libm.a))
MPY_LD_FLAGS += $(addprefix -l, $(LIBGCC_PATH) $(LIBM_PATH))
endif

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
	$(Q)rm -f $(BUILD)/$(MOD).mpy $(BUILD)/$(MOD).native.mpy $(SRC_O) $(CONFIG_H)
	$(ECHO) "  →  $(BUILD)/tiny_bclibc.mpy"

clean:
	rm -rf build generated
