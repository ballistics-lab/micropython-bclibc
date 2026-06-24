# usermod/micropython.mk
# Included by MicroPython's py.mk when USER_C_MODULES=<>.
# USERMOD_DIR is set by py.mk to the directory containing this file
# (= usermod/).

# Source lives one level up in src/ — relative to  so
# py.mk's PATHFIX strips the USER_C_MODULES prefix and build path is sane.
SRC_USERMOD_C += $(USERMOD_DIR)/../src/tiny_bclibc_mp.c

CFLAGS_USERMOD += \
    -I$(USERMOD_DIR)/../../tiny_bclibc/include \
    -I$(USERMOD_DIR) \
    -DTINY_BCLIBC_NO_THREAD_LOCAL \
    -DTINY_BCLIBC_NO_ERR_BUF

# Precision: single by default; override with TINY_BCLIBC_PRECISION=double
ifeq ($(TINY_BCLIBC_PRECISION),double)
# double precision — no extra defines
else
CFLAGS_USERMOD += \
    -DTINY_BCLIBC_SINGLE_PRECISION \
    -DMP_BCLIBC_SINGLE_PRECISION \
    -DTINY_BCLIBC_FAST_ZERO_FIND
endif
