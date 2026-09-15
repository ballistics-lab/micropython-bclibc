"""bclibc_bcp — ballistic co-processor (BCP) application (BCLIBC_BCP builds only).

Frozen into the firmware only when built with BCLIBC_BCP=1, which also
compiles the native module with BCLIBC_BCP defined (see usermod/manifest.py
and usermod/micropython.mk/.cmake).

Stays thin plumbing on purpose (BACKLOG.md Epic 1's "Entry point" bullet,
Epic 3's "implementation language is C" resolution): this module only
constructs/configures the transport object, then hands it to
`_tiny_bclibc.run()`, which owns the whole read/decode/dispatch/write loop
natively -- no per-frame trip back into Python bytecode. See
`src/bcp/bcp_dispatch_mp.h`'s own `run(stream)` doc comment for the loop
itself, and `tests/test_bcp_run_native.py` for how it is exercised without
real hardware.

`start(cdc1)` runs `_tiny_bclibc.run(cdc1)` directly on the calling
thread/core, so it does not return under normal operation (it ends only if
the transport itself breaks, or -- observed during this module's own
hardware bring-up -- if a `Ctrl-C`/raw-REPL entry attempt on CDC0 raises
`KeyboardInterrupt` into it via the same event-poll hook `run()`'s
non-blocking-read retry path calls). Calling `start()` straight from a
frozen `main.py` therefore blocks the CDC0 REPL for as long as it runs --
running it on a second core/thread instead (Epic 7, so that CDC1 traffic
never blocks CDC0) is not implemented yet, so `main.py` does not call this
automatically. Until then, start it explicitly, e.g. from the REPL itself:

    import usb.device
    from usb.device.cdc import CDCInterface
    import bclibc_bcp

    cdc1 = CDCInterface()
    cdc1.init(timeout=0, txbuf=2048, rxbuf=2048)
    usb.device.get().init(cdc1, builtin_driver=True)
    bclibc_bcp.start(cdc1)

`txbuf`/`rxbuf` must be at least 2048 -- matching PROTOCOL.md/Epic 3's own
RX-buffer sizing (`LOAD_PROFILE`'s worst case, a 200-point `CUSTOM` drag
table, is ~1.6 KB). `CDCInterface`'s own *default* is `txbuf=256`, which
is not big enough: a plain `INTEGRATE` response row is the full native
`TrajectoryData` (64 B on an SP build), so even one *unmodified*
`BCP_STREAM_ROWS_PER_FRAME=8` batch (`4 + 8*64 = 516 B`) already exceeds
it. Found the hard way during this project's own hardware bring-up: with
the default `txbuf`, `write()`'s non-blocking retry loop spins without
ever pumping TinyUSB (`mp_event_handle_nowait()` only runs once, after
the whole write already finished), so the ring buffer never drains and
the call hangs -- not a wire or protocol issue, purely an under-sized
buffer. `INTEGRATE_FAST`'s thinner 16 B rows (`4 + 8*16 = 132 B`) happen
to fit under 256 B, which is why this stayed hidden until `INTEGRATE`
itself was finally exercised over a real transport (see BACKLOG.md
Epic 5's own writeup on this).
"""

# ImportError here means the .py half was frozen without the C half (e.g. a
# stale Make object built before BCLIBC_BCP was switched on).
from _tiny_bclibc import BCP, run  # noqa: F401


def start(stream):
    """Run the BCP dispatch loop against `stream` (e.g. a CDC1
    `CDCInterface`). Never returns under normal operation -- see this
    module's own docstring."""
    run(stream)
