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
    cdc1.init(timeout=0)
    usb.device.get().init(cdc1, builtin_driver=True)
    bclibc_bcp.start(cdc1)
"""

# ImportError here means the .py half was frozen without the C half (e.g. a
# stale Make object built before BCLIBC_BCP was switched on).
from _tiny_bclibc import BCP, run  # noqa: F401


def start(stream):
    """Run the BCP dispatch loop against `stream` (e.g. a CDC1
    `CDCInterface`). Never returns under normal operation -- see this
    module's own docstring."""
    run(stream)
