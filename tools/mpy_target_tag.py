# Determine this device's native-code target: architecture + MicroPython
# .mpy ABI version, decoded from sys.implementation._mpy.
#
# Layout of sys.implementation._mpy (see py/persistentcode.h):
#   bits 0-7   version (major)
#   bits 8-9   sub-version (minor)
#   bits 10-13 native arch index
#   bits 16+   optional arch-flags (e.g. RV32 Zba/Zcmp extensions)

import sys

# Index must match py/persistentcode.h MP_NATIVE_ARCH_* ordering (0 = NONE).
_ARCH = (
    None,
    "x86",
    "x64",
    "armv6",
    "armv6m",
    "armv7m",
    "armv7em",
    "armv7emsp",
    "armv7emdp",
    "xtensa",
    "xtensawin",
    "rv32imc",
    "rv64imc",
)


def target_tag():
    """Return a dict describing this device's native-code target.

    Returns None if this build can't load persistent .mpy at all
    (sys.implementation has no _mpy field) - natmod install/matching
    doesn't apply here.
    """
    mpy = getattr(sys.implementation, "_mpy", None)
    if mpy is None:
        return None

    return {
        "arch": _ARCH[(mpy >> 10) & 0x0F],
        "abi_major": mpy & 0xFF,
        "abi_minor": (mpy >> 8) & 3,
        "arch_flags": mpy >> 16,  # 0 unless the arch uses extension flags (e.g. RV32)
        "byteorder": sys.byteorder,
        "build": getattr(sys.implementation, "_build", None),  # 1.25+, port-dependent
        "mpy_raw": mpy,  # the raw int, if you need it directly
    }


if __name__ == "__main__":
    info = target_tag()
    if info is None:
        print("This build has no persistent .mpy support (no sys.implementation._mpy).")
    else:
        print("arch:       {arch}".format(**info))
        print("abi:        {abi_major}.{abi_minor}".format(**info))
        print("arch_flags: {arch_flags:#x}".format(**info))
        print("byteorder:  {byteorder}".format(**info))
        print("build:      {build}".format(**info))
        print("mpy (raw):  {mpy_raw}".format(**info))
