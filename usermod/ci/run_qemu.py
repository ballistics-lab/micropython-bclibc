#!/usr/bin/env python3
"""Run tiny_bclibc test suite on a MicroPython QEMU usermod firmware.

The C module (_tiny_bclibc) and the Python wrapper (tiny_bclibc.py) are baked
into the firmware at build time via USER_C_MODULES + FROZEN_MANIFEST, so no
.mpy injection is needed — unlike the natmod equivalent.

Usage:
  python3 ci/run_qemu.py <firmware.elf> <tests_dir> [--machine MACHINE]

Example (Cortex-M3):
  python3 usermod/ci/run_qemu.py \\
    $MPY_DIR/ports/qemu/build-MPS2_AN385/firmware.elf \\
    tests/
"""

import sys
import os
import argparse

_HERE = os.path.dirname(os.path.abspath(__file__))
_MPY_ROOT = os.environ.get("MPY_DIR")
if not _MPY_ROOT:
    if os.path.exists("/mpy/tools"):
        _MPY_ROOT = "/mpy"
    else:
        _MPY_ROOT = os.path.join(_HERE, "..", "..", "..", "micropython")
sys.path.insert(0, os.path.join(_MPY_ROOT, "tools"))

from pyboard import Pyboard  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("firmware", help="Path to firmware.elf")
    ap.add_argument(
        "tests_dir",
        help="Directory containing test_bclibc.py",
    )
    ap.add_argument(
        "--machine",
        default="mps2-an385",
        help="QEMU -machine value (default: mps2-an385)",
    )
    ap.add_argument(
        "--qemu-extra", default="", help="Extra QEMU arguments before -serial"
    )
    args = ap.parse_args()

    with open(os.path.join(args.tests_dir, "test_bclibc.py"), "rb") as f:
        test_src = f.read()

    extra = f" {args.qemu_extra}" if args.qemu_extra else ""
    qemu_cmd = (
        f"qemu-system-arm "
        f"-machine {args.machine} "
        f"-nographic "
        f"-monitor null "
        f"-semihosting"
        f"{extra} "
        f"-serial pty "
        f"-kernel {args.firmware}"
    )

    print(f"[QEMU] Starting: {qemu_cmd}", flush=True)
    pyb = Pyboard(f"execpty:{qemu_cmd}")
    pyb.enter_raw_repl()

    print("[QEMU] Running test_bclibc.py (module baked in) ...", flush=True)
    output = pyb.exec_(test_src, timeout=120)

    pyb.exit_raw_repl()
    pyb.close()

    text = output.decode("utf-8", errors="replace")
    print(text)

    if "FAIL" in text:
        print("[QEMU] RESULT: FAILED", file=sys.stderr)
        sys.exit(1)

    print("[QEMU] RESULT: ALL PASSED")


if __name__ == "__main__":
    main()
