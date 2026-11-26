/*
 * ps5/vpx_ps5.c
 *
 * libvpx compatibility shim for runtime/ov_movie.c on PS5, backed by
 * the PS5 kit's precompiled FFmpeg VP9 decoder (libavcodec.a + libavutil.a).
 */

#include <vpx/vp8dx.h>
#include <stdlib.h>
#include <string.h>

extern void rt_log(const char *fmt, ...);

/* Opaque FFmpeg types; only ABI-frozen head fields of AVPacket / AVFrame are accessed
 * (empirically verified against third_party/ps5-kit/kit/obj/host_nn_video.o). */
typedef struct AVCodec AVCodec;
typedef struct AVCodecContext AVCodecContext;
typedef struct AVDictionary AVDictionary;

typedef struct Ps5AVPacketHead {
    void *buf;
    int64_t pts;
    int64_t dts;
    uint8_t *data;
    int size;
} Ps5AVPacketHead;

typedef struct Ps5AVFrameHead {
    uint8_t *data[8];
    int linesize[8];
    uint8_t **extended_data;
    int width;
    int height;
    int nb_samples;
    int format;
} Ps5AVFrameHead;

extern const AVCodec ff_vp9_decoder;
extern AVCodecContext *avcodec_alloc_context3(const AVCodec *codec);
extern int avcodec_open2(AVCodecContext *avctx, const AVCodec *codec, AVDictionary **options);
extern void avcodec_free_context(AVCodecContext **avctx);
extern int avcodec_send_packet(AVCodecContext *avctx, const void *avpkt);
extern int avcodec_receive_frame(AVCodecContext *avctx, void *frame);
extern void avcodec_flush_buffers(AVCodecContext *avctx);

extern void *av_packet_alloc(void);
extern void av_packet_free(void **pkt);
extern int av_new_packet(void *pkt, int size);
extern void av_packet_unref(void *pkt);

extern void *av_frame_alloc(void);
extern void av_frame_free(void **frame);
extern void av_frame_unref(void *frame);
extern int av_opt_set(void *obj, const char *name, const char *val, int search_flags);
extern int av_opt_set_int(void *obj, const char *name, int64_t val, int search_flags);

typedef struct Ps5VpxPriv {
    AVCodecContext *avctx;
    void *pkt;
    void *frame;
    int last_err;
} Ps5VpxPriv;

static int g_vp9_iface_dummy = 0;

vpx_codec_iface_t *vpx_codec_vp9_dx(void) {
    return (vpx_codec_iface_t *)&g_vp9_iface_dummy;
}

vpx_codec_err_t vpx_codec_dec_init(
    vpx_codec_ctx_t *ctx,
    vpx_codec_iface_t *iface,
    const vpx_codec_dec_cfg_t *cfg,
    long flags
) {
    (void)iface;
    (void)flags;
    if (!ctx) return VPX_CODEC_ERROR;
    memset(ctx, 0, sizeof(*ctx));
    if (cfg) {
        ctx->w = cfg->w;
        ctx->h = cfg->h;
    }

    const AVCodec *codec = &ff_vp9_decoder;

    Ps5VpxPriv *p = (Ps5VpxPriv *)calloc(1, sizeof(*p));
    if (!p) return VPX_CODEC_ERROR;

    p->avctx = avcodec_alloc_context3(codec);
    p->pkt = av_packet_alloc();
    p->frame = av_frame_alloc();
    if (!p->avctx || !p->pkt || !p->frame) {
        if (p->frame) av_frame_free(&p->frame);
        if (p->pkt) av_packet_free(&p->pkt);
        if (p->avctx) avcodec_free_context(&p->avctx);
        free(p);
        return VPX_CODEC_ERROR;
    }

    /* Multi-threaded VP9 tile/slice decoding (zero frame-buffering latency) + full deblocking loop filter */
    av_opt_set_int(p->avctx, "threads", 4, 0);
    av_opt_set(p->avctx, "thread_type", "slice", 0);
    av_opt_set(p->avctx, "skip_loop_filter", "default", 0);

    int rc = avcodec_open2(p->avctx, codec, NULL);
    if (rc < 0) {
        rt_log("ps5-vpx: avcodec_open2(vp9) failed (%d)", rc);
        av_frame_free(&p->frame);
        av_packet_free(&p->pkt);
        avcodec_free_context(&p->avctx);
        free(p);
        return VPX_CODEC_ERROR;
    }

    ctx->priv = p;
    rt_log("ps5-vpx: FFmpeg VP9 decoder initialized OK (%ux%u)", ctx->w, ctx->h);
    return VPX_CODEC_OK;
}

