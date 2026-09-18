"""
Non-blocking variant of host_pty_bench.py: sets O_NONBLOCK on the pty slave
fd *before* spawning the device process, and passes that exact fd as both
stdin and stdout (dup2'd from the same open file description, so the flag
applies to both directions) -- so device_pty_run_nb.py's readinto() really
hits "no data yet" -> None -> run()'s own mp_hal_delay_ms(1) retry path,
instead of blocking in the read() syscall like the plain pty bench did.

This measures the real cost of run()'s own non-blocking retry loop on a
transport with no USB/TinyUSB involved at all, to test the hypothesis that
that retry loop (not USB itself, not COBS/CRC) is what accounts for most of
the 25-42 ms real-hardware CDC1 overhead.
"""

import fcntl
import os
import pty
import signal
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
    drip_delay_ms = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0  # artificial gap between write() chunks

    master_fd, slave_fd = pty.openpty()

    tty_attrs = termios.tcgetattr(slave_fd)
    tty_attrs[0] = 0
    tty_attrs[1] = 0
    tty_attrs[3] = 0
    tty_attrs[2] = (tty_attrs[2] & ~termios.CSIZE) | termios.CS8
    termios.tcsetattr(slave_fd, termios.TCSANOW, tty_attrs)

    # Make the *slave* fd non-blocking before the child inherits it -- the
    # O_NONBLOCK flag lives on the open file description, so both the
    # child's dup'd stdin (fd 0) and stdout (fd 1) share it.
    fl = fcntl.fcntl(slave_fd, fcntl.F_GETFL)
    fcntl.fcntl(slave_fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

    fl_m = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, fl_m | os.O_NONBLOCK)

    proc = subprocess.Popen(
        [mpy_bin, device_script],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=sys.stderr,
    )
    os.close(slave_fd)

    ser = PtyMaster(master_fd)

    def write_maybe_dripped(data):
        if drip_delay_ms <= 0:
            ser.write(data)
            return
        for b in data:
            ser.write(bytes([b]))
            time.sleep(drip_delay_ms / 1000.0)

    reader = wb.FrameReader(ser)
    time.sleep(0.2)

    try:
        write_maybe_dripped(wb.build_frame(wb.CMD_LOAD_PROFILE, 0, 0, wb.pack_profile()))
        type_, seq, status, payload = reader.next_frame(time.time() + 5.0)
        assert type_ == (wb.CMD_LOAD_PROFILE | 0x80) and status == wb.STATUS_OK, (type_, status, payload)
        print("LOAD_PROFILE OK")

        times = []
        for i in range(iterations):
            t0 = time.perf_counter()
            write_maybe_dripped(wb.build_frame(wb.CMD_INTEGRATE_FAST, i + 1, 0, wb.pack_integrate_1km()))
            while True:
                type_, seq, status, payload = reader.next_frame(time.time() + 5.0)
                if type_ != (wb.CMD_INTEGRATE_FAST | 0x80):
                    continue
                if status == wb.STATUS_OK:
                    break
                elif status != wb.STATUS_MORE:
                    raise RuntimeError(f"unexpected status {status}")
            times.append(time.perf_counter() - t0)

        avg = sum(times) / len(times)
        print()
        tag = f"drip={drip_delay_ms}ms/byte" if drip_delay_ms > 0 else "instant write"
        print(f"INTEGRATE_FAST over NON-BLOCKING unix pty ({tag}), 1 km/10 m steps, {iterations} iterations:")
        print(f"  avg={avg * 1000:.3f} ms  min={min(times) * 1000:.3f} ms  max={max(times) * 1000:.3f} ms")
    finally:
        proc.send_signal(signal.SIGINT)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master_fd)


if __name__ == "__main__":
    main()
