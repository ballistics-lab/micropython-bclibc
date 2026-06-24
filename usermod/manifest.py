# ruff: noqa
# Freeze tiny_bclibc.py (Python API wrapper) into the firmware image.
# Pass to the port build via FROZEN_MANIFEST= (make) or --manifest (cmake).
#
# For port-specific builds (rp2, esp32, qemu) include the board's default
# manifest so that _boot.py and other standard frozen scripts are preserved.
# For unix port builds (FROZEN_MANIFEST is used for test purposes only) the
# include is a no-op because $(PORT_DIR)/boards/manifest.py doesn't exist.
try:
    include("$(PORT_DIR)/boards/manifest.py")
except Exception:
    pass

freeze("../src", "tiny_bclibc.py")
