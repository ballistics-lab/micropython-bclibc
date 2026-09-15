/* bcp_frame_mp.h — BCP wire framing codec (COBS + CRC16/CCITT-FALSE), C port
 * of the Python reference implementation in src/bcp_frame.py. See
 * PROTOCOL.md §1-§2 for the wire format this implements, and BACKLOG.md
 * Epic 3's "implementation language is C, not Python" resolution for why
 * this exists as a usermod C module instead of staying in Python.
 *
 * This is a `.h` on purpose despite holding full function bodies, not just
 * declarations: it is `#include`d exactly once, from tiny_bclibc_mp.c
 * under `#ifdef BCLIBC_BCP`, so that private helpers here can stay `static`
 * instead of needing `extern` declarations across translation units (the
 * "single amalgamated unit" / "unity build" pattern) -- it is never
 * compiled as its own translation unit and never listed in
 * usermod/micropython.mk or .cmake. Only compiled at all when
 * BCLIBC_BCP=1 (see usermod/manifest.py) — usermod only, no natmod
 * branch: BCLIBC_BCP is a usermod-only build per Epic 1. The include
 * guard below is defensive only, given the single call site.
 *
 * `src/bcp_frame.py`/`tests/test_bcp_frame.py` are not touched by this file
 * and stay as the historical design-iteration reference (their known-answer
 * vectors and failure-scenario cases are re-used almost verbatim by
 * tests/test_bcp_frame_native.py, run against the real functions defined
 * here -- exposed under `_tiny_bclibc`, not a separate module, see
 * tiny_bclibc_mp.c's own umbrella comment).
 */
#ifndef BCP_FRAME_MP_H
#define BCP_FRAME_MP_H

#include <string.h>

#include "py/obj.h"
#include "py/runtime.h"
#include "py/misc.h"

/* ── CRC16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflect, xorout 0) ──── */
/* Table-driven, same as bcp_frame.py's crc16(). Computed once, lazily, into
 * a static (.bss) array — not a literal table, to avoid a second
 * hand-transcribed copy of the same 256 values (see BACKLOG.md Epic 3: the
 * COBS test vectors already caught exactly that kind of mistake once this
 * session). Zero RAM cost concern here the way it was on MicroPython's own
 * heap: this is a plain C static array, .bss-resident regardless. */
#define BCP_CRC_POLY 0x1021u

static uint16_t bcp_crc_table[256];
static bool bcp_crc_table_ready = false;

static void bcp_crc_table_init(void)
{
    for (uint32_t i = 0; i < 256; i++)
    {
        uint16_t crc = (uint16_t)(i << 8);
        for (int b = 0; b < 8; b++)
        {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ BCP_CRC_POLY) : (uint16_t)(crc << 1);
        }
        bcp_crc_table[i] = crc;
    }
    bcp_crc_table_ready = true;
}

static uint16_t bcp_crc16(const uint8_t *data, size_t len, uint16_t crc)
{
    if (!bcp_crc_table_ready)
    {
        bcp_crc_table_init();
    }
    for (size_t i = 0; i < len; i++)
    {
        crc = (uint16_t)((crc << 8) ^ bcp_crc_table[((crc >> 8) ^ data[i]) & 0xFFu]);
    }
    return crc;
}

static mp_obj_t mp_bcp_crc16(size_t n_args, const mp_obj_t *args)
{
    mp_buffer_info_t bi;
    mp_get_buffer_raise(args[0], &bi, MP_BUFFER_READ);
    uint16_t seed = (n_args > 1) ? (uint16_t)mp_obj_get_int(args[1]) : 0xFFFFu;
    uint16_t crc = bcp_crc16((const uint8_t *)bi.buf, bi.len, seed);
    return MP_OBJ_NEW_SMALL_INT(crc);
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bcp_crc16_obj, 1, 2, mp_bcp_crc16);

/* ── COBS ─────────────────────────────────────────────────────────────────
 * Direct C port of bcp_frame.py's cobs_encode()/cobs_decode() — same
 * algorithm, same variable names where practical, so the two stay easy to
 * diff by eye. */

/* out must have capacity >= len + len/254 + 2 (bcp_frame.py's own bound). */
static size_t bcp_cobs_encode(const uint8_t *data, size_t len, uint8_t *out)
{
    size_t read = 0, write = 1, code_index = 0;
    uint8_t code = 1;
    while (read < len)
    {
        uint8_t b = data[read];
        if (b == 0)
        {
            out[code_index] = code;
            code = 1;
            code_index = write++;
            read++;
        }
        else
        {
            out[write++] = b;
            read++;
            code++;
            if (code == 0xFFu)
            {
                out[code_index] = code;
                code = 1;
                code_index = write++;
            }
        }
    }
    out[code_index] = code;
    return write;
}

