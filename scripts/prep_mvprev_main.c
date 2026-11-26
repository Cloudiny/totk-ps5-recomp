
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "cfg.h"
#include "gfx.h"
#include "host.h"
#include "platform/platform.h"

extern void sha256(const void *data, size_t len, uint8_t out[32]);

void rt_sha256(const void *p, size_t n, uint8_t out[32]) { sha256(p, n, out); }
void rt_log(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stdout, fmt, ap);
    fprintf(stdout, "\n");
    fflush(stdout);
    va_end(ap);
}
void rt_fatal(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "FATAL: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    exit(1);
}
const char *rt_data_dir(void) {
    const char *d = getenv("TOTK_PREP_DIR");
    return d ? d : ".";
}
const char *rt_exe_dir(void) { return rt_data_dir(); }
int rt_knob(const char *name, const char *def) {
    char key[128];
    snprintf(key, sizeof key, "TOTK_%s", name);
    const char *v = cfg_get(key);
    if (!v || !*v) v = def;
    return v ? atoi(v) : 0;
}
int gfx_window_monitor_size(int *w, int *h) {
    if (w) *w = 2560;
    if (h) *h = 1440;
    return 1;
}
int kern_core_away(void) { return 0; }
void kern_core_back(int *a) { (void)a; }
uint64_t perf_begin(void) { return 0; }
void perf_end(int k, uint64_t t) { (void)k; (void)t; }
void vk_hdr_shader_swap(uint32_t **spirv, uint64_t *words) { (void)spirv; (void)words; }
int input_prompts_pick(void) { return 0; }
const char *input_prompts_folder(int p) { (void)p; return NULL; }
int romfs_shaped_prompts_ready(const char *a, unsigned w, unsigned h) { (void)a; (void)w; (void)h; return 0; }
int SDL_SetClipboardText(const char *s) { (void)s; return 0; }

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "usage: %s <stage_dir> [threads] [procs]\n", argv[0]);
        return 2;
    }
    const char *dir = argv[1];
    int threads = argc > 2 ? atoi(argv[2]) : 12;
    int procs = argc > 3 ? atoi(argv[3]) : 10;
    setenv("TOTK_PREP_DIR", dir, 1);
    cfg_init();
    uint32_t sg[3] = {64, 32, 32};
    gfx_shader_set_host(1, 0, sg, 8, 0);
    return gfx_shader_prepare_seed(dir, threads, procs);
}
