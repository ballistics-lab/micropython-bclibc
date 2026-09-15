/* Pure-C (no MicroPython at all) BCP device harness, for comparing against
 * the MicroPython run()-over-pty numbers. Reuses the exact same wire codec
 * (crc16/cobs, copied verbatim from src/bcp/bcp_frame_mp.h's pure-C core
 * functions) and the exact same engine calls
 * (tiny_bclibc_build_shot_props/find_zero_angle/integrate_stream) that
 * bcp_dispatch_mp.h's LOAD_PROFILE/INTEGRATE_FAST handlers use -- only the
 * mp_obj_t plumbing is gone, replaced with plain blocking POSIX read()/
 * write() on the pty fd (same "blocking read" shape as the first
 * MicroPython pty test, for apples-to-apples).
 *
 * Only implements LOAD_PROFILE (G1/G7 fixed-table case) and INTEGRATE_FAST
 * -- the two commands the benchmark actually exercises.
 */
#define TINY_BCLIBC_SINGLE_PRECISION
#define TINY_BCLIBC_NO_THREAD_LOCAL
#define TINY_BCLIBC_NO_ERR_BUF
#define TINY_BCLIBC_FAST_ZERO_FIND

#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "tiny_bclibc.h"
#include "drag_tables.h"

/* ── wire codec: verbatim port of bcp_frame_mp.h's pure-C core ─────────── */
#define BCP_CRC_POLY 0x1021u
static uint16_t bcp_crc_table[256];
static bool bcp_crc_table_ready = false;

static void bcp_crc_table_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint16_t crc = (uint16_t)(i << 8);
        for (int b = 0; b < 8; b++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ BCP_CRC_POLY) : (uint16_t)(crc << 1);
        }
        bcp_crc_table[i] = crc;
    }
    bcp_crc_table_ready = true;
}

static uint16_t bcp_crc16(const uint8_t *data, size_t len, uint16_t crc) {
    if (!bcp_crc_table_ready) bcp_crc_table_init();
    for (size_t i = 0; i < len; i++) {
        crc = (uint16_t)((crc << 8) ^ bcp_crc_table[((crc >> 8) ^ data[i]) & 0xFFu]);
    }
    return crc;
}

static size_t bcp_cobs_encode(const uint8_t *data, size_t len, uint8_t *out) {
    size_t read = 0, write = 1, code_index = 0;
    uint8_t code = 1;
    while (read < len) {
        uint8_t b = data[read];
        if (b == 0) {
            out[code_index] = code;
            code = 1;
            code_index = write++;
            read++;
        } else {
            out[write++] = b;
            read++;
            code++;
            if (code == 0xFFu) {
                out[code_index] = code;
                code = 1;
                code_index = write++;
            }
        }
    }
    out[code_index] = code;
    return write;
}

static size_t bcp_cobs_decode(const uint8_t *data, size_t len, uint8_t *out, size_t out_cap) {
    if (len == 0) return (size_t)-1;
    size_t read = 0, write = 0;
    while (read < len) {
        uint8_t code = data[read];
        if (code == 0) return (size_t)-1;
        read++;
        size_t end = read + (size_t)code - 1u;
        if (end > len) return (size_t)-1;
        size_t block = end - read;
        if (write + block > out_cap) return (size_t)-1;
        memcpy(out + write, data + read, block);
        write += block;
        read = end;
        if (code < 0xFFu && read < len) {
            if (write >= out_cap) return (size_t)-1;
            out[write++] = 0;
        }
    }
    return write;
}

static uint32_t rdf32_bits(const uint8_t *p, size_t off) {
    return (uint32_t)p[off] | ((uint32_t)p[off + 1] << 8) | ((uint32_t)p[off + 2] << 16) | ((uint32_t)p[off + 3] << 24);
}
static float rdf32(const uint8_t *p, size_t off) {
    uint32_t bits = rdf32_bits(p, off);
    float f;
    memcpy(&f, &bits, 4);
    return f;
}
static void wf32(uint8_t *p, size_t off, float v) {
    uint32_t bits;
    memcpy(&bits, &v, 4);
    p[off] = bits & 0xFF; p[off+1] = (bits>>8)&0xFF; p[off+2]=(bits>>16)&0xFF; p[off+3]=(bits>>24)&0xFF;
}
static void wu16(uint8_t *p, size_t off, uint16_t v) { p[off] = v & 0xFF; p[off+1] = (v>>8)&0xFF; }
static void wu32(uint8_t *p, size_t off, uint32_t v) {
    p[off]=v&0xFF; p[off+1]=(v>>8)&0xFF; p[off+2]=(v>>16)&0xFF; p[off+3]=(v>>24)&0xFF;
}
static int32_t rdi32(const uint8_t *p, size_t off) { return (int32_t)rdf32_bits(p, off); }
static uint16_t rdu16(const uint8_t *p, size_t off) { return (uint16_t)(p[off] | (p[off+1]<<8)); }

/* Benchmark harness only -- a short write() on a pty is not a real-world
 * failure mode worth handling, unlike the eventual real transport code. */
