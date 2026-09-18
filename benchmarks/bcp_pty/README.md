# BCP latency isolation: unix pty + pure-C harness

Companion investigation to `benchmarks/bcp_wire_bench.py`'s real-hardware
CDC1 numbers (see `BACKLOG.md` Epic 4's "Status at a glance" section for
those: RP2040-Zero +41.7 ms, RP2350 +25.5 ms wire-vs-local overhead for the
same `LOAD_PROFILE` + `INTEGRATE_FAST` request). None of these scripts touch
real hardware or USB at all -- they isolate everything *except* the USB bus
itself, to find out how much of that overhead is explained by
software (framing, MicroPython, the non-blocking retry loop) versus
something specific to real USB/TinyUSB. See `BACKLOG.md` Epic 4's
"CDC1 latency investigation" subsection for the full writeup and numbers;
this file just documents how to run each piece.

All of it runs against a `BCLIBC_BCP=1` **unix port** build (no hardware
needed):

```sh
make -C <micropython>/ports/unix BCLIBC_BCP=1 \
    USER_C_MODULES=<this repo> \
    FROZEN_MANIFEST=<this repo>/usermod/manifest.py
```

## Scripts

- **`local_bench.py`** -- run on-device (`micropython local_bench.py`).
  Calls `_tiny_bclibc.dispatch()` directly, no stream/framing/syscalls at
  all: the pure engine+dispatch baseline, same request shape as
  `bcp_wire_bench.py`.

- **`device_pty_run.py`** / **`host_pty_bench.py`** -- the MicroPython
  `run()` loop driven over a real unix pty instead of USB CDC1, **blocking**
  read (no EAGAIN/retry path exercised). Run:
  `python3 host_pty_bench.py <path-to-micropython-unix-binary> device_pty_run.py [iterations]`

- **`device_pty_run_nb.py`** / **`host_pty_bench_nb.py`** -- same, but the
  pty is opened **non-blocking** (flag set host-side before the device
  process inherits the fd, since the unix port's `os` module has no
  `O_NONBLOCK`/`fcntl`), so `readinto()` genuinely returns `None` and
  exercises `run()`'s real `mp_is_nonblocking_error()` + `mp_hal_delay_ms(1)`
  retry path -- the same C code path real hardware's CDC1 loop uses, just
  woken by a local pty instead of TinyUSB. Takes an optional 4th arg,
  `drip_delay_ms`, to force artificial multi-ms gaps between written bytes
  (for calibrating retry cost under worse conditions than a local pty
  naturally produces). Run:
  `python3 host_pty_bench_nb.py <mpy-bin> device_pty_run_nb.py [iterations] [drip_delay_ms]`

- **`framing_micro_bench.py`** -- run on-device. Isolates `crc16()` /
  `cobs_encode()` / `cobs_decode()` cost alone (no dispatch, no I/O) across
  representative payload sizes (16 B header up to the 1800 B worst-case
  `LOAD_PROFILE`).

- **`pure_c_bcp.c`** / **`host_pty_bench_c.py`** -- a from-scratch **pure C,
  no MicroPython at all** device harness: implements `LOAD_PROFILE`
  (G1/G7 fixed-table only) and `INTEGRATE_FAST` by calling straight into
  `tiny_bclibc.h` (header-only, no separate link step) and a verbatim copy
  of `src/bcp/bcp_frame_mp.h`'s pure-C `crc16`/`cobs_encode`/`cobs_decode`
  core (only the `mp_obj_t` Python-facing wrappers are left out). Blocking
  POSIX `read()`/`write()` on the pty fd, for direct comparison against
  `host_pty_bench.py`'s MicroPython-blocking number. Build:
  ```sh
  gcc -O2 -std=c99 -DTINY_BCLIBC_SINGLE_PRECISION \
      -I<bclibc>/tiny_bclibc/include -I<this repo>/src \
      -o pure_c_bcp pure_c_bcp.c -lm
  ```
  Run: `python3 host_pty_bench_c.py ./pure_c_bcp [iterations]`

## Headline numbers (x64 unix, this session -- see BACKLOG.md for full table)

| variant | avg |
|---|---:|
| local `dispatch()`, no stream | 0.145 ms |
| pty, pure C, blocking | 0.36 ms |
| pty, MicroPython, blocking | 0.42 ms |
| pty, MicroPython, non-blocking (real retry path) | 1.00 ms |
| **real CDC1 wire, RP2350** | **+25.5 ms** |
| **real CDC1 wire, RP2040-Zero** | **+41.7 ms** |

Every local/pty variant is two-plus orders of magnitude below the real
hardware number -- see BACKLOG.md for what that does and doesn't rule out.
