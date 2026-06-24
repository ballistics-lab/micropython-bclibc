ARCH    ?= armv6m
MPY_DIR ?= ../../micropython-mod/natmod/micropython

MOD   := _flops_bench_$(ARCH)
SRC   := flops_bench_natmod.c
BUILD := build/$(ARCH)

# ARM soft-float builtins (__mulsf3, __addsf3, etc.) come from newlib via LINK_RUNTIME
ifeq ($(ARCH),$(filter $(ARCH),armv6m armv7m armv7emsp armv7emdp))
LINK_RUNTIME = 1
endif

ifeq ($(wildcard $(MPY_DIR)/py/dynruntime.mk),)
$(error MPY_DIR="$(MPY_DIR)" not found — set MPY_DIR=/path/to/micropython)
endif
include $(MPY_DIR)/py/dynruntime.mk

dist: all
	$(Q)mkdir -p $(BUILD)
	$(Q)mv $(MOD).mpy $(BUILD)/_flops_bench.mpy
	$(ECHO) "  →  $(BUILD)/_flops_bench.mpy"

clean:
	rm -rf build
