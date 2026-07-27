import sys


def get():
    if hasattr(sys.implementation, "_mpy"):
        version = (
            f"v{sys.implementation._mpy & 0xFF}.{(sys.implementation._mpy >> 8) & 3}"
        )
        return version
    raise Exception("Is not a .mpy implementation")
