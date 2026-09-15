"""Same as host_pty_bench.py, but spawns the pure-C `pure_c_bcp` binary
(program, slave_path) instead of the MicroPython [mpy_bin, script, path]
invocation -- everything else (pty setup, raw-mode tty, wire client) is
identical, for an apples-to-apples comparison."""
import fcntl
import os
import pty
import struct
import subprocess
import sys
import termios
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bcp_wire_bench as wb  # noqa: E402


class PtyMaster:
    def __init__(self, fd):
        self.fd = fd
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    @property
    def in_waiting(self):
        buf = fcntl.ioctl(self.fd, termios.FIONREAD, struct.pack("i", 0))
        return struct.unpack("i", buf)[0]

    def read(self, n):
        try:
            return os.read(self.fd, max(n, 1))
        except BlockingIOError:
            return b""
        except OSError:
            return b""

    def write(self, data):
        return os.write(self.fd, data)


def main():
    c_bin = sys.argv[1]
    iterations = int(sys.argv[2]) if len(sys.argv) > 2 else 200

    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)

    tty_attrs = termios.tcgetattr(slave_fd)
    tty_attrs[0] = 0
    tty_attrs[1] = 0
    tty_attrs[3] = 0
    tty_attrs[2] = (tty_attrs[2] & ~termios.CSIZE) | termios.CS8
    termios.tcsetattr(slave_fd, termios.TCSANOW, tty_attrs)

    proc = subprocess.Popen([c_bin, slave_path], stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)
    os.close(slave_fd)

    ser = PtyMaster(master_fd)
    reader = wb.FrameReader(ser)
    time.sleep(0.2)

    try:
        ser.write(wb.build_frame(wb.CMD_LOAD_PROFILE, 0, 0, wb.pack_profile()))
        type_, seq, status, payload = reader.next_frame(time.time() + 5.0)
        assert type_ == (wb.CMD_LOAD_PROFILE | 0x80) and status == wb.STATUS_OK, (type_, status, payload)
        print("LOAD_PROFILE OK")

        times = []
        for i in range(iterations):
            dt, total, reason = wb.run_once(ser, reader)
            times.append(dt)

        avg = sum(times) / len(times)
        print()
        print(f"INTEGRATE_FAST over unix pty, PURE C (no MicroPython), 1 km/10 m steps, {iterations} iterations:")
        print(f"  avg={avg * 1000:.3f} ms  min={min(times) * 1000:.3f} ms  max={max(times) * 1000:.3f} ms")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master_fd)


if __name__ == "__main__":
    main()