/* Returns decoded length, or (size_t)-1 on malformed input (empty input,
 * a zero byte inside the encoded data, or a truncated block) — mirrors
 * cobs_decode()'s ValueError cases exactly. out_cap bounds writes; a
 * decode that would overflow it is also reported as (size_t)-1. */
static size_t bcp_cobs_decode(const uint8_t *data, size_t len, uint8_t *out, size_t out_cap)
{
    if (len == 0)
    {
        return (size_t)-1;
    }
    size_t read = 0, write = 0;
    while (read < len)
    {
        uint8_t code = data[read];
        if (code == 0)
        {
            return (size_t)-1;
        }
        read++;
        size_t end = read + (size_t)code - 1u;
        if (end > len)
        {
            return (size_t)-1;
        }
        size_t block = end - read;
        if (write + block > out_cap)
        {
            return (size_t)-1;
        }
        memcpy(out + write, data + read, block);
        write += block;
        read = end;
        if (code < 0xFFu && read < len)
        {
            if (write >= out_cap)
            {
                return (size_t)-1;
            }
            out[write++] = 0;
        }
    }
    return write;
}

static mp_obj_t mp_bcp_cobs_encode(mp_obj_t data_obj)
{
    mp_buffer_info_t bi;
    mp_get_buffer_raise(data_obj, &bi, MP_BUFFER_READ);
    size_t cap = bi.len + bi.len / 254u + 2u;
    uint8_t *out = m_new(uint8_t, cap);
    size_t n = bcp_cobs_encode((const uint8_t *)bi.buf, bi.len, out);
    mp_obj_t result = mp_obj_new_bytes(out, n);
    m_del(uint8_t, out, cap);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bcp_cobs_encode_obj, mp_bcp_cobs_encode);

static mp_obj_t mp_bcp_cobs_decode(mp_obj_t data_obj)
{
    mp_buffer_info_t bi;
    mp_get_buffer_raise(data_obj, &bi, MP_BUFFER_READ);
    /* Decoded output is never larger than the encoded input. */
    size_t cap = bi.len > 0 ? bi.len : 1;
    uint8_t *out = m_new(uint8_t, cap);
    size_t n = bcp_cobs_decode((const uint8_t *)bi.buf, bi.len, out, cap);
    if (n == (size_t)-1)
    {
        m_del(uint8_t, out, cap);
        mp_raise_ValueError(MP_ERROR_TEXT("malformed COBS input"));
    }
    mp_obj_t result = mp_obj_new_bytes(out, n);
    m_del(uint8_t, out, cap);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bcp_cobs_decode_obj, mp_bcp_cobs_decode);

/* ── Packet header + framing (PROTOCOL.md §1-§2) ────────────────────────── */

#define BCP_HEADER_SIZE 4u
#define BCP_CRC_SIZE 2u
#define BCP_MIN_PACKET_SIZE (BCP_HEADER_SIZE + BCP_CRC_SIZE)

enum
{
    BCP_STATUS_OK = 0,
    BCP_STATUS_MORE = 1,
    BCP_STATUS_INTERRUPTED = 2,
    BCP_STATUS_ERR_BAD_SIZE = 3,
    BCP_STATUS_ERR_BAD_ARG = 4,
    BCP_STATUS_ERR_NOT_LOADED = 5,
    BCP_STATUS_ERR_INTERNAL = 6,
};

/* build_frame(type_, seq, status, payload=b"") -> bytes
 * Packs header+payload+crc16, COBS-encodes it, and delimits it with the
 * leading/trailing 0x00 that goes straight on the wire — same contract as
 * bcp_frame.build_frame(). */
static mp_obj_t mp_bcp_build_frame(size_t n_args, const mp_obj_t *args)
{
    uint8_t type_ = (uint8_t)mp_obj_get_int(args[0]);
    uint8_t seq = (uint8_t)mp_obj_get_int(args[1]);
    uint8_t status = (uint8_t)mp_obj_get_int(args[2]);

    mp_buffer_info_t pbi = {0};
    if (n_args > 3)
    {
        mp_get_buffer_raise(args[3], &pbi, MP_BUFFER_READ);
    }

    size_t packet_len = BCP_HEADER_SIZE + pbi.len + BCP_CRC_SIZE;
    uint8_t *packet = m_new(uint8_t, packet_len);
    packet[0] = type_;
    packet[1] = seq;
    packet[2] = status;
    packet[3] = 0; /* rsvd */
    if (pbi.len > 0)
    {
        memcpy(packet + BCP_HEADER_SIZE, pbi.buf, pbi.len);
    }
    uint16_t crc = bcp_crc16(packet, BCP_HEADER_SIZE + pbi.len, 0xFFFFu);
    packet[BCP_HEADER_SIZE + pbi.len] = (uint8_t)(crc & 0xFFu);
    packet[BCP_HEADER_SIZE + pbi.len + 1] = (uint8_t)((crc >> 8) & 0xFFu);

    size_t enc_cap = packet_len + packet_len / 254u + 2u;
    uint8_t *encoded = m_new(uint8_t, enc_cap);
    size_t enc_len = bcp_cobs_encode(packet, packet_len, encoded);
    m_del(uint8_t, packet, packet_len);

    uint8_t *out = m_new(uint8_t, enc_len + 2u);
    out[0] = 0;
    memcpy(out + 1, encoded, enc_len);
    out[enc_len + 1] = 0;
    m_del(uint8_t, encoded, enc_cap);

    mp_obj_t result = mp_obj_new_bytes(out, enc_len + 2u);
    m_del(uint8_t, out, enc_len + 2u);
    return result;
}
static MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(mp_bcp_build_frame_obj, 3, 4, mp_bcp_build_frame);

