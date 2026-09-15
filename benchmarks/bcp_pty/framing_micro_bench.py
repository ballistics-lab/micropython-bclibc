import time
import _tiny_bclibc as bc

for size in (16, 130, 516, 1800):
    payload = bytes((i % 256) for i in range(size))
    N = 5000

    t0 = time.ticks_us()
    for _ in range(N):
        c = bc.crc16(payload)
    t_crc = time.ticks_diff(time.ticks_us(), t0) / N

    t0 = time.ticks_us()
    for _ in range(N):
        enc = bc.cobs_encode(payload)
    t_enc = time.ticks_diff(time.ticks_us(), t0) / N

    t0 = time.ticks_us()
    for _ in range(N):
        dec = bc.cobs_decode(enc)
    t_dec = time.ticks_diff(time.ticks_us(), t0) / N

    print("payload={:5d}B  crc16={:.3f}us  cobs_encode={:.3f}us  cobs_decode={:.3f}us  total={:.3f}us".format(
        size, t_crc, t_enc, t_dec, t_crc + t_enc + t_dec))
