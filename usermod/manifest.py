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

# BCLIBC_BCP=1 (environment): also freeze the ballistic co-processor (BCP)
# application. The same variable switches the C half on in
# micropython.mk/.cmake -- see their own BCLIBC_BCP blocks. Read from the
# environment because makemanifest.py's -v variables are path substitutions
# only; a make command-line BCLIBC_BCP=1 is exported to recipes (and so to
# makemanifest.py) by GNU make itself.
import os

if os.environ.get("BCLIBC_BCP") == "1":
    freeze("../src", "bclibc_bcp.py")
    require("usb-device")
    require("usb-device-cdc")
