# MicroPython (unix, BCLIBC_BCP=1) -- device side, NON-BLOCKING variant.
# stdin/stdout are dup()s of the same pty slave fd, opened O_NONBLOCK by the
# host before spawning (unix MicroPython has no os.open()/fcntl, so the
# flag must be set from outside). readinto() on a non-blocking FileIO here
# returns None on "no data yet", matching CDCInterface's own contract --
# confirmed directly, no OSError/EAGAIN wrapping needed. This exercises the
# exact same run()/mp_hal_delay_ms(1) retry path real hardware uses, on the
# same unix binary as local_bench.py / device_pty_run.py.
import io
import sys

import _tiny_bclibc as bc

retry_count = 0


class DuplexNB(io.IOBase):
    def __init__(self, r, w):
        self.r = r
        self.w = w

    def readinto(self, buf):
        global retry_count
        n = self.r.readinto(buf)
        if n is None:
            retry_count += 1
        return n

    def write(self, buf):
        return self.w.write(buf)

    def ioctl(self, req, arg):
        return 0


stream = DuplexNB(sys.stdin.buffer, sys.stdout.buffer)
try:
    bc.run(stream)
except KeyboardInterrupt:
    pass
finally:
    sys.stderr.write("retry_count={}\n".format(retry_count))
