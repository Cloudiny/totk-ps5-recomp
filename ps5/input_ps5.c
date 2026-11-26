/*
 * ps5/input_ps5.c
 *
 * DualSense controller input scaffold using PS5 libSceUserService + libScePad
 * (replaces SDL3 gamepad handling in runtime/input_sdl.c for Phase 3).
 */

#include "plat_ps5.h"

#include <stdint.h>
#include <string.h>

/* Sony PS5 libSceUserService / libScePad ABI signatures (present in exported.txt) */
extern int32_t sceUserServiceInitialize(const void *params);
extern int32_t sceUserServiceGetInitialUser(int32_t *user_id);
extern int32_t scePadInit(void);
extern int32_t scePadOpen(int32_t user_id, int32_t type, int32_t index, const void *param);
extern int32_t scePadClose(int32_t handle);

typedef struct TotkPs5Pad {
    int32_t user_id;
    int32_t handle;
    int initialized;
} TotkPs5Pad;

static TotkPs5Pad g_pad = { .user_id = -1, .handle = -1, .initialized = 0 };

int totk_ps5_input_init(void) {
    if (g_pad.initialized) {
        return 0;
    }
    int32_t rc = sceUserServiceInitialize(NULL);
    if (rc < 0 && (uint32_t)rc != 0x80960003u /* already initialized */) {
        totk_ps5_klogf("[totk-ps5] sceUserServiceInitialize failed: 0x%x\n", (unsigned)rc);
        return -1;
    }
    rc = sceUserServiceGetInitialUser(&g_pad.user_id);
    if (rc < 0) {
        totk_ps5_klogf("[totk-ps5] sceUserServiceGetInitialUser failed: 0x%x\n", (unsigned)rc);
        return -1;
    }
    rc = scePadInit();
    if (rc < 0 && (uint32_t)rc != 0x80920001u /* already initialized */) {
        totk_ps5_klogf("[totk-ps5] scePadInit failed: 0x%x\n", (unsigned)rc);
        return -1;
    }
    g_pad.handle = scePadOpen(g_pad.user_id, 0 /* STANDARD */, 0, NULL);
    if (g_pad.handle < 0) {
        totk_ps5_klogf("[totk-ps5] scePadOpen failed: 0x%x\n", (unsigned)g_pad.handle);
        return -1;
    }
    g_pad.initialized = 1;
    return 0;
}

void totk_ps5_input_shutdown(void) {
    if (g_pad.handle >= 0) {
        scePadClose(g_pad.handle);
    }
    memset(&g_pad, 0, sizeof(g_pad));
    g_pad.user_id = -1;
    g_pad.handle = -1;
}
