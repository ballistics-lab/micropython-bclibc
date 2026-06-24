# sincosf shim (x64 / x86 only)

## What it is

`src/math_shim.c` provides a thin `sincosf` / `sincos` wrapper:

```c
void sincosf(float x, float *s, float *c) { *s = sinf(x); *c = cosf(x); }
void sincos (double x, double *s, double *c) { *s = sin(x); *c = cos(x); }
```

## Why it exists

GCC `-O2` can merge adjacent `sinf(x)` + `cosf(x)` calls into a single
`sincosf(x, &s, &c)` call (a GNU extension).  glibc's `libm` provides
`sincosf`, but it uses IFUNC dispatch internally — a mechanism that cannot
be relocated by `mpy_ld.py`.  fdlibm and musl's `libm_dbl` (both bundled in
MicroPython) do not provide `sincosf` at all.  The shim bridges that gap.

## Why it is not compiled for ARM / RISC-V

With the flags used for MCU targets (`-Os`, no `-ffinite-math-only`, no
`-fno-math-errno`) GCC does not generate `sincosf` calls on ARM or RISC-V.
Adding the shim there is harmless but wastes ~68 B of flash, so it is omitted.

## If you hit an undefined `sincosf` on an MCU target

Add `src/math_shim.c` to the relevant `SRC +=` line in
[Makefile](Makefile), e.g.:

```makefile
else ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc))
SRC += $(_FDLIBM_SRCS) src/mem_shim.c src/math_shim.c
```