/* parse_frame(encoded) -> (type, seq, status, payload) or None
 *
 * `encoded` is one already delimiter-stripped COBS-encoded segment (what a
 * caller gets after splitting raw transport bytes on 0x00 — the equivalent
 * of what bcp_frame.FrameDecoder accumulates into self._buf before calling
 * its own _try_decode()). Returns None instead of raising on any failure
 * (malformed COBS, under-length packet, bad CRC) — there is no reliable
 * `seq` to reply to on a corrupt frame, matching FrameDecoder's
 * silently-drop contract (PROTOCOL.md §1, BACKLOG.md Epic 3). */
/* Frames dropped for bad COBS/under-length/bad CRC since boot -- reported
 * as IDENT's drop_count (PROTOCOL.md §4.6, optional telemetry). Read by
 * bcp_dispatch_mp.h's IDENT handler further down this same translation
 * unit, not through Python -- `static`, no `extern` needed. */
static uint32_t bcp_frame_drop_count_ = 0;

static uint32_t bcp_frame_drop_count(void)
{
    return bcp_frame_drop_count_;
}

static mp_obj_t mp_bcp_parse_frame(mp_obj_t encoded_obj)
{
    mp_buffer_info_t ebi;
    mp_get_buffer_raise(encoded_obj, &ebi, MP_BUFFER_READ);

    size_t cap = ebi.len > 0 ? ebi.len : 1;
    uint8_t *packet = m_new(uint8_t, cap);
    size_t n = bcp_cobs_decode((const uint8_t *)ebi.buf, ebi.len, packet, cap);
    if (n == (size_t)-1 || n < BCP_MIN_PACKET_SIZE)
    {
        m_del(uint8_t, packet, cap);
        bcp_frame_drop_count_++;
        return mp_const_none;
    }

    size_t body_len = n - BCP_CRC_SIZE;
    uint16_t got_crc = (uint16_t)packet[body_len] | ((uint16_t)packet[body_len + 1] << 8);
    uint16_t want_crc = bcp_crc16(packet, body_len, 0xFFFFu);
    if (got_crc != want_crc)
    {
        m_del(uint8_t, packet, cap);
        bcp_frame_drop_count_++;
        return mp_const_none;
    }

    mp_obj_t items[4];
    items[0] = MP_OBJ_NEW_SMALL_INT(packet[0]); /* type */
    items[1] = MP_OBJ_NEW_SMALL_INT(packet[1]); /* seq */
    items[2] = MP_OBJ_NEW_SMALL_INT(packet[2]); /* status */
    items[3] = mp_obj_new_bytes(packet + BCP_HEADER_SIZE, body_len - BCP_HEADER_SIZE);
    m_del(uint8_t, packet, cap);
    return mp_obj_new_tuple(4, items);
}
static MP_DEFINE_CONST_FUN_OBJ_1(mp_bcp_parse_frame_obj, mp_bcp_parse_frame);

static mp_obj_t mp_bcp_drop_count(void)
{
    return mp_obj_new_int_from_uint(bcp_frame_drop_count_);
}
static MP_DEFINE_CONST_FUN_OBJ_0(mp_bcp_drop_count_obj, mp_bcp_drop_count);

/* No module table / MP_REGISTER_MODULE here: bcp_frame_mp.h and
 * bcp_dispatch_mp.h only define C functions and their mp_obj_t wrapper
 * objects -- one combined `_bcp` module (Python-visible name, globals
 * table, registration) is assembled in tiny_bclibc_mp.c's umbrella
 * section, from both files' objects together. Same reasoning as merging
 * the two .c files into one translation unit in the first place: once
 * the C is one thing, there's no reason to still expose two separate
 * Python-importable names for it (and the two files' STATUS_* constants
 * would otherwise be listed twice, once per module, for the exact same
 * values). */

#endif /* BCP_FRAME_MP_H */
