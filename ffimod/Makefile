# ffimod/Makefile
#
#   make            → x64_dp (default)
#   make x64        → build/x64_dp/tiny_bclibc.so + Python files
#   make x86        → build/x86_dp/tiny_bclibc.so + Python files
#   make aarch64    → build/aarch64_dp/tiny_bclibc.so + Python files
#   make all        → all three

THIS_DIR  := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BCLIBC    := $(abspath $(THIS_DIR)/../bclibc)
TINY_SRC  := $(BCLIBC)/tiny_bclibc/src/tiny_bclibc_impl.c
TINY_INC  := $(BCLIBC)/tiny_bclibc/include
SRC_PY    := $(abspath $(THIS_DIR)/../src/tiny_bclibc.py)
_BUILD    := $(THIS_DIR)/build

CFLAGS    := -O2 -shared -fPIC -DTINY_BCLIBC_BUILD_SHARED -I$(TINY_INC)

_PY_FILES := $(wildcard $(THIS_DIR)/*.py)

.PHONY: all x64 x86 aarch64 clean

all: x64 x86 aarch64

# $(1) = build subdir  (e.g. x64_dp)
# $(2) = CC prefix     (e.g. aarch64-linux-gnu-)
# $(3) = extra CFLAGS  (e.g. -m32)
define ffimod_target
.PHONY: $(1)
$(1): $(_BUILD)/$(1)/tiny_bclibc.so $(_BUILD)/$(1)/.py_stamp

$(_BUILD)/$(1)/tiny_bclibc.so: $(TINY_SRC)
	@mkdir -p $$(@D)
	$(2)gcc $(CFLAGS) $(3) -o $$@ $$<

$(_BUILD)/$(1)/.py_stamp: $(_PY_FILES) $(SRC_PY)
	@mkdir -p $(_BUILD)/$(1)
	cp $(_PY_FILES) $(_BUILD)/$(1)/
	cp $(SRC_PY) $(_BUILD)/$(1)/tiny_bclibc.py
	@touch $$@
endef

$(eval $(call ffimod_target,x64_dp,,))
$(eval $(call ffimod_target,x86_dp,,-m32))
$(eval $(call ffimod_target,aarch64_dp,aarch64-linux-gnu-,))

x64:    x64_dp
x86:    x86_dp
aarch64: aarch64_dp

clean:
	rm -rf $(_BUILD)
