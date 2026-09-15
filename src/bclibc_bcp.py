"""bclibc_bcp — ballistic co-processor (BCP) application (BCLIBC_BCP builds only).

Frozen into the firmware only when built with BCLIBC_BCP=1, which also
compiles the native module with BCLIBC_BCP defined (see usermod/manifest.py
and usermod/micropython.mk/.cmake). Placeholder for now: the command
protocol, transport and worker (BACKLOG.md epics 3-8) land here.
"""

# ImportError here means the .py half was frozen without the C half (e.g. a
# stale Make object built before BCLIBC_BCP was switched on).
from _tiny_bclibc import BCP  # noqa: F401
