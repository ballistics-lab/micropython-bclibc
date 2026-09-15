"""bcp_frame — wire framing for the Ballistic Co-Processor protocol (BACKLOG.md Epic 3).

Transport-agnostic: no I/O, no MicroPython-only APIs. Runs unchanged under
CPython (host-side tooling, tests) and MicroPython (on-device dispatcher).

Wire format
-----------
    00 COBS(packet) 00

No separate start byte and no length field (see BACKLOG.md Epic 3 for the
rationale) -- COBS guarantees the encoded bytes contain no 0x00, so the
leading/trailing zero alone delimits a frame, and per-command payload size
checks (not a length field) catch a merged/truncated frame.

``packet`` is a 4-byte header followed by the payload followed by a 2-byte
CRC over everything before it:

    type:u8  seq:u8  status:u8  rsvd:u8  payload...  crc16:u16 (LE)

``type`` is the command id in a request, ``cmd | 0x80`` in the matching
response. ``seq`` is set by the host and echoed back unchanged. ``status``
is 0 in a request; in a response it is one of the STATUS_* codes below.
"""

# ── CRC16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect, xorout 0) ────
# Table-driven for O(1)-per-byte cost. Check value for b"123456789" is
# 0x29B1 -- the standard catalogue test vector for this variant, asserted
# in tests/test_bcp_frame.py.
_CRC_POLY = 0x1021

# array('H', ...) instead of a plain list: a list of 256 ints is really a
# 256-pointer object array (~1040 B measured on RP2040), while a packed
# uint16 array is ~528 B for the same 256 entries -- same values, same
# lookup, about half the RAM, ~5% slower (measured, within noise next to
# the table-size choice itself; see BACKLOG.md Epic 3).
try:
    from array import array as _array
except ImportError:
    _array = None


def _make_crc_table():
    table = _array("H", bytes(512)) if _array else [0] * 256
    for i in range(256):
        crc = i << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ _CRC_POLY) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
        table[i] = crc
    return table


_CRC_TABLE = _make_crc_table()


def crc16(data, crc=0xFFFF):
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _CRC_TABLE[((crc >> 8) ^ b) & 0xFF]
    return crc


# ── COBS ───────────────────────────────────────────────────────────────────
def cobs_encode(data):
    """Consistent Overhead Byte Stuffing. Output contains no 0x00 byte."""
    out = bytearray(len(data) + len(data) // 254 + 2)
    read = 0
    write = 1
    code_index = 0
    code = 1
    n = len(data)
    while read < n:
        b = data[read]
        if b == 0:
            out[code_index] = code
            code = 1
            code_index = write
            write += 1
            read += 1
        else:
            out[write] = b
            write += 1
            read += 1
            code += 1
            if code == 0xFF:
                out[code_index] = code
                code = 1
                code_index = write
                write += 1
    out[code_index] = code
    return bytes(out[:write])


def cobs_decode(data):
    """Inverse of cobs_encode. Raises ValueError on malformed input."""
    n = len(data)
    if n == 0:
        raise ValueError("empty COBS input")
    out = bytearray()
    read = 0
    while read < n:
        code = data[read]
        if code == 0:
            raise ValueError("zero byte inside COBS payload")
        read += 1
        end = read + code - 1
        if end > n:
            raise ValueError("truncated COBS block")
        out.extend(data[read:end])
        read = end
        if code < 0xFF and read < n:
            out.append(0)
    return bytes(out)


# ── Packet header ──────────────────────────────────────────────────────────
HEADER_SIZE = 4
CRC_SIZE = 2
MIN_PACKET_SIZE = HEADER_SIZE + CRC_SIZE

RESP_BIT = 0x80

# Response status codes (packet header's `status` field).
STATUS_OK = 0
STATUS_MORE = 1
STATUS_INTERRUPTED = 2
STATUS_ERR_BAD_SIZE = 3
STATUS_ERR_BAD_ARG = 4
STATUS_ERR_NOT_LOADED = 5
STATUS_ERR_INTERNAL = 6


def pack_header(type_, seq, status=0, rsvd=0):
    return bytes((type_ & 0xFF, seq & 0xFF, status & 0xFF, rsvd & 0xFF))


def unpack_header(buf):
    return buf[0], buf[1], buf[2], buf[3]


def build_frame(type_, seq, status, payload=b""):
    """Pack a header+payload+crc16 packet, COBS-encode it, and delimit it
    with the leading/trailing 0x00 that goes straight on the wire."""
    packet = bytearray(pack_header(type_, seq, status))
    packet.extend(payload)
    crc = crc16(packet)
    packet.append(crc & 0xFF)
    packet.append((crc >> 8) & 0xFF)
    encoded = cobs_encode(bytes(packet))
    out = bytearray(len(encoded) + 2)
    out[0] = 0
    out[1 : 1 + len(encoded)] = encoded
    out[1 + len(encoded)] = 0
    return bytes(out)


class FrameDecoder:
    """Stateful byte-stream -> validated-packet decoder.

    Feed it raw transport bytes (in any chunking) via ``feed()``; it returns
    the list of packets that decoded and CRC-checked successfully as
    ``(type, seq, status, payload)`` tuples. Anything that fails COBS
    decode, is under MIN_PACKET_SIZE, or fails its CRC is silently dropped
    -- there is no reliable ``seq`` to reply to on a corrupt frame (see
    BACKLOG.md Epic 3).
    """

    def __init__(self, max_frame_size=2048):
        self._max_frame_size = max_frame_size
        self._buf = bytearray()

    def feed(self, chunk):
        out = []
        for b in chunk:
            if b == 0:
                if self._buf:
                    pkt = self._try_decode(self._buf)
                    if pkt is not None:
                        out.append(pkt)
                    self._buf = bytearray()
                # else: empty segment (00 00) or a leading sync byte -- ignore
            else:
                self._buf.append(b)
                if len(self._buf) > self._max_frame_size:
                    # No delimiter within the size budget -- drop and
                    # resync on the next 0x00, keeping the RX buffer bounded.
                    self._buf = bytearray()
        return out

    def _try_decode(self, encoded):
        try:
            packet = cobs_decode(bytes(encoded))
        except ValueError:
            return None
        if len(packet) < MIN_PACKET_SIZE:
            return None
        body, crc_bytes = packet[:-CRC_SIZE], packet[-CRC_SIZE:]
        got_crc = crc_bytes[0] | (crc_bytes[1] << 8)
        if crc16(body) != got_crc:
            return None
        type_, seq, status, _rsvd = unpack_header(body)
        payload = body[HEADER_SIZE:]
        return type_, seq, status, payload
