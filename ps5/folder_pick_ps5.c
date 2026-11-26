/*
 * ps5/folder_pick_ps5.c
 *
 * PS5 backend for runtime/folder_pick.h (no desktop folder picker dialog on PS5).
 */

#include "folder_pick.h"
#include <stddef.h>

void folder_pick(const char *start, FolderPickDone done, void *ctx) {
    (void)start;
    if (done) {
        done(NULL, ctx);
    }
}
