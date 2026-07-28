# Reverse of target_tag(): given an architecture name and .mpy ABI version,
# build the raw sys.implementation._mpy-shaped integer. Useful for writing
# manifest "mpy" tags by hand, without needing the real device to hand.
#
# Layout (see py/persistentcode.h and target_tag.py):
#   bits 0-7   version (major)
#   bits 8-9   sub-version (minor)
#   bits 10-13 native arch index
#   bits 16+   optional arch-flags (e.g. RV32 Zba/Zcmp extensions)

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
_ARCH_INDEX = {name: i for i, name in enumerate(_ARCH) if name is not None}


def encode_mpy_tag(arch, abi, arch_flags=0):
    """Build a raw _mpy-shaped int from arch name + abi version.

    arch       - one of _ARCH's names (e.g. "rv32imc"), or None for
                 bytecode-only (arch index 0)
    abi        - "6.3" / "6" (string), or (major, minor) / major (int)
    arch_flags - optional int, only meaningful for archs that use it
                 (currently just RV32's Zba/Zcmp bits)
    """
    if arch is None:
        arch_idx = 0
    elif arch not in _ARCH_INDEX:
        raise ValueError(
            "unknown arch {!r}, expected one of {}".format(arch, sorted(_ARCH_INDEX))
        )
    else:
        arch_idx = _ARCH_INDEX[arch]

    if isinstance(abi, str):
        parts = abi.split(".")
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 else 0
    elif isinstance(abi, (tuple, list)):
        major, minor = (abi + (0,))[:2] if len(abi) < 2 else abi[:2]
    else:
        major, minor = int(abi), 0

    if not (0 <= major <= 0xFF):
        raise ValueError("abi major {} out of range 0-255".format(major))
    if not (0 <= minor <= 3):
        raise ValueError("abi minor {} out of range 0-3".format(minor))

    return major | (minor << 8) | (arch_idx << 10) | (arch_flags << 16)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("usage: encode_mpy_tag.py <arch|none> <abi> [arch_flags]")
        print("example: encode_mpy_tag.py rv32imc 6.3")
        raise SystemExit(1)

    arch_arg = None if sys.argv[1] == "none" else sys.argv[1]
    abi_arg = sys.argv[2]
    flags_arg = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0

    tag = encode_mpy_tag(arch_arg, abi_arg, flags_arg)
    print(tag)
