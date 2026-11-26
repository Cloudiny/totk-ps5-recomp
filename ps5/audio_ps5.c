/*
 * ps5/audio_ps5.c
 *
 * PS5 48 kHz PCM audio backend scaffold using libSceAudioOut
 * (replaces SDL3 audio stream output in runtime/audio_mixer.c for Phase 3).
 *
 * Note: libopus is already precompiled for PS5 inside the Longshot kit
 * (third_party/ps5-kit/kit/obj/opus_*.o), so Switch Opus voices can link directly.
 */

#include "plat_ps5.h"

#include <stdint.h>

extern int32_t sceAudioOutInit(void);
extern int32_t sceAudioOutOpen(
    int32_t user_id,
    int32_t type,
    int32_t index,
    uint32_t len,
    uint32_t freq,
    uint32_t param
);
extern int32_t sceAudioOutOutput(int32_t handle, const void *ptr);
extern int32_t sceAudioOutClose(int32_t handle);

#define TOTK_PS5_AUDIO_USER_SYSTEM 0xFF
#define TOTK_PS5_AUDIO_TYPE_MAIN   0
#define TOTK_PS5_AUDIO_FMT_S16_ST  1 /* S16 stereo */

static int32_t g_audio_handle = -1;

int totk_ps5_audio_init(uint32_t samples_per_frame) {
    if (g_audio_handle >= 0) {
        return 0;
    }
    int32_t rc = sceAudioOutInit();
    if (rc < 0 && (uint32_t)rc != 0x80260002u /* already initialized */) {
        totk_ps5_klogf("[totk-ps5] sceAudioOutInit failed: 0x%x\n", (unsigned)rc);
        return -1;
    }
    uint32_t grain = samples_per_frame ? samples_per_frame : 256u;
    g_audio_handle = sceAudioOutOpen(
        TOTK_PS5_AUDIO_USER_SYSTEM,
        TOTK_PS5_AUDIO_TYPE_MAIN,
        0,
        grain,
        48000u,
        TOTK_PS5_AUDIO_FMT_S16_ST
    );
    if (g_audio_handle < 0) {
        totk_ps5_klogf("[totk-ps5] sceAudioOutOpen failed: 0x%x\n", (unsigned)g_audio_handle);
        return -1;
    }
    return 0;
}

int totk_ps5_audio_submit(const int16_t *interleaved_pcm) {
    if (g_audio_handle < 0 || !interleaved_pcm) {
        return -1;
    }
    return sceAudioOutOutput(g_audio_handle, interleaved_pcm) < 0 ? -1 : 0;
}

void totk_ps5_audio_shutdown(void) {
    if (g_audio_handle >= 0) {
        sceAudioOutClose(g_audio_handle);
        g_audio_handle = -1;
    }
}
