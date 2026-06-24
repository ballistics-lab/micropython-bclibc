"""CPython shim for MicroPython uctypes — subset needed by tiny_bclibc_mp_ffi.

Encoding mirrors moductypes.c (extmod):
  descriptor value = (type_id << _TS) | byte_offset
  type bits in [31:28], offset bits in [27:0].

Supported:
  - scalar constants: UINT8/16/32/64, INT8/16/32/64, FLOAT32/64, VOID
  - layout constants: LITTLE_ENDIAN, BIG_ENDIAN, NATIVE
  - addressof(buf)  — memory address of bytearray / array.array
  - struct(addr, descriptor, layout)  — typed field access over raw memory
"""

import array as _array
import ctypes as _ct
import struct as _st

LITTLE_ENDIAN = 0
BIG_ENDIAN = 1
NATIVE = 2

# Type id occupies top 4 bits of a 32-bit descriptor word.
_TS = 28
_MASK = (1 << _TS) - 1  # offset mask (bits 0-27)

UINT8 = 0 << _TS
INT8 = 1 << _TS
UINT16 = 2 << _TS
INT16 = 3 << _TS
UINT32 = 4 << _TS
INT32 = 5 << _TS
UINT64 = 6 << _TS
INT64 = 7 << _TS
FLOAT32 = 14 << _TS
FLOAT64 = 15 << _TS
VOID = UINT8

# type_id -> (struct format char, byte size)
_TYPE = {
    0: ("B", 1),  # UINT8
    1: ("b", 1),  # INT8
    2: ("H", 2),  # UINT16
    3: ("h", 2),  # INT16
    4: ("I", 4),  # UINT32
    5: ("i", 4),  # INT32
    6: ("Q", 8),  # UINT64
    7: ("q", 8),  # INT64
    14: ("f", 4),  # FLOAT32
    15: ("d", 8),  # FLOAT64
}


def addressof(obj):
    """Return the integer memory address of a buffer object."""
    if isinstance(obj, _array.array):
        return obj.buffer_info()[0]
    return _ct.addressof((_ct.c_char * len(obj)).from_buffer(obj))


class struct:
    """Typed view over a raw memory region described by a uctypes descriptor dict.

    Descriptor format (same as MicroPython):
      {"field": TYPE | offset}           -- scalar at byte offset
      {"field": (offset, sub_desc)}      -- nested struct
    """

    __slots__ = ("_a", "_d", "_p")  # base address, descriptor dict, endian prefix

    def __init__(self, addr, desc, layout=NATIVE):
        object.__setattr__(self, "_a", int(addr))
        object.__setattr__(self, "_d", desc)
        pfx = "<" if layout == LITTLE_ENDIAN else ">" if layout == BIG_ENDIAN else "="
        object.__setattr__(self, "_p", pfx)

    def _layout(self):
        p = object.__getattribute__(self, "_p")
        return LITTLE_ENDIAN if p == "<" else BIG_ENDIAN if p == ">" else NATIVE

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_d")
        try:
            v = d[name]
        except KeyError:
            raise AttributeError(name)
        addr = object.__getattribute__(self, "_a")
        if isinstance(v, tuple):
            off, sub = v
            return struct(addr + off, sub, self._layout())
        tid = (v >> _TS) & 0xF
        off = v & _MASK
        ch, sz = _TYPE[tid]
        pfx = object.__getattribute__(self, "_p")
        raw = bytes((_ct.c_char * sz).from_address(addr + off))
        return _st.unpack(pfx + ch, raw)[0]

    def __setattr__(self, name, value):
        d = object.__getattribute__(self, "_d")
        try:
            v = d[name]
        except KeyError:
            raise AttributeError(name)
        if isinstance(v, tuple):
            raise AttributeError(f"cannot assign to nested struct '{name}'")
        tid = (v >> _TS) & 0xF
        off = v & _MASK
        ch, sz = _TYPE[tid]
        pfx = object.__getattribute__(self, "_p")
        addr = object.__getattribute__(self, "_a")
        _ct.memmove(addr + off, _st.pack(pfx + ch, value), sz)