static void wr(int fd, const void *buf, size_t n) { ssize_t r = write(fd, buf, n); (void)r; }

#define CMD_LOAD_PROFILE 1
#define CMD_INTEGRATE_FAST 5
#define STATUS_OK 0
#define STATUS_MORE 1
#define STATUS_ERR_BAD_SIZE 2
#define STATUS_ERR_BAD_ARG 3
#define STATUS_ERR_NOT_LOADED 4
#define STATUS_ERR_INTERNAL 5

/* build_frame: <start=0x00><COBS(cmd,seq,status,rsvd,payload,crc16)><0x00> */
static size_t build_frame(uint8_t type_, uint8_t seq, uint8_t status, const uint8_t *payload, size_t plen, uint8_t *out) {
    uint8_t packet[2048];
    packet[0] = type_; packet[1] = seq; packet[2] = status; packet[3] = 0;
    memcpy(packet + 4, payload, plen);
    uint16_t crc = bcp_crc16(packet, 4 + plen, 0xFFFF);
    packet[4 + plen] = crc & 0xFF;
    packet[4 + plen + 1] = (crc >> 8) & 0xFF;
    size_t packet_len = 4 + plen + 2;
    out[0] = 0;
    size_t n = bcp_cobs_encode(packet, packet_len, out + 1);
    out[1 + n] = 0;
    return 1 + n + 1;
}

/* ── engine state, mirroring bcp_state (G1/G7 fixed-table subset only) ──── */
static TINY_BCLIBC_Shot shot;
static TINY_BCLIBC_CurvePoint curve_buf[256];
static real_t zero_distance_ft;
static bool has_profile = false;

static void state_init(void) {
    shot.config = TINY_BCLIBC_Config_default();
    shot.temp_c = REAL_C(15.0);
    shot.pressure_hpa = REAL_C(1013.25);
    shot.altitude_ft = REAL_C(0.0);
    shot.humidity = REAL_C(0.5);
    shot.latitude_deg = (real_t)NAN;
    shot.azimuth_deg = (real_t)NAN;
    shot.winds = NULL;
    shot.wind_count = 0;
    shot.look_angle_rad = REAL_C(0.0);
    shot.barrel_azimuth_rad = REAL_C(0.0);
    shot.cant_angle_rad = REAL_C(0.0);
}

static int32_t build_props(TINY_BCLIBC_ShotProps *out) {
    return tiny_bclibc_build_shot_props(&shot, curve_buf, out);
}

static int handle_load_profile(const uint8_t *p, size_t plen, uint8_t *status_out) {
    if (plen < 36) { *status_out = STATUS_ERR_BAD_SIZE; return 0; }
    uint8_t drag_type = p[32];
    uint16_t drag_count = rdu16(p, 34);
    if ((drag_type != 0 && drag_type != 1) || drag_count != 0) {
        *status_out = STATUS_ERR_BAD_ARG; return 0; /* only G1/G7 fixed supported here */
    }
    shot.bc = (real_t)rdf32(p, 0);
    shot.weight_grain = (real_t)rdf32(p, 4);
    shot.diameter_inch = (real_t)rdf32(p, 8);
    shot.length_inch = (real_t)rdf32(p, 12);
    shot.muzzle_velocity_fps = (real_t)rdf32(p, 16);
    shot.sight_height_ft = (real_t)rdf32(p, 20);
    shot.twist_inch = (real_t)rdf32(p, 24);
    zero_distance_ft = (real_t)rdf32(p, 28);
    if (drag_type == 0) {
        shot.mach_data = g1_mach; shot.cd_data = g1_cd; shot.drag_table_size = G1_N;
    } else {
        shot.mach_data = g7_mach; shot.cd_data = g7_cd; shot.drag_table_size = G7_N;
    }
    has_profile = true;

    TINY_BCLIBC_ShotProps props;
    if (build_props(&props) != TINY_BCLIBC_OK) { *status_out = STATUS_ERR_INTERNAL; return 0; }
    real_t angle;
    if (tiny_bclibc_find_zero_angle(&props, zero_distance_ft, &angle) != TINY_BCLIBC_OK) {
        *status_out = STATUS_ERR_INTERNAL; return 0;
    }
    shot.barrel_elevation_rad = angle;
    *status_out = STATUS_OK;
    return 1;
}

#define ROWS_PER_FRAME 8u
typedef struct {
    int fd;
    uint8_t type_resp;
    uint8_t seq;
    uint8_t buf[4 + ROWS_PER_FRAME * 16];
    uint32_t buf_count;
    uint32_t next_row_idx;
} StreamCtx;

static void stream_flush(StreamCtx *ctx) {
    if (ctx->buf_count == 0) return;
    wu16(ctx->buf, 0, (uint16_t)ctx->next_row_idx);
    ctx->buf[2] = (uint8_t)ctx->buf_count;
    ctx->buf[3] = 0;
    uint8_t frame[2048];
    size_t flen = build_frame(ctx->type_resp, ctx->seq, STATUS_MORE, ctx->buf, 4 + ctx->buf_count * 16, frame);
    wr(ctx->fd, frame, flen);
    ctx->next_row_idx += ctx->buf_count;
    ctx->buf_count = 0;
}

