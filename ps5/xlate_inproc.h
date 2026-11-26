/*
 * ps5/xlate_inproc.h
 *
 * In-process Maxwell -> SPIR-V shader translation interface for PS5.
 *
 * On Linux, totk-linux-native-recomp/runtime/gfx_shader.c spawns child
 * processes (`totk_xlate --serve`) over pipes via posix_spawn().
 * PlayStation 5 titles cannot spawn child processes.
 *
 * Phase 2 links totk-linux-native-recomp/tools/xlate/ (pure C++ / Eden
 * shader_recompiler + Sirit) directly into eboot.bin as a static library
 * (or reuses the kit's precompiled PS5 Eden shader_recompiler + Sirit
 * objects) and serves translations synchronously/on a worker thread pool
 * through this C ABI, backed by pre-translated PC caches:
 *   /data/totk-ps5/cache/shader-programs.bin
 *   /data/totk-ps5/cache/shader-answers.bin
 */

#ifndef TOTK_PS5_XLATE_INPROC_H
#define TOTK_PS5_XLATE_INPROC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct TotkPs5XlateCtx TotkPs5XlateCtx;

typedef struct TotkPs5XlateResult {
    uint32_t *spirv_words;
    size_t spirv_word_count;
    int status; /* 0 = OK, non-zero = translation error */
} TotkPs5XlateResult;

/* Create an in-process translator context configured for PS5 RADV capabilities. */
TotkPs5XlateCtx *totk_ps5_xlate_create(void);

/* Translate one Maxwell shader program binary blob into SPIR-V words. */
int totk_ps5_xlate_translate(
    TotkPs5XlateCtx *ctx,
    uint32_t stage,
    const void *maxwell_code,
    size_t maxwell_size,
    TotkPs5XlateResult *out_res
);

/* Release SPIR-V word buffer returned by totk_ps5_xlate_translate. */
void totk_ps5_xlate_free_result(TotkPs5XlateResult *res);

/* Destroy translator context. */
void totk_ps5_xlate_destroy(TotkPs5XlateCtx *ctx);

#ifdef __cplusplus
}
#endif

#endif /* TOTK_PS5_XLATE_INPROC_H */
