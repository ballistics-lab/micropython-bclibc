import ctypes

_M = {
    "b": ctypes.c_byte,
    "B": ctypes.c_ubyte,
    "h": ctypes.c_short,
    "H": ctypes.c_ushort,
    "i": ctypes.c_int,
    "I": ctypes.c_uint,
    "l": ctypes.c_long,
    "L": ctypes.c_ulong,
    "q": ctypes.c_longlong,
    "Q": ctypes.c_ulonglong,
    "f": ctypes.c_float,
    "d": ctypes.c_double,
    "v": None,
    "p": ctypes.c_void_p,
    "P": ctypes.c_void_p,
    "s": ctypes.c_char_p,
}


class _F:
    def __init__(self, lh, n, rt, at):
        self.f = getattr(lh, n)
        self.f.argtypes = [_M[x] for x in at]
        self.f.restype = _M[rt]

    def __call__(self, *args):
        p = []
        for a in args:
            if isinstance(a, (bytes, bytearray)):
                p.append(ctypes.addressof(ctypes.c_char.from_buffer(a)))
            else:
                p.append(a)
        return self.f(*p)


class _Mod:
    def __init__(self, path):
        self._h = ctypes.CDLL(path)

    def func(self, rt, n, at):
        return _F(self._h, n, rt, at)


def open(path):
    return _Mod(path)