static int32_t stream_row_cb(const TINY_BCLIBC_TrajectoryData *pt, void *ctx_) {
    StreamCtx *ctx = (StreamCtx *)ctx_;
    uint8_t *dst = ctx->buf + 4 + ctx->buf_count * 16;
    wf32(dst, 0, (float)pt->distance_ft);
    wf32(dst, 4, (float)pt->drop_angle_rad);
    wf32(dst, 8, (float)pt->windage_angle_rad);
    wf32(dst, 12, (float)pt->velocity_fps);
    ctx->buf_count++;
    if (ctx->buf_count >= ROWS_PER_FRAME) stream_flush(ctx);
    return 0;
}

static void handle_integrate_fast(int fd, const uint8_t *p, size_t plen, uint8_t seq) {
    uint8_t frame[2048];
    if (plen != 16 || !has_profile) {
        uint8_t st = plen != 16 ? STATUS_ERR_BAD_SIZE : STATUS_ERR_NOT_LOADED;
        size_t flen = build_frame(CMD_INTEGRATE_FAST | 0x80, seq, st, NULL, 0, frame);
        wr(fd, frame, flen);
        return;
    }
    TINY_BCLIBC_TrajectoryRequest req;
    req.range_limit_ft = (real_t)rdf32(p, 0);
    req.range_step_ft = (real_t)rdf32(p, 4);
    req.time_step = (real_t)rdf32(p, 8);
    req.filter_flags = rdi32(p, 12);

    TINY_BCLIBC_ShotProps props;
    if (build_props(&props) != TINY_BCLIBC_OK) {
        size_t flen = build_frame(CMD_INTEGRATE_FAST | 0x80, seq, STATUS_ERR_INTERNAL, NULL, 0, frame);
        wr(fd, frame, flen);
        return;
    }
    StreamCtx ctx; memset(&ctx, 0, sizeof(ctx));
    ctx.fd = fd; ctx.type_resp = CMD_INTEGRATE_FAST | 0x80; ctx.seq = seq;

    int32_t total = 0, reason = 0;
    int32_t rc = tiny_bclibc_integrate_stream(&props, &req, stream_row_cb, &ctx, &total, &reason, NULL);
    stream_flush(&ctx);
    if (rc != TINY_BCLIBC_OK) {
        size_t flen = build_frame(CMD_INTEGRATE_FAST | 0x80, seq, STATUS_ERR_INTERNAL, NULL, 0, frame);
        wr(fd, frame, flen);
        return;
    }
    uint8_t out[8];
    wu32(out, 0, (uint32_t)total);
    wu32(out, 4, (uint32_t)reason);
    size_t flen = build_frame(CMD_INTEGRATE_FAST | 0x80, seq, STATUS_OK, out, 8, frame);
    wr(fd, frame, flen);
}

static void handle_segment(int fd, const uint8_t *seg, size_t seg_len) {
    uint8_t packet[2048];
    size_t plen = bcp_cobs_decode(seg, seg_len, packet, sizeof(packet));
    if (plen == (size_t)-1 || plen < 6) return; /* malformed, silently dropped */
    size_t body_len = plen - 2;
    uint16_t crc_got = packet[body_len] | (packet[body_len + 1] << 8);
    if (bcp_crc16(packet, body_len, 0xFFFF) != crc_got) return; /* bad CRC, dropped */

    uint8_t type_ = packet[0], seq = packet[1];
    const uint8_t *payload = packet + 4;
    size_t payload_len = body_len - 4;

    if (type_ == CMD_LOAD_PROFILE) {
        uint8_t status;
        handle_load_profile(payload, payload_len, &status);
        uint8_t frame[64];
        size_t flen = build_frame(CMD_LOAD_PROFILE | 0x80, seq, status, NULL, 0, frame);
        wr(fd, frame, flen);
    } else if (type_ == CMD_INTEGRATE_FAST) {
        handle_integrate_fast(fd, payload, payload_len, seq);
    }
    /* unrecognized commands: not implemented in this minimal harness */
}

int main(int argc, char **argv) {
    (void)argc;
    state_init();

    const char *path = argv[1];
    int fd = open(path, O_RDWR);
    if (fd < 0) { perror("open"); return 1; }

    uint8_t rxbuf[8192];
    size_t rx_len = 0;
    uint8_t byte;
    ssize_t n;

    for (;;) {
        n = read(fd, &byte, 1);
        if (n <= 0) {
            if (n < 0) continue; /* blocking read, shouldn't normally hit EAGAIN */
            continue;
        }
        if (byte == 0) {
            if (rx_len > 0) {
                handle_segment(fd, rxbuf, rx_len);
                rx_len = 0;
            }
        } else {
            if (rx_len < sizeof(rxbuf)) {
                rxbuf[rx_len++] = byte;
            }
        }
    }
    return 0;
}