vpx_codec_err_t vpx_codec_control(vpx_codec_ctx_t *ctx, int ctrl_id, ...) {
    (void)ctx;
    (void)ctrl_id;
    return VPX_CODEC_OK;
}

vpx_codec_err_t vpx_codec_decode(
    vpx_codec_ctx_t *ctx,
    const uint8_t *data,
    unsigned int data_sz,
    void *user_priv,
    long deadline
) {
    (void)user_priv;
    (void)deadline;
    if (!ctx || !ctx->priv) return VPX_CODEC_ERROR;
    Ps5VpxPriv *p = (Ps5VpxPriv *)ctx->priv;
    if (!data || data_sz == 0) {
        int rc = avcodec_send_packet(p->avctx, NULL);
        p->last_err = rc;
        return rc < 0 ? VPX_CODEC_ERROR : VPX_CODEC_OK;
    }

    av_packet_unref(p->pkt);
    if (av_new_packet(p->pkt, (int)data_sz) < 0) {
        p->last_err = -12;
        return VPX_CODEC_ERROR;
    }
    Ps5AVPacketHead *ph = (Ps5AVPacketHead *)p->pkt;
    memcpy(ph->data, data, data_sz);

    int rc = avcodec_send_packet(p->avctx, p->pkt);
    if (rc == -11 || rc == -35) { /* AVERROR(EAGAIN) on Linux (-11) or FreeBSD/PS5 (-35) */
        av_frame_unref(p->frame);
        while (avcodec_receive_frame(p->avctx, p->frame) == 0) {
            av_frame_unref(p->frame);
        }
        rc = avcodec_send_packet(p->avctx, p->pkt);
    } else if (rc == -541478725) { /* AVERROR_EOF after a prior drain packet */
        avcodec_flush_buffers(p->avctx);
        rc = avcodec_send_packet(p->avctx, p->pkt);
    }
    av_packet_unref(p->pkt);
    p->last_err = rc;
    if (rc < 0) {
        return VPX_CODEC_ERROR;
    }
    return VPX_CODEC_OK;
}

vpx_image_t *vpx_codec_get_frame(vpx_codec_ctx_t *ctx, vpx_codec_iter_t *iter) {
    (void)iter;
    if (!ctx || !ctx->priv) return NULL;
    Ps5VpxPriv *p = (Ps5VpxPriv *)ctx->priv;

    av_frame_unref(p->frame);
    int rc = avcodec_receive_frame(p->avctx, p->frame);
    if (rc != 0) {
        return NULL;
    }

    const Ps5AVFrameHead *fh = (const Ps5AVFrameHead *)p->frame;
    /* AV_PIX_FMT_YUV420P = 0, AV_PIX_FMT_YUVJ420P = 12 */
    if (fh->width <= 0 || fh->height <= 0 || (fh->format != 0 && fh->format != 12)) {
        return NULL;
    }

    ctx->frame.fmt = VPX_IMG_FMT_I420;
    ctx->frame.d_w = (unsigned int)fh->width;
    ctx->frame.d_h = (unsigned int)fh->height;
    ctx->frame.planes[0] = fh->data[0];
    ctx->frame.planes[1] = fh->data[1];
    ctx->frame.planes[2] = fh->data[2];
    ctx->frame.planes[3] = NULL;
    ctx->frame.stride[0] = fh->linesize[0];
    ctx->frame.stride[1] = fh->linesize[1];
    ctx->frame.stride[2] = fh->linesize[2];
    ctx->frame.stride[3] = 0;
    return &ctx->frame;
}

vpx_codec_err_t vpx_codec_destroy(vpx_codec_ctx_t *ctx) {
    if (!ctx) return VPX_CODEC_OK;
    Ps5VpxPriv *p = (Ps5VpxPriv *)ctx->priv;
    if (p) {
        if (p->frame) av_frame_free(&p->frame);
        if (p->pkt) av_packet_free(&p->pkt);
        if (p->avctx) avcodec_free_context(&p->avctx);
        free(p);
        ctx->priv = NULL;
    }
    return VPX_CODEC_OK;
}

const char *vpx_codec_error_detail(const vpx_codec_ctx_t *ctx) {
    if (!ctx || !ctx->priv) return "decoder not initialized";
    return "FFmpeg VP9 decode error";
}

const char *vpx_codec_err_to_string(vpx_codec_err_t err) {
    switch (err) {
    case VPX_CODEC_OK: return "OK";
    case VPX_CODEC_UNSUP_FEATURE: return "Unsupported feature";
    default: return "Codec error";
    }
}

const char *vpx_codec_version_str(void) {
    return "ps5-ffmpeg-vp9-1.0";
}
