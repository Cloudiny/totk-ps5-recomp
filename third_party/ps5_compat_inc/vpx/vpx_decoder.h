#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef int vpx_codec_err_t;
enum {
    VPX_CODEC_OK = 0,
    VPX_CODEC_ERROR = 1,
    VPX_CODEC_UNSUP_FEATURE = 3,
};

typedef enum vpx_img_fmt {
    VPX_IMG_FMT_NONE = 0,
    VPX_IMG_FMT_I420 = 0x102,
} vpx_img_fmt_t;

enum {
    VPX_PLANE_Y = 0,
    VPX_PLANE_U = 1,
    VPX_PLANE_V = 2,
};

typedef struct vpx_image {
    vpx_img_fmt_t fmt;
    unsigned int d_w;
    unsigned int d_h;
    unsigned char *planes[4];
    int stride[4];
} vpx_image_t;

typedef struct vpx_codec_dec_cfg {
    unsigned int threads;
    unsigned int w;
    unsigned int h;
} vpx_codec_dec_cfg_t;

typedef struct vpx_codec_iface vpx_codec_iface_t;
typedef const void *vpx_codec_iter_t;

typedef struct vpx_codec_ctx {
    void *priv;
    unsigned int w;
    unsigned int h;
    vpx_image_t frame;
} vpx_codec_ctx_t;

vpx_codec_err_t vpx_codec_dec_init(
    vpx_codec_ctx_t *ctx,
    vpx_codec_iface_t *iface,
    const vpx_codec_dec_cfg_t *cfg,
    long flags
);
vpx_codec_err_t vpx_codec_control(vpx_codec_ctx_t *ctx, int ctrl_id, ...);
vpx_codec_err_t vpx_codec_decode(
    vpx_codec_ctx_t *ctx,
    const uint8_t *data,
    unsigned int data_sz,
    void *user_priv,
    long deadline
);
vpx_image_t *vpx_codec_get_frame(vpx_codec_ctx_t *ctx, vpx_codec_iter_t *iter);
vpx_codec_err_t vpx_codec_destroy(vpx_codec_ctx_t *ctx);
const char *vpx_codec_error_detail(const vpx_codec_ctx_t *ctx);
const char *vpx_codec_err_to_string(vpx_codec_err_t err);
const char *vpx_codec_version_str(void);

#ifdef __cplusplus
}
#endif
