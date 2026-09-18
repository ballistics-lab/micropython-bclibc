"""
BCP wire-round-trip benchmark over a Unix pty instead of real USB CDC1.

Same request shape / same wire codec as benchmarks/bcp_wire_bench.py (COBS +
CRC16/CCITT-FALSE, LOAD_PROFILE then INTEGRATE_FAST, 1 km/10 m steps) -- only
the transport differs: a local pty pair instead of a real USB serial device,
and the "device" side is the same BCLIBC_BCP=1 unix build running
`_tiny_bclibc.run()` against the pty slave, instead of real firmware on real
hardware. This isolates protocol/dispatch overhead from anything USB- or
TinyUSB-specific (bus scheduling, endpoint buffering, mpremote/host driver
stack) -- if the pty overhead is close to the real CDC1 overhead, the cost is
in the protocol/round-trips; if it's much smaller, USB itself is a real
contributor.

Usage:
    python3 host_pty_bench.py <path-to-micropython-unix-binary> <path-to-device_pty_run.py> [iterations]
"""

import fcntl
import os
import pty
import struct
import subprocess
import sys
import termios
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bcp_wire_bench as wb  # noqa: E402  (crc16/cobs/build_frame/parse_frame/pack_*/FrameReader)


class PtyMaster:
    """Minimal pyserial-`Serial`-shaped adapter over a raw pty master fd, so
    bcp_wire_bench.FrameReader (written against pyserial) can drive it
    unmodified."""

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
    mpy_bin = sys.argv[1]
    device_script = sys.argv[2]
    iterations = int(sys.argv[3]) if len(sys.argv) > 3 else 200

    master_fd, slave_fd = pty.openpty()
    slave_path = os.ttyname(slave_fd)

    # Raw mode: a pty defaults to line-discipline/cooked-mode tty behaviour
    # (echo, CR/LF translation, 0x00/0x04 special handling) inherited from
    # the controlling terminal's defaults -- fatal for a binary COBS stream
    # (frames are 0x00-delimited). Must disable that before the device
    # process opens its end.
    tty_attrs = termios.tcgetattr(slave_fd)
    tty_attrs[0] = 0  # iflag
    tty_attrs[1] = 0  # oflag
    tty_attrs[3] = 0  # lflag (disables ECHO, ICANON, ISIG, IEXTEN)
    tty_attrs[2] = (tty_attrs[2] & ~termios.CSIZE) | termios.CS8
    termios.tcsetattr(slave_fd, termios.TCSANOW, tty_attrs)

    proc = subprocess.Popen(
        [mpy_bin, device_script, slave_path],
        stdin=subprocess.DEVNULL,
        stdout=sys.stderr,  # let device-side prints/tracebacks surface for debugging
        stderr=sys.stderr,
    )
    os.close(slave_fd)  # host doesn't need the slave end once the child has it open

    ser = PtyMaster(master_fd)
    reader = wb.FrameReader(ser)
    time.sleep(0.2)  # let the device process reach open()+run()

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
        print(f"INTEGRATE_FAST over unix pty (no USB), 1 km/10 m steps, {iterations} iterations:")
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
