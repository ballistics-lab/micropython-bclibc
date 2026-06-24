/* mem_shim.c — memory + errno shims for all natmod targets.
 *
 * memset/memcpy: forwarded through mp_fun_table (indices 50-51, dynruntime.h)
 * instead of compiling the host libc — the fun_table approach works equally on
 * x64 (host), ARM, Xtensa, and RISC-V because every MicroPython binary exposes it.
 *
 * __errno / __errno_location: newlib (ARM/RISC-V) pulls these in from libc.a
 * when wf_exp.o / wf_pow.o / wf_sqrt.o error wrappers are linked.  We cannot
 * provide a static/global int for errno because natmods require BSS=0.
 * Instead we allocate a throwaway 4-byte cell on the MicroPython heap; the
 * caller writes errno there and immediately discards the pointer — we never
 * read it back.  The allocation is tiny and is freed by the GC. */

#include "py/dynruntime.h"
#include <stddef.h>

void *memset(void *dest, int c, size_t n)
{
    return mp_fun_table.memset_(dest, c, n);
}

void *memcpy(void *dest, const void *src, size_t n)
{
    return mp_fun_table.memmove_(dest, src, n);
}

/* newlib errno accessor (arm-none-eabi, riscv-elf toolchains) */
int *__errno(void)
{
    return (int *)m_malloc(sizeof(int));
}

/* glibc errno accessor (x64/x86 host toolchain) */
int *__errno_location(void)
{
    return (int *)m_malloc(sizeof(int));
}
