# RISC-V natmod and picolibc

## Current state

RISC-V (rv32imc / rv64imc) builds use fdlibm instead of `LINK_RUNTIME=1`
due to two bugs in MicroPython's `tools/mpy_ld.py`. Once they are fixed
upstream the Makefile block can be simplified to a single line.

---

## Bugs in mpy_ld.py

### 1. `.srodata` sections not recognised

`load_object_file` only loads sections whose names start with `.rodata`,
`.text`, `.bss`, etc. The RISC-V-specific read-only sections for float
constants — **`.srodata.cst4`** and **`.srodata.cst8`** — are not on the
list. Sections with these names are silently skipped, leaving every symbol
that points into them without a `.section` attribute.

Result with `LINK_RUNTIME=1`:
```
AttributeError: 'Symbol' object has no attribute 'section'
```

Fix — one line:
```diff
-elif s.name.startswith((".literal", ".text", ".rodata", ".data.rel.ro", ".bss")):
+elif s.name.startswith((".literal", ".text", ".rodata", ".srodata", ".data.rel.ro", ".bss")):
```

### 2. Absolute `R_RISCV_LO12_I/S` not handled

`process_riscv32_relocation` handles `LO12_I/S` and `PCREL_LO12_I/S` with
the same parent-lookup logic: it searches `s.section.reloc` for the matching
`HI20` instruction. This is correct for the PCREL variant (where the symbol
points to the `HI20` instruction in `.text`), but wrong for the absolute
variant used by picolibc (where the symbol points directly to data in
`.srodata`). The lookup finds nothing and hits `assert 0`.

Fix — split the two cases:
```diff
-        if parent is None:
-            assert 0, r
         addr = s.section.addr + s["st_value"]
-        reloc = parent.computed_reloc
+        if parent is not None:
+            reloc = parent.computed_reloc
+        elif r_info_type in (R_RISCV_LO12_I, R_RISCV_LO12_S):
+            reloc = addr + r_addend   # address is fully known from the symbol
+        else:
+            assert 0, r               # PCREL without a parent is a real error
```

Full patch: [mpy_ld_srodata.patch](patches/micropython/mpy_ld_srodata.patch)

---

## Why ARM is not affected

newlib's `libm.a` stores float constants in plain `.rodata` sections.
`.srodata` is a RISC-V-specific GCC optimisation for the "small data" area
and does not appear in ARM object files.

---

## Reproducer

The bug is only triggered when math functions are called with **runtime
(non-constant) arguments**. A compile-time constant like `sinf(1.0f)` is
folded by GCC, leaving no undefined symbol in the object file and no archive
object to load — which is why a trivial hello-world reproducer works fine.

```c
static mp_obj_t hello(mp_obj_t x_obj) {
    float x = mp_obj_get_float(x_obj);   // runtime value
    return mp_obj_new_float(
        sinf(x) + cosf(x) + atan2f(x, 0.5f) + expf(x) + powf(x, 2.0f)
    );
}
```

```
make ARCH=rv32imc MICROPY_FLOAT_IMPL=float
→ AttributeError: 'Symbol' object has no attribute 'section'
```

---

## When the upstream patch lands

Replace the workaround block in the Makefile:

```makefile
# CURRENT WORKAROUND:
else ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc))
SRC          += $(_FDLIBM_SRCS) src/math_shim.c src/mem_shim.c
CFLAGS_EXTRA += $(_FDLIBM_FLAGS)
```

with:

```makefile
# AFTER PATCH:
else ifeq ($(ARCH),$(filter $(ARCH),rv32imc rv64imc))
LINK_RUNTIME  = 1
```

Also remove the post-include `MPY_LD_FLAGS += libgcc` block.

Text size: fdlibm ~35 500 B → picolibc ~33 900 B (−1.6 KB).

---

## References

- Issue: https://github.com/micropython/micropython/issues/19364
- Patch: [mpy_ld_srodata.patch](mpy_ld_srodata.patch)
