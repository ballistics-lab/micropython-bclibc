# ruff: noqa
# Test firmware manifest — extends manifest.py with the test suite.
# Used only for CI test builds (make rp2040test); NOT for release firmware.
include("manifest.py")
freeze("../tests", "test_bclibc.py")
