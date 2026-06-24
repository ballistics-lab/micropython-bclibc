#!/usr/bin/env python3
"""Run tiny_bclibc test suite on MicroPython QEMU.

Usage:
  python3 ci/run_qemu.py <firmware.elf> <natmod-dir> [--machine MACHINE] [--qemu-extra ARGS]

<natmod-dir> must contain:
  _tiny_bclibc.mpy  — native module built for the target architecture
  tiny_bclibc.mpy   — bytecode wrapper (compiled from src/tiny_bclibc.py)
  test_bclibc.py    — test suite

Examples:
  # Cortex-M3 (armv7m)
  python3 natmod/ci/run_qemu.py firmware.elf tests/

  # Cortex-M0 / nRF51 (armv6m)
  python3 natmod/ci/run_qemu.py firmware.elf tests/ \\
    --machine microbit \\
    --qemu-extra "-global nrf51-soc.flash-size=1048576 -global nrf51-soc.sram-size=262144"
"""

import sys
import os
import argparse

# pyboard.py lives in MicroPython's tools/ directory.
# MPY_DIR env var (set in CI) takes precedence over the local default.
_HERE = os.path.dirname(os.path.abspath(__file__))
_MPY_ROOT = os.environ.get("MPY_DIR") or os.path.join(_HERE, "..", "..", "micropython")
sys.path.insert(0, os.path.join(_MPY_ROOT, "tools"))

from pyboard import Pyboard  # noqa: E402


def read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def inject_modules(native_mpy: bytes, wrapper_mpy: bytes) -> bytes:
    """Mount _tiny_bclibc.mpy (native) and tiny_bclibc.mpy (bytecode) from RAM buffers."""
    native_repr = repr(native_mpy).encode()
    wrapper_repr = repr(wrapper_mpy).encode()
    return (
        b"import sys, io, vfs\n"
        b"__native = " + native_repr + b"\n"
        b"__wrapper = " + wrapper_repr + b"\n"
        b"class _F(io.IOBase):\n"
        b"  def __init__(self,d): self.d=d; self.off=0\n"
        b"  def ioctl(self,r,a): return 0 if r==4 else -1\n"
        b"  def readinto(self,b):\n"
        b"    b[:]=memoryview(self.d)[self.off:self.off+len(b)]\n"
        b"    self.off+=len(b); return len(b)\n"
        b"class _FS:\n"
        b"  def mount(self,r,m): pass\n"
        b"  def chdir(self,p): pass\n"
        b"  def stat(self,p):\n"
        b"    if p in ('/_tiny_bclibc.mpy','/tiny_bclibc.mpy'): return (0,)*10\n"
        b"    raise OSError(-2)\n"
        b"  def open(self,p,m):\n"
        b"    return _F(__native if '_tiny_bclibc' in p else __wrapper)\n"
        b"vfs.mount(_FS(),'/__remote')\n"
        b"sys.path.insert(0,'/__remote')\n"
        b"import _tiny_bclibc\n"
        b"import tiny_bclibc\n"
        b"del __native,__wrapper\n"
        b"import gc;gc.collect()\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("firmware", help="Path to firmware.elf")
    ap.add_argument(
        "natmod_dir",
        help="Directory with _tiny_bclibc.mpy / tiny_bclibc.mpy / test_bclibc.py",
    )
    ap.add_argument(
        "--machine",
        default="mps2-an385",
        help="QEMU -machine value (default: mps2-an385)",
    )
    ap.add_argument(
        "--qemu-extra", default="", help="Extra QEMU arguments inserted before -serial"
    )
    args = ap.parse_args()

    native_data = read_file(os.path.join(args.natmod_dir, "_tiny_bclibc.mpy"))
    wrapper_data = read_file(os.path.join(args.natmod_dir, "tiny_bclibc.mpy"))
    test_src = read_file(os.path.join(args.natmod_dir, "test_bclibc.py"))

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

    print("[QEMU] Injecting _tiny_bclibc.mpy + tiny_bclibc.mpy ...", flush=True)
    pyb.exec_(inject_modules(native_data, wrapper_data), timeout=30)

    print("[QEMU] Running test_bclibc.py ...", flush=True)
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
