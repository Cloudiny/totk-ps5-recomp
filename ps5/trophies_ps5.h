/*
 * ps5/trophies_ps5.h
 *
 * PlayStation 5 Trophy system for Tears of the Kingdom (PPSA99199).
 * - Per-PS5-user persistence in <TOTK_PROFILE_DIR>/trophies.json (isolated per user)
 * - Zero gameplay FPS overhead: evaluates progress.sav only on save mount & commit
 * - Triggers native PS5 system notification (sceKernelSendNotificationRequest)
 *   plus an in-game PS5-style trophy toast banner and dedicated "Trofeos" menu tab.
 */

#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    PS5_TROPHY_BRONZE = 0,
    PS5_TROPHY_SILVER = 1,
    PS5_TROPHY_GOLD = 2,
    PS5_TROPHY_PLATINUM = 3
} Ps5TrophyTier;

typedef struct {
    const char *id;
    const char *title;
    const char *desc;
    Ps5TrophyTier tier;
    int unlocked;
    uint64_t unlocked_at;
    int cur;     /* current progress for multi-step trophies (0 if boolean) */
    int target;  /* target count (1 for boolean) */
} Ps5TrophyView;

/* Scan the newest slot_00..slot_05/progress.sav under save_root (called on mount & save commit). */
void ps5_trophies_scan_save(const char *save_root);

/* Query trophy list for the ImGui "Trofeos" tab. */
int ps5_trophies_count(void);
int ps5_trophies_get(int index, Ps5TrophyView *out);
void ps5_trophies_summary(int *unlocked_total, int *bronze, int *silver, int *gold, int *platinum);
const char *ps5_trophies_user_label(void);

/* Banner queue for ImGui overlay (returns 1 while a banner should be drawn). */
int ps5_trophies_toast_active(void);
int ps5_trophies_current_banner(Ps5TrophyView *out, float *alpha_out);

#ifdef __cplusplus
}
#endif
