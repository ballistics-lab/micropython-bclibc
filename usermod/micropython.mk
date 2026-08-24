# usermod/micropython.mk
# Included by MicroPython's py.mk when USER_C_MODULES=<>.
# USERMOD_DIR is set by py.mk to the directory containing this file
# (= usermod/).
#
# No wrapper Makefile of our own for usermod (a7p doesn't have one for its
# own usermod either) -- this file is the entire "how to build with bclibc"
# story for Make-based ports. py.mk scans $(USER_C_MODULES)/*/micropython.mk,
# so point USER_C_MODULES at this file's *parent* directory (the repo root,
# one level up from usermod/) and build normally -- e.g.
# USER_C_MODULES=/path/to/micropython-bclibc.

# ── Version header ────────────────────────────────────────────────────────────
# tiny_bclibc_mp.c does #include "generated/bclibc_mp/version.h" -- generate
# it once if missing (same git-describe + version.h.in template as
# micropython.cmake's own equivalent block, for CMake-based ports). Plain
# $(shell) at parse time, guarded by $(wildcard), rather than a proper Make
# rule: this file is *included* into another port's own Makefile, and a
# real rule would need to predict that port's own object-file path scheme
# for py.mk's USER_C_MODULES sources to wire up a dependency correctly.
# Regenerating only when the file doesn't exist yet avoids that entirely,
# at the cost of a stale version string surviving until `generated/` is
# removed by hand -- an acceptable tradeoff for a version string.
ifeq ($(wildcard $(USERMOD_DIR)/generated/bclibc_mp/version.h),)
$(shell mkdir -p $(USERMOD_DIR)/generated/bclibc_mp)
_BCLIBC_GIT_TAG := $(shell git -C $(USERMOD_DIR)/.. describe --tags --always 2>/dev/null || echo v0.0.0)
_BCLIBC_MAJ := $(shell printf '%s' '$(_BCLIBC_GIT_TAG)' | sed -E 's/^v?([0-9]+)\..*/\1/;t;s/.*/0/')
_BCLIBC_MIN := $(shell printf '%s' '$(_BCLIBC_GIT_TAG)' | sed -E 's/^v?[0-9]+\.([0-9]+)\..*/\1/;t;s/.*/0/')
_BCLIBC_PAT := $(shell printf '%s' '$(_BCLIBC_GIT_TAG)' | sed -E 's/^v?[0-9]+\.[0-9]+\.([0-9]+).*/\1/;t;s/.*/0/')
_BCLIBC_VER := $(shell printf '%s' '$(_BCLIBC_GIT_TAG)' | sed 's/^v//')
$(shell sed -e 's/@MP_BCLIBC_VERSION_MAJOR@/$(_BCLIBC_MAJ)/g' \
            -e 's/@MP_BCLIBC_VERSION_MINOR@/$(_BCLIBC_MIN)/g' \
            -e 's/@MP_BCLIBC_VERSION_PATCH@/$(_BCLIBC_PAT)/g' \
            -e 's/@MP_BCLIBC_VERSION@/$(_BCLIBC_VER)/g' \
            $(USERMOD_DIR)/../version.h.in > $(USERMOD_DIR)/generated/bclibc_mp/version.h)
endif

# Source lives one level up in src/ — relative to  so
# py.mk's PATHFIX strips the USER_C_MODULES prefix and build path is sane.
SRC_USERMOD_C += $(USERMOD_DIR)/../src/tiny_bclibc_mp.c

CFLAGS_USERMOD += \
    -I$(USERMOD_DIR)/../bclibc/tiny_bclibc/include \
    -I$(USERMOD_DIR) \
    -DTINY_BCLIBC_NO_THREAD_LOCAL \
    -DTINY_BCLIBC_NO_ERR_BUF

# Precision: always single -- no more MP_BCLIBC_PRECISION knob, no double
# variant (see natmod/Makefile's own "Precision" header for why).
CFLAGS_USERMOD += \
    -DTINY_BCLIBC_SINGLE_PRECISION \
    -DTINY_BCLIBC_FAST_ZERO_FIND
