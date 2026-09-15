# MicroPython (unix, BCLIBC_BCP=1) — device side of the pty benchmark.
# Opens the pty slave path (argv[1]) as one duplex stream and hands it to
# _tiny_bclibc.run(), exactly as bclibc_bcp.start(cdc1) does with a real
# CDCInterface -- only the transport object differs.
import sys

import _tiny_bclibc as bc

path = sys.argv[1]
f = open(path, "rb+", buffering=0)
bc.run(f)
