/*
 * ps5/platform_ps5.c
 *
 * PlayStation 5 (Prospero) implementation of totk-linux-native-recomp's
 * runtime/platform/platform.h using libkernel + libps5platform + Mesa RADV PS5.
 */

#include "platform/platform.h"
#include "plat_ps5.h"
#include <ps5platform/shm.h>
#include <ps5platform/heap.h>

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <ucontext.h>
#include <unistd.h>

/* Direct static Mesa RADV PS5 Vulkan ICD entry point */
extern void *vk_icdGetInstanceProcAddr(void *instance, const char *name);
extern int32_t sceKernelUsleep(uint32_t microseconds);
extern void ps5_arc4random_buf(void *buf, size_t len);
extern int32_t sceSystemServiceHideSplashScreen(void);
extern int32_t sceUserServiceInitialize(const void *params);
extern int32_t sceUserServiceGetInitialUser(int32_t *user_id);
extern int32_t sceUserServiceGetUserName(int32_t user_id, char *user_name, size_t size);
extern int32_t scePthreadSetprio(pthread_t thread, int prio);
extern void rt_log(const char *fmt, ...);
extern void *kern_cpu(void) __attribute__((weak));
extern int kern_thread_state(uint32_t handle) __attribute__((weak));

/* ---- Live PS5 diagnostic counters, thread sampler & watchdog ---- */
static volatile uint64_t g_wd_fibers = 0;
static volatile uint64_t g_wd_cond_waits = 0;
static volatile uint64_t g_wd_cond_signals = 0;
static volatile uint64_t g_wd_commits = 0;
static volatile uint64_t g_wd_ww_faults = 0;
static volatile uint64_t g_wd_threads_created = 0;
static volatile uint64_t g_wd_yields = 0;
static volatile uint64_t g_wd_sleeps = 0;
static volatile uint64_t g_wd_last_sleep_ns = 0;
static volatile uint64_t g_wd_now_calls = 0;
static volatile uint64_t g_wd_ctr_calls = 0;
static volatile int32_t g_wd_in_cond_wait = 0;
static volatile int32_t g_wd_in_mutex_lock = 0;
static volatile int32_t g_wd_in_sleep = 0;
static volatile int32_t g_wd_started = 0;

typedef struct Ps5TrackedThr {
    pthread_t pt;
    char name[32];
    volatile int32_t active;
} Ps5TrackedThr;

#define WD_MAX_THR 32
static Ps5TrackedThr g_wd_thr[WD_MAX_THR];
static volatile int32_t g_wd_thr_n = 0;

typedef struct Ps5Sample {
    volatile int32_t armed;
    volatile int32_t done;
    uintptr_t rip;
    uintptr_t rsp;
    uintptr_t rbp;
    uintptr_t frames[6];
    int nframes;
    uint64_t guest_pc;
    uint64_t guest_lr;
} Ps5Sample;
static Ps5Sample g_wd_sample;

static void ps5_sample_handler(int sig, siginfo_t *si, void *uctx) {
    (void)sig; (void)si;
    if (!__atomic_load_n(&g_wd_sample.armed, __ATOMIC_ACQUIRE)) return;
    const ucontext_t *uc = (const ucontext_t *)uctx;
    uintptr_t rip = uc ? (uintptr_t)uc->uc_mcontext.mc_rip : 0;
    uintptr_t rsp = uc ? (uintptr_t)uc->uc_mcontext.mc_rsp : 0;
    uintptr_t rbp = uc ? (uintptr_t)uc->uc_mcontext.mc_rbp : 0;
    g_wd_sample.rip = rip;
    g_wd_sample.rsp = rsp;
    g_wd_sample.rbp = rbp;
    int nf = 0;
    uintptr_t lo = rsp, hi = rsp + (8u << 20);
    uintptr_t fp = rbp;
    while (nf < 6 && fp >= lo && fp < hi && !(fp & 7)) {
        g_wd_sample.frames[nf++] = ((const uintptr_t *)fp)[1];
        uintptr_t next = ((const uintptr_t *)fp)[0];
        if (next <= fp) break;
        fp = next;
    }
    g_wd_sample.nframes = nf;
    uint64_t gpc = 0, glr = 0;
    if (kern_cpu) {
        const uint64_t *cpu = (const uint64_t *)kern_cpu();
        if (cpu) {
            glr = cpu[30];
            gpc = cpu[33]; /* offset 264 = 33 * 8 */
        }
    }
    g_wd_sample.guest_pc = gpc;
    g_wd_sample.guest_lr = glr;
    __atomic_store_n(&g_wd_sample.armed, 0, __ATOMIC_RELEASE);
    __atomic_store_n(&g_wd_sample.done, 1, __ATOMIC_RELEASE);
}

static void ps5_wd_sample_all(int sec) {
    uintptr_t ref = (uintptr_t)&plat_now_ns;
    int n = __atomic_load_n(&g_wd_thr_n, __ATOMIC_ACQUIRE);
    if (n > WD_MAX_THR) n = WD_MAX_THR;
    rt_log("ps5-samp: t=%ds ref(plat_now_ns)=%#llx tracked=%d", sec, (unsigned long long)ref, n);
    for (int i = 0; i < n; ++i) {
        if (!__atomic_load_n(&g_wd_thr[i].active, __ATOMIC_ACQUIRE)) continue;
        memset((void *)&g_wd_sample, 0, sizeof(g_wd_sample));
        __atomic_store_n(&g_wd_sample.armed, 1, __ATOMIC_RELEASE);
        if (pthread_kill(g_wd_thr[i].pt, SIGUSR1) != 0) {
            __atomic_store_n(&g_wd_sample.armed, 0, __ATOMIC_RELEASE);
            continue;
        }
        for (int w = 0; w < 50 && !__atomic_load_n(&g_wd_sample.done, __ATOMIC_ACQUIRE); ++w) {
            sceKernelUsleep(1000u);
        }
        __atomic_store_n(&g_wd_sample.armed, 0, __ATOMIC_RELEASE);
        if (__atomic_load_n(&g_wd_sample.done, __ATOMIC_ACQUIRE)) {
            long long d0 = (long long)(g_wd_sample.rip - ref);
            long long f0 = g_wd_sample.nframes > 0 ? (long long)(g_wd_sample.frames[0] - ref) : 0;
            long long f1 = g_wd_sample.nframes > 1 ? (long long)(g_wd_sample.frames[1] - ref) : 0;
            long long f2 = g_wd_sample.nframes > 2 ? (long long)(g_wd_sample.frames[2] - ref) : 0;
            long long f3 = g_wd_sample.nframes > 3 ? (long long)(g_wd_sample.frames[3] - ref) : 0;
            rt_log("ps5-samp: [%d:%s] rip=%#llx(d=%+lld) bt=[%+lld,%+lld,%+lld,%+lld] gpc=%#llx glr=%#llx",
                   i, g_wd_thr[i].name, (unsigned long long)g_wd_sample.rip, d0,
                   f0, f1, f2, f3,
                   (unsigned long long)g_wd_sample.guest_pc,
                   (unsigned long long)g_wd_sample.guest_lr);
        } else {
            rt_log("ps5-samp: [%d:%s] no-reply (blocked/exited)", i, g_wd_thr[i].name);
        }
    }
    if (kern_thread_state) {
        char stbuf[256];
        int k = 0;
        for (uint32_t h = 0x1001; h <= 0x1014 && k < 220; ++h) {
            int st = kern_thread_state(h);
            if (st >= 0) k += snprintf(stbuf + k, sizeof(stbuf) - (size_t)k, " %#x=%d", h, st);
        }
        rt_log("ps5-samp: guest_states:%s", k ? stbuf : " none");
    }
}

static void *ps5_watchdog_thread(void *arg) {
    (void)arg;
    for (int tick = 1; tick <= 6; ++tick) {
        sceKernelUsleep(5000000u); /* every 5s for first 30s */
        struct ps5_memory_stats s;
        unsigned long long free_mb = 0, flex_mb = 0;
        if (ps5_memory_query(&s)) {
            free_mb = (unsigned long long)(s.free_bytes >> 20);
            flex_mb = (unsigned long long)(s.flexible_bytes >> 20);
        }
        rt_log("ps5-wd: t=%ds thr=%llu fib=%llu com=%llu wwf=%llu free=%lluMiB flex=%lluMiB",
               tick * 5,
               (unsigned long long)__atomic_load_n(&g_wd_threads_created, __ATOMIC_RELAXED),
               (unsigned long long)__atomic_load_n(&g_wd_fibers, __ATOMIC_RELAXED),
               (unsigned long long)__atomic_load_n(&g_wd_commits, __ATOMIC_RELAXED),
               (unsigned long long)__atomic_load_n(&g_wd_ww_faults, __ATOMIC_RELAXED),
               free_mb, flex_mb);
    }
    return NULL;
}

static void ps5_start_watchdog(void) {
    const char *wd = getenv("TOTK_PS5_WATCHDOG");
    if (!wd || strcmp(wd, "1") != 0) return;
    int32_t zero = 0;
    if (__atomic_compare_exchange_n(&g_wd_started, &zero, 1, 0, __ATOMIC_ACQ_REL, __ATOMIC_RELAXED)) {
        struct sigaction sa;
        memset(&sa, 0, sizeof(sa));
        sa.sa_sigaction = ps5_sample_handler;
        sa.sa_flags = SA_SIGINFO | SA_RESTART;
        sigemptyset(&sa.sa_mask);
        sigaction(SIGUSR1, &sa, NULL);
        pthread_t pt;
        if (pthread_create(&pt, NULL, ps5_watchdog_thread, NULL) == 0) {
            pthread_detach(pt);
        }
    }
}

/* ---- Per-PS5-User Save Isolation (Saúl vs Yazmín, etc.) ---- */
static void ps5_init_user_profile(void) {
    /* Force FSR 3.1.5 Frame Generation permanently OFF on PS5 */
    setenv("TOTK_FRAME_GEN", "off", 1);

    /* Ensure base saves root exists */
    mkdir("/data/totk-ps5", 0777);
    mkdir("/data/totk-ps5/saves", 0777);

    int32_t init_rc = sceUserServiceInitialize(NULL);
    (void)init_rc; /* 0x80960003 ALREADY_INITIALIZED is fine */

    int32_t uid = 0;
    if (sceUserServiceGetInitialUser(&uid) != 0 || uid <= 0) {
        totk_ps5_klogf("[totk-ps5] user-save: GetInitialUser unavailable, using shared /data/totk-ps5/saves\n");
        return;
    }

    char uname[64];
    memset(uname, 0, sizeof(uname));
    if (sceUserServiceGetUserName(uid, uname, sizeof(uname)) != 0 || !uname[0]) {
        snprintf(uname, sizeof(uname), "user_%08x", (unsigned)uid);
    }

    char user_dir[256];
    snprintf(user_dir, sizeof(user_dir), "/data/totk-ps5/saves/user_%08x", (unsigned)uid);

    /* One-time lossless migration of legacy shared /data/totk-ps5/saves/save -> first user's folder */
    struct stat st_legacy;
    int has_legacy = (stat("/data/totk-ps5/saves/save", &st_legacy) == 0 && S_ISDIR(st_legacy.st_mode));
    if (has_legacy) {
        int has_any_user_dir = 0;
        DIR *d = opendir("/data/totk-ps5/saves");
        if (d) {
            struct dirent *de;
            while ((de = readdir(d)) != NULL) {
                if (strncmp(de->d_name, "user_", 5) == 0) {
                    has_any_user_dir = 1;
                    break;
                }
            }
            closedir(d);
        }
        if (!has_any_user_dir) {
            mkdir(user_dir, 0777);
            static const char *const legacy_items[] = {
                "account.uid", "save", "save-backup", "save-tx", "temp", "cache", "playtime.txt", "resolution"
            };
            for (size_t i = 0; i < sizeof(legacy_items) / sizeof(legacy_items[0]); ++i) {
                char src[320], dst[320];
                snprintf(src, sizeof(src), "/data/totk-ps5/saves/%s", legacy_items[i]);
                snprintf(dst, sizeof(dst), "%s/%s", user_dir, legacy_items[i]);
                rename(src, dst);
            }
            totk_ps5_klogf("[totk-ps5] user-save: migrated legacy save to %s (%s)\n", user_dir, uname);
        }
    }

    mkdir(user_dir, 0777);
    setenv("TOTK_PROFILE_DIR", user_dir, 1);
    totk_ps5_klogf("[totk-ps5] user-save: active PS5 user '%s' (0x%08x) -> %s\n", uname, (unsigned)uid, user_dir);
}

/* ---- Startup / klog hook ---- */
static uint64_t g_start_ns = 0;

__attribute__((constructor)) static void ps5_early_ctor(void) {
    sceKernelDebugOutText(0, "[totk-ps5] BOOT: eboot constructor entered\n");
    ps5_klog_capture_stderr("[totk-ps5] ");
    ps5_init_user_profile();
}

static void ps5_ensure_init(void) {
    if (__atomic_load_n(&g_start_ns, __ATOMIC_ACQUIRE) != 0) return;
    ps5_klog_capture_stderr("[totk-ps5] ");
    sceSystemServiceHideSplashScreen();
    sceKernelDebugOutText(0, "[totk-ps5] BOOT: splash hidden, platform init OK\n");
    ps5_start_watchdog();
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    uint64_t now = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
    uint64_t zero = 0;
    __atomic_compare_exchange_n(&g_start_ns, &zero, now ? now : 1, 0, __ATOMIC_RELEASE, __ATOMIC_RELAXED);
}

/* ---- Threads ---- */
struct PlatThread {
    pthread_t pt;
    PlatThreadFn fn;
    void *arg;
    pthread_mutex_t mu;
    pthread_cond_t cv;
    int done;
    int detached;
};

static _Thread_local uint32_t tl_tid = 0;
static volatile uint32_t g_next_tid = 1;

uint32_t plat_thread_id(void) {
    if (!tl_tid) {
        tl_tid = __atomic_fetch_add(&g_next_tid, 1, __ATOMIC_RELAXED);
    }
    return tl_tid;
}

static void *thread_trampoline(void *p) {
    PlatThread *t = (PlatThread *)p;
    int slot = -1;
    for (int i = 0; i < WD_MAX_THR; ++i) {
        if (__atomic_load_n(&g_wd_thr[i].active, __ATOMIC_ACQUIRE) && pthread_equal(g_wd_thr[i].pt, pthread_self())) {
            slot = i;
            break;
        }
    }
    (void)plat_thread_id();
    t->fn(t->arg);
    if (slot >= 0) __atomic_store_n(&g_wd_thr[slot].active, 0, __ATOMIC_RELEASE);
    pthread_mutex_lock(&t->mu);
    t->done = 1;
    int det = t->detached;
    pthread_cond_broadcast(&t->cv);
    pthread_mutex_unlock(&t->mu);
    if (det) {
        pthread_mutex_destroy(&t->mu);
        pthread_cond_destroy(&t->cv);
        free(t);
    }
    return NULL;
}

PlatThread *plat_thread_new_ex(PlatThreadFn fn, void *arg, const char *name, size_t stack) {
    (void)name;
    ps5_ensure_init();
    PlatThread *t = (PlatThread *)calloc(1, sizeof(*t));
    if (!t) return NULL;
    t->fn = fn;
    t->arg = arg;
    pthread_mutex_init(&t->mu, NULL);
    pthread_cond_init(&t->cv, NULL);

    pthread_attr_t attr;
    pthread_attr_init(&attr);
    /* PS5 eagerly charges pthread stacks to the small flexible memory budget (~720 MiB).
     * TOTK spawns 50-100 guest threads (guest stacks live in direct memory via Cpu::sp),
     * so keep host pthread stacks compact (1 MiB for workers, 2 MiB for guest main). */
    size_t max_st = (name && strcmp(name, "guest main") == 0) ? (2u << 20) : (1u << 20);
    size_t st = stack ? stack : max_st;
    if (st > max_st) st = max_st;
    if (st < (256u << 10)) st = (256u << 10);
    pthread_attr_setstacksize(&attr, st);

    int rc = pthread_create(&t->pt, &attr, thread_trampoline, t);
    if (rc != 0 && st > (512u << 10)) {
        st = (512u << 10);
        pthread_attr_setstacksize(&attr, st);
        rc = pthread_create(&t->pt, &attr, thread_trampoline, t);
    }
    pthread_attr_destroy(&attr);
    if (rc != 0) {
        rt_log("ps5-thr: pthread_create('%s', %zu) FAILED rc=%d (created=%llu)",
               name ? name : "unnamed", st, rc,
               (unsigned long long)__atomic_load_n(&g_wd_threads_created, __ATOMIC_RELAXED));
        pthread_mutex_destroy(&t->mu);
        pthread_cond_destroy(&t->cv);
        free(t);
        return NULL;
    }
    __atomic_fetch_add(&g_wd_threads_created, 1, __ATOMIC_RELAXED);
    int idx = __atomic_fetch_add(&g_wd_thr_n, 1, __ATOMIC_ACQ_REL);
    if (idx >= 0 && idx < WD_MAX_THR) {
        g_wd_thr[idx].pt = t->pt;
        snprintf(g_wd_thr[idx].name, sizeof(g_wd_thr[idx].name), "%s", name ? name : "unnamed");
        __atomic_store_n(&g_wd_thr[idx].active, 1, __ATOMIC_RELEASE);
    }
    return t;
}

PlatThread *plat_thread_new(PlatThreadFn fn, void *arg, const char *name) {
    return plat_thread_new_ex(fn, arg, name, 0);
}

int plat_thread_spawn(PlatThreadFn fn, void *arg, const char *name, size_t stack) {
    PlatThread *t = plat_thread_new_ex(fn, arg, name, stack);
    if (!t) return 0;
    plat_thread_detach(t);
    return 1;
}

void plat_thread_join(PlatThread *t) {
    if (!t) return;
    pthread_join(t->pt, NULL);
    pthread_mutex_destroy(&t->mu);
    pthread_cond_destroy(&t->cv);
    free(t);
}

int plat_thread_join_ns(PlatThread *t, uint64_t ns) {
    if (!t) return 1;
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    uint64_t nsec = (uint64_t)ts.tv_nsec + (ns % 1000000000ull);
    ts.tv_sec += (time_t)(ns / 1000000000ull + nsec / 1000000000ull);
    ts.tv_nsec = (long)(nsec % 1000000000ull);

    pthread_mutex_lock(&t->mu);
    while (!t->done) {
        if (pthread_cond_timedwait(&t->cv, &t->mu, &ts) == ETIMEDOUT) break;
    }
    int ok = t->done;
    pthread_mutex_unlock(&t->mu);
    if (ok) {
        plat_thread_join(t);
        return 1;
    }
    return 0;
}

void plat_thread_detach(PlatThread *t) {
    if (!t) return;
    pthread_detach(t->pt);
    pthread_mutex_lock(&t->mu);
    t->detached = 1;
    int done = t->done;
    pthread_mutex_unlock(&t->mu);
    if (done) {
        pthread_mutex_destroy(&t->mu);
        pthread_cond_destroy(&t->cv);
        free(t);
    }
}

uint64_t plat_thread_affinity(PlatThread *t, uint64_t mask) {
    pthread_t pt = t ? t->pt : pthread_self();
    uint64_t prev = 0;
    scePthreadGetaffinity(pt, &prev);
    if (mask) {
        scePthreadSetaffinity(pt, mask);
    }
    return prev;
}

uint32_t plat_cpu_count(void) { return 8; }
uint32_t plat_cpu_usable(void) { return 7; }
uint64_t plat_thread_cpu_ns(uint32_t tid) { (void)tid; return 0; }

int plat_cpu_cores(uint64_t *all, uint64_t *first) {
    if (all) *all = 0x7Full;
    if (first) *first = 0x7Full;
    return 7;
}

int plat_process_affinity(uint64_t mask) {
    (void)mask;
    return 1;
}

void plat_thread_priority(int prio) { (void)prio; }
void plat_thread_set_priority(PlatThread *t, int prio) { (void)t; (void)prio; }
int plat_thread_priority_get(void) { return 0; }
void plat_yield(void) {
    __atomic_fetch_add(&g_wd_yields, 1, __ATOMIC_RELAXED);
    sched_yield();
}

/* ---- Async thread interruption (Phase 1 safe placeholder) ---- */
struct PlatIntr {
    pthread_t pt;
};

PlatIntr *plat_intr_self(void) {
    PlatIntr *in = (PlatIntr *)calloc(1, sizeof(*in));
    if (in) in->pt = pthread_self();
    return in;
}

void plat_intr_free(PlatIntr *t) { free(t); }

int plat_intr_stop(PlatIntr *t, uint64_t *rip, uint64_t *rsp) {
    (void)t;
    if (rip) *rip = 0;
    if (rsp) *rsp = 0;
    return 0;
}

int plat_intr_resume(PlatIntr *t, uint64_t to) {
    (void)t;
    (void)to;
    return 0;
}

/* ---- Fibers (x86_64 SysV ABI callee-saved context switch) ---- */
typedef struct Ps5FiberRegs {
    uint64_t rsp;
    uint64_t rbx;
    uint64_t rbp;
    uint64_t r12;
    uint64_t r13;
    uint64_t r14;
    uint64_t r15;
    uint32_t mxcsr;
    uint16_t fcw;
    uint16_t pad;
} Ps5FiberRegs;

struct PlatFiber {
    Ps5FiberRegs regs;
    void *stack_base;
    size_t stack_size;
    void (*fn)(void *);
    void *arg;
    int is_thread_self;
};

static _Thread_local PlatFiber *tl_cur_fiber = NULL;
static _Thread_local PlatFiber tl_root_fiber;

__attribute__((naked)) static void ps5_fiber_swap(Ps5FiberRegs *from, const Ps5FiberRegs *to) {
    __asm__ volatile(
        "movq %%rsp, 0(%%rdi)\n"
        "movq %%rbx, 8(%%rdi)\n"
        "movq %%rbp, 16(%%rdi)\n"
        "movq %%r12, 24(%%rdi)\n"
        "movq %%r13, 32(%%rdi)\n"
        "movq %%r14, 40(%%rdi)\n"
        "movq %%r15, 48(%%rdi)\n"
        "stmxcsr 56(%%rdi)\n"
        "fnstcw 60(%%rdi)\n"
        "movq 0(%%rsi), %%rsp\n"
        "movq 8(%%rsi), %%rbx\n"
        "movq 16(%%rsi), %%rbp\n"
        "movq 24(%%rsi), %%r12\n"
        "movq 32(%%rsi), %%r13\n"
        "movq 40(%%rsi), %%r14\n"
        "movq 48(%%rsi), %%r15\n"
        "ldmxcsr 56(%%rsi)\n"
        "fldcw 60(%%rsi)\n"
        "ret\n"
        ::: "memory");
}

static void ps5_fiber_entry(void) {
    PlatFiber *f = tl_cur_fiber;
    f->fn(f->arg);
    _exit(1);
}

PlatFiber *plat_fiber_self(void) {
    memset(&tl_root_fiber, 0, sizeof(tl_root_fiber));
    tl_root_fiber.is_thread_self = 1;
    tl_cur_fiber = &tl_root_fiber;
    return &tl_root_fiber;
}

void plat_fiber_unself(void) {
    tl_cur_fiber = NULL;
}

PlatFiber *plat_fiber_new(size_t stack, void (*fn)(void *arg), void *arg) {
    PlatFiber *f = (PlatFiber *)calloc(1, sizeof(*f));
    if (!f) return NULL;
    size_t sz = stack ? stack : (1u << 20);
    if (sz > (1u << 20)) sz = (1u << 20);
    if (sz < (256u << 10)) sz = (256u << 10);
    void *mem = NULL;
    if (posix_memalign(&mem, 4096, sz) != 0 || !mem) {
        free(f);
        return NULL;
    }
    f->stack_base = mem;
    f->stack_size = sz;
    f->fn = fn;
    f->arg = arg;

    /* x86_64 SysV ABI requires RSP % 16 == 8 upon function entry (as if entered via CALL).
     * Since ps5_fiber_swap pops 8 bytes via RET into ps5_fiber_entry, place the return slot
     * at a 16-byte aligned address so RSP % 16 == 8 immediately after RET. */
    uintptr_t top = (((uintptr_t)mem + sz) & ~(uintptr_t)15) - 16;
    *(uint64_t *)top = (uint64_t)(uintptr_t)&ps5_fiber_entry;
    f->regs.rsp = top;
    f->regs.mxcsr = 0x1F80u;
    f->regs.fcw = 0x037Fu;
    return f;
}

void plat_fiber_switch(PlatFiber *to) {
    PlatFiber *from = tl_cur_fiber;
    if (!from || !to || from == to) return;
    __atomic_fetch_add(&g_wd_fibers, 1, __ATOMIC_RELAXED);
    tl_cur_fiber = to;
    ps5_fiber_swap(&from->regs, &to->regs);
}

void plat_fiber_free(PlatFiber *f) {
    if (!f || f->is_thread_self) return;
    free(f->stack_base);
    free(f);
}

/* ---- Clocks & sleep ---- */
uint64_t plat_now_ns(void) {
    __atomic_fetch_add(&g_wd_now_calls, 1, __ATOMIC_RELAXED);
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

uint64_t plat_counter(void) {
    __atomic_fetch_add(&g_wd_ctr_calls, 1, __ATOMIC_RELAXED);
    return sceKernelReadTsc();
}

uint64_t plat_counter_hz(void) {
    uint64_t hz = sceKernelGetTscFrequency();
    return hz ? hz : 1000000000ull;
}

void plat_timer_1ms(void) {}
int plat_power_full(void) { return -1; }
int plat_perf_core_setup(char *why, size_t n) {
    if (why && n) snprintf(why, n, "PS5 Zen 2 (OS scheduler across 7 cores)");
    return 0;
}
int plat_thread_perf_core(void) {
    /* Let PS5 OS scheduler balance all 7 homogeneous Zen 2 cores; 1-core pinning starves worker threads. */
    return 0;
}

void plat_sleep_ns(uint64_t ns) {
    if (ns == 0) return;
    __atomic_fetch_add(&g_wd_sleeps, 1, __ATOMIC_RELAXED);
    __atomic_store_n(&g_wd_last_sleep_ns, ns, __ATOMIC_RELAXED);
    __atomic_fetch_add(&g_wd_in_sleep, 1, __ATOMIC_RELAXED);
    if (ns > 60000000000ull) ns = 60000000000ull; /* clamp huge sleeps to 60s */
    uint64_t us = (ns + 999ull) / 1000ull;
    while (us > 1000000ull) {
        sceKernelUsleep(1000000u);
        us -= 1000000ull;
    }
    if (us > 0) sceKernelUsleep((uint32_t)us);
    __atomic_fetch_sub(&g_wd_in_sleep, 1, __ATOMIC_RELAXED);
}

void plat_wait_ns(uint64_t ns) {
    plat_sleep_ns(ns);
}

void plat_sleep_ms(uint32_t ms) {
    plat_sleep_ns((uint64_t)ms * 1000000ull);
}

/* ---- Locks & Condition Variables ---- */
typedef struct Ps5RwLock {
    pthread_mutex_t mu;
    pthread_cond_t cv;
    int readers;
    int writer;
    int waiting_writers;
} Ps5RwLock;

static Ps5RwLock *rw_get(PlatMutex *m) {
    Ps5RwLock *rw = (Ps5RwLock *)__atomic_load_n(&m->p, __ATOMIC_ACQUIRE);
    if (rw) return rw;
    Ps5RwLock *n = (Ps5RwLock *)calloc(1, sizeof(*n));
    pthread_mutex_init(&n->mu, NULL);
    pthread_cond_init(&n->cv, NULL);
    void *expected = NULL;
    if (!__atomic_compare_exchange_n(&m->p, &expected, n, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        pthread_mutex_destroy(&n->mu);
        pthread_cond_destroy(&n->cv);
        free(n);
        return (Ps5RwLock *)expected;
    }
    return n;
}

static pthread_cond_t *cv_get(PlatCond *c) {
    pthread_cond_t *cv = (pthread_cond_t *)__atomic_load_n(&c->p, __ATOMIC_ACQUIRE);
    if (cv) return cv;
    pthread_cond_t *n = (pthread_cond_t *)calloc(1, sizeof(*n));
    pthread_cond_init(n, NULL);
    void *expected = NULL;
    if (!__atomic_compare_exchange_n(&c->p, &expected, n, 0, __ATOMIC_ACQ_REL, __ATOMIC_ACQUIRE)) {
        pthread_cond_destroy(n);
        free(n);
        return (pthread_cond_t *)expected;
    }
    return n;
}

void plat_mutex_init(PlatMutex *m) { m->p = NULL; (void)rw_get(m); }

void plat_mutex_lock(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    __atomic_fetch_add(&g_wd_in_mutex_lock, 1, __ATOMIC_RELAXED);
    pthread_mutex_lock(&rw->mu);
    rw->waiting_writers++;
    while (rw->writer || rw->readers > 0) {
        pthread_cond_wait(&rw->cv, &rw->mu);
    }
    rw->waiting_writers--;
    rw->writer = 1;
    pthread_mutex_unlock(&rw->mu);
    __atomic_fetch_sub(&g_wd_in_mutex_lock, 1, __ATOMIC_RELAXED);
}

int plat_mutex_trylock(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_mutex_lock(&rw->mu);
    int ok = 0;
    if (!rw->writer && rw->readers == 0) {
        rw->writer = 1;
        ok = 1;
    }
    pthread_mutex_unlock(&rw->mu);
    return ok;
}

void plat_mutex_unlock(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_mutex_lock(&rw->mu);
    rw->writer = 0;
    pthread_cond_broadcast(&rw->cv);
    pthread_mutex_unlock(&rw->mu);
}

void plat_mutex_lock_shared(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_mutex_lock(&rw->mu);
    while (rw->writer || rw->waiting_writers > 0) {
        pthread_cond_wait(&rw->cv, &rw->mu);
    }
    rw->readers++;
    pthread_mutex_unlock(&rw->mu);
}

int plat_mutex_trylock_shared(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_mutex_lock(&rw->mu);
    int ok = 0;
    if (!rw->writer && rw->waiting_writers == 0) {
        rw->readers++;
        ok = 1;
    }
    pthread_mutex_unlock(&rw->mu);
    return ok;
}

void plat_mutex_unlock_shared(PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_mutex_lock(&rw->mu);
    rw->readers--;
    if (rw->readers == 0) pthread_cond_broadcast(&rw->cv);
    pthread_mutex_unlock(&rw->mu);
}

void plat_cond_init(PlatCond *c) { c->p = NULL; (void)cv_get(c); }

void plat_cond_wait(PlatCond *c, PlatMutex *m) {
    Ps5RwLock *rw = rw_get(m);
    pthread_cond_t *cv = cv_get(c);
    __atomic_fetch_add(&g_wd_cond_waits, 1, __ATOMIC_RELAXED);
    __atomic_fetch_add(&g_wd_in_cond_wait, 1, __ATOMIC_RELAXED);
    pthread_mutex_lock(&rw->mu);
    rw->writer = 0;
    pthread_cond_broadcast(&rw->cv);
    pthread_cond_wait(cv, &rw->mu);
    rw->waiting_writers++;
    while (rw->writer || rw->readers > 0) {
        pthread_cond_wait(&rw->cv, &rw->mu);
    }
    rw->waiting_writers--;
    rw->writer = 1;
    pthread_mutex_unlock(&rw->mu);
    __atomic_fetch_sub(&g_wd_in_cond_wait, 1, __ATOMIC_RELAXED);
}

int plat_cond_wait_ns(PlatCond *c, PlatMutex *m, uint64_t ns) {
    Ps5RwLock *rw = rw_get(m);
    pthread_cond_t *cv = cv_get(c);
    /* Clamp huge/infinite timeouts (e.g. INT64_MAX) so tv_sec never overflows */
    const uint64_t max_ns = 31536000ull * 1000000000ull; /* 1 year */
    if (ns > max_ns) ns = max_ns;
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    uint64_t nsec = (uint64_t)ts.tv_nsec + (ns % 1000000000ull);
    ts.tv_sec += (time_t)(ns / 1000000000ull + nsec / 1000000000ull);
    ts.tv_nsec = (long)(nsec % 1000000000ull);

    __atomic_fetch_add(&g_wd_cond_waits, 1, __ATOMIC_RELAXED);
    __atomic_fetch_add(&g_wd_in_cond_wait, 1, __ATOMIC_RELAXED);
    pthread_mutex_lock(&rw->mu);
    rw->writer = 0;
    pthread_cond_broadcast(&rw->cv);
    int rc = pthread_cond_timedwait(cv, &rw->mu, &ts);
    rw->waiting_writers++;
    while (rw->writer || rw->readers > 0) {
        pthread_cond_wait(&rw->cv, &rw->mu);
    }
    rw->waiting_writers--;
    rw->writer = 1;
    pthread_mutex_unlock(&rw->mu);
    __atomic_fetch_sub(&g_wd_in_cond_wait, 1, __ATOMIC_RELAXED);
    return rc == ETIMEDOUT ? 0 : 1;
}

void plat_cond_signal(PlatCond *c) {
    __atomic_fetch_add(&g_wd_cond_signals, 1, __ATOMIC_RELAXED);
    pthread_cond_signal(cv_get(c));
}
void plat_cond_broadcast(PlatCond *c) {
    __atomic_fetch_add(&g_wd_cond_signals, 1, __ATOMIC_RELAXED);
    pthread_cond_broadcast(cv_get(c));
}

/* ---- Virtual Memory (PS5 Direct Memory via libps5platform ps5_vrange_*) ---- */
#define PG_PROT_MASK 0x03u  /* 0=reserved, 1=none, 2=read, 3=rw */
#define PG_DIRTY     0x04u  /* 4 KiB page written since last plat_mem_written reset */
#define PG_WATCHED   0x08u  /* 4 KiB page has been queried by plat_mem_written */

typedef struct Ps5MemRange {
    uint64_t base;
    uint64_t size;
    int watch;
    uint8_t *page_state;        /* 1 byte per 4 KiB page: PG_PROT_MASK | PG_DIRTY | PG_WATCHED */
    volatile uint8_t *hw_clean; /* 1 byte per 16 KiB HW page: 1 = write-protected RO for write-watch */
} Ps5MemRange;

#define MAX_PS5_RANGES 64
static Ps5MemRange g_ranges[MAX_PS5_RANGES];
static volatile int g_range_count = 0;
static pthread_mutex_t g_mem_mu = PTHREAD_MUTEX_INITIALIZER;

static size_t align_up_sz(size_t v, size_t a) { return (v + a - 1u) & ~(a - 1u); }

static Ps5MemRange *find_range(uint64_t addr) {
    int n = __atomic_load_n(&g_range_count, __ATOMIC_ACQUIRE);
    for (int i = 0; i < n; ++i) {
        if (addr >= g_ranges[i].base && addr < g_ranges[i].base + g_ranges[i].size) {
            return &g_ranges[i];
        }
    }
    return NULL;
}

int plat_mem_reserve(uint64_t addr, uint64_t n, int watch) {
    ps5_ensure_init();
    pthread_mutex_lock(&g_mem_mu);
    int cur_n = __atomic_load_n(&g_range_count, __ATOMIC_RELAXED);
    if (cur_n >= MAX_PS5_RANGES || n == 0) {
        pthread_mutex_unlock(&g_mem_mu);
        return 0;
    }
    uint64_t aligned_addr = addr & ~(uint64_t)(PS5_KERNEL_DIRECT_ALIGNMENT - 1u);
    size_t aligned_size = align_up_sz((size_t)(addr + n - aligned_addr), PS5_KERNEL_DIRECT_ALIGNMENT);

    /* Never use MAP_FIXED over occupied PS5 kernel/GPU/heap ranges!
     * ps5_vrange_reserve_at safely rejects collisions with PS5_SHM_NO_PLACE. */
    int rc = ps5_vrange_reserve_at((void *)(uintptr_t)aligned_addr, aligned_size);
    if (rc != 0) {
        pthread_mutex_unlock(&g_mem_mu);
        return 0;
    }

    size_t npages = aligned_size >> 12;
    uint8_t *states = (uint8_t *)calloc(npages, 1);
    if (!states) {
        ps5_vrange_release((void *)(uintptr_t)aligned_addr, aligned_size);
        pthread_mutex_unlock(&g_mem_mu);
        return 0;
    }
    uint8_t *clean = NULL;
    if (watch) {
        size_t nhw = aligned_size >> 14;
        clean = (uint8_t *)calloc(nhw, 1);
        if (!clean) {
            free(states);
            ps5_vrange_release((void *)(uintptr_t)aligned_addr, aligned_size);
            pthread_mutex_unlock(&g_mem_mu);
            return 0;
        }
    }

    Ps5MemRange *r = &g_ranges[cur_n];
    r->base = aligned_addr;
    r->size = aligned_size;
    r->watch = watch;
    r->page_state = states;
    r->hw_clean = clean;
    __atomic_store_n(&g_range_count, cur_n + 1, __ATOMIC_RELEASE);
    totk_ps5_klogf("[totk-ps5] plat_mem_reserve OK: 0x%llx + 0x%llx (%llu MiB, watch=%d)\n",
                   (unsigned long long)aligned_addr, (unsigned long long)aligned_size,
                   (unsigned long long)(aligned_size >> 20), watch);
    pthread_mutex_unlock(&g_mem_mu);
    return 1;
}

void *plat_mem_alloc(size_t n) {
    ps5_ensure_init();
    if (n == 0) return NULL;
    return calloc(1, n);
}

static int hw_prot_for_16k(const Ps5MemRange *r, uint64_t hp) {
    uint64_t base_p = hp << 2;
    uint8_t mx = 0;
    for (uint64_t k = 0; k < 4; ++k) {
        uint8_t s = r->page_state[base_p + k] & PG_PROT_MASK;
        if (s > mx) mx = s;
    }
    if (mx >= 3) return PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE;
    if (mx == 2) return PS5_KERNEL_PROT_CPU_READ;
    return 0;
}

static void clear_hw_clean(Ps5MemRange *r, uint64_t p0, uint64_t p1) {
    if (!r->hw_clean) return;
    uint64_t max_hp = r->size >> 14;
    uint64_t hp0 = p0 >> 2;
    uint64_t hp1 = (p1 + 3u) >> 2;
    if (hp1 > max_hp) hp1 = max_hp;
    for (uint64_t hp = hp0; hp < hp1; ++hp) {
        __atomic_store_n(&r->hw_clean[hp], 0, __ATOMIC_RELEASE);
    }
}

static void ps5_sync_hw_prot(const Ps5MemRange *r, uint64_t p0, uint64_t p1) {
    uint64_t max_hp = r->size >> 14;
    uint64_t hp0 = p0 >> 2;
    uint64_t hp1 = (p1 + 3u) >> 2;
    if (hp1 > max_hp) hp1 = max_hp;
    uint64_t hp = hp0;
    while (hp < hp1) {
        int prot = hw_prot_for_16k(r, hp);
        uint64_t end_hp = hp + 1;
        while (end_hp < hp1 && hw_prot_for_16k(r, end_hp) == prot) end_hp++;
        void *va = (void *)(uintptr_t)(r->base + (hp << 14));
        size_t len = (size_t)((end_hp - hp) << 14);
        sceKernelMprotect(va, len, prot);
        hp = end_hp;
    }
}

static void ps5_ww_touch_range(uint64_t addr, size_t n) {
    if (n == 0) return;
    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (r && r->hw_clean && addr + n <= r->base + r->size) {
        uint64_t p0 = (addr - r->base) >> 12;
        uint64_t p1 = ((addr + n - r->base) + 0xFFFull) >> 12;
        uint64_t hp0 = p0 >> 2;
        uint64_t hp1 = (p1 + 3u) >> 2;
        uint64_t max_hp = r->size >> 14;
        if (hp1 > max_hp) hp1 = max_hp;
        uint64_t hp = hp0;
        while (hp < hp1) {
            if (__atomic_load_n(&r->hw_clean[hp], __ATOMIC_ACQUIRE) &&
                hw_prot_for_16k(r, hp) == (PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE)) {
                uint64_t end_hp = hp + 1;
                while (end_hp < hp1 &&
                       __atomic_load_n(&r->hw_clean[end_hp], __ATOMIC_ACQUIRE) &&
                       hw_prot_for_16k(r, end_hp) == (PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE)) {
                    end_hp++;
                }
                sceKernelMprotect((void *)(uintptr_t)(r->base + (hp << 14)),
                                  (size_t)((end_hp - hp) << 14),
                                  PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE);
                for (uint64_t h = hp; h < end_hp; ++h) {
                    __atomic_store_n(&r->hw_clean[h], 0, __ATOMIC_RELEASE);
                }
                hp = end_hp;
            } else {
                hp++;
            }
        }
    }
    pthread_mutex_unlock(&g_mem_mu);
}

int plat_mem_commit(uint64_t addr, size_t n) {
    if (n == 0) return 1;
    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (!r || addr + n > r->base + r->size) {
        pthread_mutex_unlock(&g_mem_mu);
        return 0;
    }

    int rc = ps5_vrange_commit((void *)(uintptr_t)addr, n, PS5_SHM_READ | PS5_SHM_WRITE);
    if (rc != 0) {
        rt_log("ps5-mem: ps5_vrange_commit(0x%llx, %zu) FAILED: 0x%x",
               (unsigned long long)addr, n, (unsigned)rc);
        totk_ps5_klogf("[totk-ps5] ps5_vrange_commit(0x%llx, %zu) failed: 0x%x\n",
                       (unsigned long long)addr, n, (unsigned)rc);
        pthread_mutex_unlock(&g_mem_mu);
        return 0;
    }

    uint64_t p0 = (addr - r->base) >> 12;
    uint64_t p1 = ((addr + n - r->base) + 0xFFFull) >> 12;
    clear_hw_clean(r, p0, p1);
    for (uint64_t p = p0; p < p1; ++p) r->page_state[p] = 3u | PG_DIRTY; /* RW + dirty */
    __atomic_fetch_add(&g_wd_commits, 1, __ATOMIC_RELAXED);
    pthread_mutex_unlock(&g_mem_mu);
    return 1;
}

static int unit_64k_is_free(const Ps5MemRange *r, uint64_t u) {
    uint64_t base_p = u << 4;
    for (uint64_t k = 0; k < 16; ++k) {
        if ((r->page_state[base_p + k] & PG_PROT_MASK) != 0) return 0;
    }
    return 1;
}

int plat_mem_decommit(uint64_t addr, uint64_t n) {
    if (n == 0) return 1;
    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (r && addr + n <= r->base + r->size) {
        uint64_t p0 = (addr - r->base) >> 12;
        uint64_t p1 = ((addr + n - r->base) + 0xFFFull) >> 12;
        /* Mark freed 4 KiB pages; only decommit 64 KiB units that are completely empty
         * so adjacent live Switch 4 KiB pages inside the same 16 KiB/64 KiB PS5 unit are preserved. */
        uint64_t u0 = p0 >> 4;
        uint64_t u1 = (p1 + 15u) >> 4;
        uint64_t max_u = r->size >> 16;
        if (u1 > max_u) u1 = max_u;

        clear_hw_clean(r, p0, p1);
        for (uint64_t p = p0; p < p1; ++p) r->page_state[p] = 0;

        uint64_t u = u0;
        while (u < u1) {
            if (unit_64k_is_free(r, u)) {
                uint64_t end_u = u + 1;
                while (end_u < u1 && unit_64k_is_free(r, end_u)) end_u++;
                ps5_vrange_decommit((void *)(uintptr_t)(r->base + (u << 16)),
                                    (size_t)((end_u - u) << 16));
                u = end_u;
            } else {
                /* Unit still has live 4 KiB neighbors: zero only the newly freed 4 KiB sub-pages. */
                uint64_t zp0 = (u << 4) > p0 ? (u << 4) : p0;
                uint64_t zp1 = ((u + 1) << 4) < p1 ? ((u + 1) << 4) : p1;
                if (zp0 < zp1) {
                    void *hw_va = (void *)(uintptr_t)(r->base + ((zp0 >> 2) << 14));
                    size_t hw_len = (size_t)((((zp1 + 3u) >> 2) - (zp0 >> 2)) << 14);
                    sceKernelMprotect(hw_va, hw_len, PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE);
                    memset((void *)(uintptr_t)(r->base + (zp0 << 12)), 0, (size_t)((zp1 - zp0) << 12));
                    ps5_sync_hw_prot(r, zp0, zp1);
                }
                u++;
            }
        }
    }
    pthread_mutex_unlock(&g_mem_mu);
    return 1;
}

int plat_mem_protect(uint64_t addr, uint64_t n, int prot) {
    if (n == 0) return 1;
    uint8_t st = 1;
    if (prot == PLAT_PROT_READ) st = 2;
    else if (prot == PLAT_PROT_RW) st = 3;

    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (r && addr + n <= r->base + r->size) {
        uint64_t p0 = (addr - r->base) >> 12;
        uint64_t p1 = ((addr + n - r->base) + 0xFFFull) >> 12;
        int had_uncommitted = 0;
        clear_hw_clean(r, p0, p1);
        for (uint64_t p = p0; p < p1; ++p) {
            uint8_t old = r->page_state[p];
            if ((old & PG_PROT_MASK) == 0) had_uncommitted = 1;
            uint8_t flags = (old & PG_WATCHED) | ((st == 3) ? PG_DIRTY : (old & PG_DIRTY));
            r->page_state[p] = st | flags;
        }
        /* PS5 hardware pages are 16 KiB while Switch pages are 4 KiB.
         * Never strip permissions from a 16 KiB hardware page if any sibling 4 KiB page
         * still needs higher access (e.g. ThreadType living next to a 4 KiB-aligned moved stack). */
        if (had_uncommitted && st >= 2) {
            int shm_prot = (st == 3) ? (PS5_SHM_READ | PS5_SHM_WRITE) : PS5_SHM_READ;
            ps5_vrange_commit((void *)(uintptr_t)addr, (size_t)n, shm_prot);
        }
        ps5_sync_hw_prot(r, p0, p1);
    }
    pthread_mutex_unlock(&g_mem_mu);
    return 1;
}

int plat_mem_state(uint64_t addr, uint64_t limit, uint64_t *end) {
    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (!r) {
        if (end) *end = limit;
        pthread_mutex_unlock(&g_mem_mu);
        return PLAT_MEM_FREE;
    }
    uint64_t p = (addr - r->base) >> 12;
    uint64_t max_p = (r->size) >> 12;
    uint8_t s0 = r->page_state[p] & PG_PROT_MASK;
    while (p < max_p && (r->page_state[p] & PG_PROT_MASK) == s0 && (r->base + (p << 12)) < limit) p++;
    if (end) {
        uint64_t e = r->base + (p << 12);
        *end = e < limit ? e : limit;
    }
    pthread_mutex_unlock(&g_mem_mu);
    if (s0 == 0) return PLAT_MEM_RESERVED;
    if (s0 == 1) return PLAT_PROT_NONE;
    if (s0 == 2) return PLAT_PROT_READ;
    return PLAT_PROT_RW;
}

uint64_t plat_mem_written(uint64_t addr, uint64_t n, uint64_t *pages, uint64_t max, int reset) {
    if (!max || !n) return 0;
    pthread_mutex_lock(&g_mem_mu);
    Ps5MemRange *r = find_range(addr);
    if (!r || !r->hw_clean || addr + n > r->base + r->size) {
        pthread_mutex_unlock(&g_mem_mu);
        return UINT64_MAX;
    }

    uint64_t p0 = (addr - r->base) >> 12;
    uint64_t p1 = ((addr + n - r->base) + 0xFFFull) >> 12;
    uint64_t hp0 = p0 >> 2;
    uint64_t hp1 = (p1 + 3u) >> 2;
    uint64_t max_hp = r->size >> 14;
    if (hp1 > max_hp) hp1 = max_hp;

    uint64_t got = 0;
    uint64_t wp_start = 0, wp_end = 0;

    for (uint64_t hp = hp0; hp < hp1; ++hp) {
        int is_clean = __atomic_load_n(&r->hw_clean[hp], __ATOMIC_ACQUIRE) != 0;
        uint64_t base_p = hp << 2;
        int is_rw = (hw_prot_for_16k(r, hp) == (PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE));
        if (!is_rw) continue;

        /* If the 16 KiB HW page was writable (not clean), any watched/queried RW sub-page may have been written. */
        if (!is_clean) {
            for (uint64_t k = 0; k < 4; ++k) {
                uint64_t sp = base_p + k;
                uint8_t s = r->page_state[sp];
                if ((s & PG_PROT_MASK) == 3u && ((s & PG_WATCHED) || (sp >= p0 && sp < p1))) {
                    r->page_state[sp] = s | PG_DIRTY;
                }
            }
        }

        /* Count dirty sub-pages in this 16 KiB block that fall inside [p0, p1). */
        uint64_t q0 = base_p > p0 ? base_p : p0;
        uint64_t q1 = (base_p + 4u) < p1 ? (base_p + 4u) : p1;
        uint64_t need = 0;
        for (uint64_t sp = q0; sp < q1; ++sp) {
            uint8_t s = r->page_state[sp];
            if ((s & PG_PROT_MASK) == 3u && (s & PG_DIRTY)) need++;
        }
        if (got + need > max) {
            break;
        }
        for (uint64_t sp = q0; sp < q1; ++sp) {
            uint8_t s = r->page_state[sp];
            if ((s & PG_PROT_MASK) == 3u) {
                s |= PG_WATCHED;
                if (s & PG_DIRTY) {
                    pages[got++] = r->base + (sp << 12);
                    if (reset) s &= (uint8_t)~PG_DIRTY;
                }
                r->page_state[sp] = s;
            }
        }

        /* Arm 16 KiB HW write-protect (RO) once no watched sub-page inside it remains dirty. */
        if (reset && !is_clean) {
            int any_dirty = 0;
            for (uint64_t k = 0; k < 4; ++k) {
                uint8_t s = r->page_state[base_p + k];
                if ((s & PG_PROT_MASK) == 3u && (s & PG_WATCHED) && (s & PG_DIRTY)) {
                    any_dirty = 1;
                    break;
                }
            }
            if (!any_dirty) {
                __atomic_store_n(&r->hw_clean[hp], 1, __ATOMIC_RELEASE);
                if (wp_end == hp) {
                    wp_end = hp + 1;
                } else {
                    if (wp_end > wp_start) {
                        sceKernelMprotect((void *)(uintptr_t)(r->base + (wp_start << 14)),
                                          (size_t)((wp_end - wp_start) << 14),
                                          PS5_KERNEL_PROT_CPU_READ);
                    }
                    wp_start = hp;
                    wp_end = hp + 1;
                }
            }
        }
    }

    if (wp_end > wp_start) {
        sceKernelMprotect((void *)(uintptr_t)(r->base + (wp_start << 14)),
                          (size_t)((wp_end - wp_start) << 14),
                          PS5_KERNEL_PROT_CPU_READ);
    }

    pthread_mutex_unlock(&g_mem_mu);
    return got;
}

static int (*g_fault_hook)(uint64_t addr) = NULL;
static void (*g_crash_hook)(const PlatCrash *c) = NULL;

static void ps5_sigsegv_handler(int sig, siginfo_t *si, void *uctx) {
    uint64_t fault_addr = (uint64_t)(uintptr_t)(si ? si->si_addr : NULL);
    /* Lock-free fast path for PS5 write-watch (hw_clean == 1 -> restore RW and mark dirty). */
    if (sig == SIGSEGV && fault_addr) {
        Ps5MemRange *r = find_range(fault_addr);
        if (r && r->hw_clean) {
            uint64_t hp = (fault_addr - r->base) >> 14;
            if (__atomic_load_n(&r->hw_clean[hp], __ATOMIC_ACQUIRE) != 0) {
                void *hp_va = (void *)(uintptr_t)(r->base + (hp << 14));
                sceKernelMprotect(hp_va, PS5_KERNEL_PAGE_SIZE,
                                  PS5_KERNEL_PROT_CPU_READ | PS5_KERNEL_PROT_CPU_WRITE);
                __atomic_store_n(&r->hw_clean[hp], 0, __ATOMIC_RELEASE);
                __atomic_fetch_add(&g_wd_ww_faults, 1, __ATOMIC_RELAXED);
                return;
            }
        }
    }
    if (g_fault_hook && fault_addr && g_fault_hook(fault_addr)) {
        return;
    }
    uintptr_t rip = 0;
    if (uctx) {
        ucontext_t *uc = (ucontext_t *)uctx;
        rip = (uintptr_t)uc->uc_mcontext.mc_rip;
    }
    rt_log("ps5-sig: UNHANDLED signal=%d addr=%#llx rip=%#llx",
           sig, (unsigned long long)fault_addr, (unsigned long long)rip);
    if (g_crash_hook) {
        PlatCrash c;
        memset(&c, 0, sizeof(c));
        c.what = sig == SIGSEGV ? "access violation" : "signal";
        c.code = (uint32_t)sig;
        c.addr = fault_addr;
        c.access = 0;
        c.rip = rip;
        g_crash_hook(&c);
    }
    _exit(128 + sig);
}

static void install_signal_handlers(void) {
    static int installed = 0;
    if (installed) return;
    installed = 1;
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa));
    sa.sa_sigaction = ps5_sigsegv_handler;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    sigaction(SIGBUS, &sa, NULL);
    sigaction(SIGILL, &sa, NULL);
}

void plat_mem_fault_hook(int (*fn)(uint64_t addr)) {
    g_fault_hook = fn;
    install_signal_handlers();
}

void plat_crash_hook(void (*fn)(const PlatCrash *c)) {
    g_crash_hook = fn;
    install_signal_handlers();
}

_Noreturn void plat_reexec(void) { _exit(0); }

int plat_mem_readable(uint64_t addr, uint64_t n) {
    if (n == 0) return 1;
    uint64_t cur = addr;
    uint64_t lim = addr + n;
    while (cur < lim) {
        uint64_t end = lim;
        int st = plat_mem_state(cur, lim, &end);
        if (st != PLAT_PROT_READ && st != PLAT_PROT_RW) return 0;
        if (end <= cur) break;
        cur = end;
    }
    return 1;
}

int plat_mem_read(uint64_t addr, void *out, size_t n) {
    if (!plat_mem_readable(addr, n)) return 0;
    memcpy(out, (const void *)(uintptr_t)addr, n);
    return 1;
}

extern int gfx_window_monitor_size(int *w, int *h) __attribute__((weak));

int plat_screen_size(int *w, int *h) {
    if (gfx_window_monitor_size) return gfx_window_monitor_size(w, h);
    if (w) *w = 1920;
    if (h) *h = 1080;
    return 1;
}

void *plat_aligned_alloc(size_t size, size_t align) {
    void *p = NULL;
    if (align < sizeof(void *)) align = sizeof(void *);
    return posix_memalign(&p, align, size) == 0 ? p : NULL;
}

void plat_aligned_free(void *p) { free(p); }

/* ---- Process & Time ---- */
_Noreturn void plat_exit(int code) { _exit(code); }

int plat_setenv(const char *name, const char *value) {
    if (!name) return 0;
    return (value ? setenv(name, value, 1) : unsetenv(name)) == 0 ? 1 : 0;
}

uint32_t plat_process_id(void) { return (uint32_t)getpid(); }
uint64_t plat_process_cpu_ns(void) { return 0; }
uint64_t plat_process_uptime_ns(void) {
    ps5_ensure_init();
    uint64_t now = plat_now_ns();
    return now >= g_start_ns ? now - g_start_ns : 0;
}

uint64_t plat_unix_time_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

void plat_local_time(struct tm *out) {
    time_t t = time(NULL);
    localtime_r(&t, out);
}

int plat_localtime(int64_t unix_s, struct tm *out) {
    time_t t = (time_t)unix_s;
    return localtime_r(&t, out) != NULL ? 1 : 0;
}

int plat_gmtime(int64_t unix_s, struct tm *out) {
    time_t t = (time_t)unix_s;
    return gmtime_r(&t, out) != NULL ? 1 : 0;
}

long plat_tz_west(void) { return 0; }

int plat_run_self(const char *e, const char *v, char *out, size_t cap, uint32_t ms) {
    (void)e; (void)v; (void)ms;
    if (out && cap) out[0] = '\0';
    return -1;
}

int plat_random(void *out, size_t n) {
    if (!out || n == 0) return 1;
    ps5_arc4random_buf(out, n);
    return 1;
}

/* ---- Files & Host FS ---- */
static _Thread_local int tl_fs_err = 0;

static int map_errno(int e) {
    tl_fs_err = e;
    switch (e) {
    case 0: return PLAT_FS_OK;
    case ENOENT: return PLAT_FS_NOT_FOUND;
    case EEXIST: return PLAT_FS_EXISTS;
    case ENOTEMPTY: return PLAT_FS_NOT_EMPTY;
    case EBUSY: return PLAT_FS_BUSY;
    default: return PLAT_FS_ERROR;
    }
}

int plat_fs_os_error(void) { return tl_fs_err; }

int plat_file_exists(const char *path) {
    struct stat st;
    return (path && stat(path, &st) == 0 && S_ISREG(st.st_mode)) ? 1 : 0;
}

int plat_dir_exists(const char *path) {
    struct stat st;
    return (path && stat(path, &st) == 0 && S_ISDIR(st.st_mode)) ? 1 : 0;
}

int plat_full_path(const char *path, char *out, size_t cap) {
    if (!path || !out || cap == 0) return 0;
    if (path[0] == '/') {
        if (strlen(path) + 1 > cap) return 0;
        strcpy(out, path);
        return 1;
    }
    int n = snprintf(out, cap, "/data/totk-ps5/%s", path);
    return n > 0 && (size_t)n < cap;
}

void plat_file_mkdir_p(const char *path) {
    if (!path || !*path) return;
    char tmp[PLAT_PATH_MAX];
    size_t len = strlen(path);
    if (len >= sizeof(tmp)) return;
    memcpy(tmp, path, len + 1);
    for (char *p = tmp + 1; *p; ++p) {
        if (*p == '/') {
            *p = '\0';
            mkdir(tmp, 0777);
            *p = '/';
        }
    }
    mkdir(tmp, 0777);
}

uint8_t *plat_file_read(const char *path, uint64_t *size) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;
    struct stat st;
    if (fstat(fd, &st) != 0 || st.st_size <= 0 || st.st_size > (1ll << 30)) {
        close(fd);
        return NULL;
    }
    uint8_t *buf = (uint8_t *)malloc((size_t)st.st_size + 1u);
    if (!buf) {
        close(fd);
        return NULL;
    }
    size_t got = 0;
    while (got < (size_t)st.st_size) {
        ssize_t r = read(fd, buf + got, (size_t)st.st_size - got);
        if (r <= 0) break;
        got += (size_t)r;
    }
    close(fd);
    if (got != (size_t)st.st_size) {
        free(buf);
        return NULL;
    }
    buf[got] = 0;
    if (size) *size = got;
    return buf;
}

int plat_file_write(const char *path, const void *data, size_t n) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0666);
    if (fd < 0) return 0;
    size_t done = 0;
    const uint8_t *p = (const uint8_t *)data;
    while (done < n) {
        ssize_t w = write(fd, p + done, n - done);
        if (w <= 0) { close(fd); return 0; }
        done += (size_t)w;
    }
    close(fd);
    return 1;
}

int plat_file_replace(const char *from, const char *to) {
    return rename(from, to) == 0 ? 1 : 0;
}

int plat_file_write_atomic(const char *path, const void *data, size_t n) {
    char tmp[PLAT_PATH_MAX];
    snprintf(tmp, sizeof(tmp), "%s.%u.%u.tmp", path, plat_process_id(), plat_thread_id());
    if (!plat_file_write(tmp, data, n)) return 0;
    return rename(tmp, path) == 0 ? 1 : 0;
}

int plat_file_flush(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return 0;
    int ok = fsync(fd) == 0 ? 1 : 0;
    close(fd);
    return ok;
}

int plat_file_sync(FILE *f) {
    if (!f) return 0;
    fflush(f);
    return fsync(fileno(f)) == 0 ? 1 : 0;
}

void plat_file_delete(const char *path) { if (path) unlink(path); }
int plat_file_truncate(const char *path, uint64_t size) { return truncate(path, (off_t)size) == 0 ? 1 : 0; }

int64_t plat_file_size(const char *path) {
    struct stat st;
    return (path && stat(path, &st) == 0) ? (int64_t)st.st_size : -1;
}

int plat_file_set_readonly(const char *path, int on) {
    return chmod(path, on ? 0444 : 0666) == 0 ? 1 : 0;
}

struct PlatAppend { int fd; };

PlatAppend *plat_append_open(const char *path) {
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC | O_APPEND, 0666);
    if (fd < 0) return NULL;
    PlatAppend *a = (PlatAppend *)malloc(sizeof(*a));
    if (!a) { close(fd); return NULL; }
    a->fd = fd;
    return a;
}

int plat_append_write(PlatAppend *f, const void *data, size_t n) {
    if (!f) return 0;
    return write(f->fd, data, n) == (ssize_t)n ? 1 : 0;
}

int plat_file_list(const char *dir, const char *ext, int (*cb)(const char *name, void *ctx), void *ctx) {
    DIR *d = opendir(dir);
    if (!d) return 0;
    size_t elen = ext ? strlen(ext) : 0;
    struct dirent *de;
    while ((de = readdir(d)) != NULL) {
        if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, "..")) continue;
        size_t nlen = strlen(de->d_name);
        if (elen && (nlen < elen || strcmp(de->d_name + nlen - elen, ext) != 0)) continue;
        if (!cb(de->d_name, ctx)) break;
    }
    closedir(d);
    return 1;
}

struct PlatFile {
    int fd;
    void *mapped;
    size_t mapped_size;
};

PlatFile *plat_file_open(const char *path) {
    int fd = open(path, O_RDONLY);
    if (fd < 0) return NULL;
    PlatFile *f = (PlatFile *)calloc(1, sizeof(*f));
    if (!f) { close(fd); return NULL; }
    f->fd = fd;
    return f;
}

PlatFile *plat_file_open_unbuffered(const char *path) {
    return plat_file_open(path);
}

void plat_file_close(PlatFile *f) {
    if (!f) return;
    if (f->fd >= 0) close(f->fd);
    free(f);
}

int64_t plat_file_pread(PlatFile *f, void *buf, uint32_t n, uint64_t off) {
    if (!f) return -1;
    ssize_t r = pread(f->fd, buf, n, (off_t)off);
    if (r < 0 && errno == EFAULT) {
        ps5_ww_touch_range((uint64_t)(uintptr_t)buf, n);
        r = pread(f->fd, buf, n, (off_t)off);
        if (r < 0 && errno == EFAULT) return -2;
    }
    return (int64_t)r;
}

int plat_file_id(PlatFile *f, PlatFileId *out) {
    if (!f || !out) return 0;
    struct stat st;
    if (fstat(f->fd, &st) != 0) return 0;
    out->volume = (uint64_t)st.st_dev;
    out->file_id = (uint64_t)st.st_ino;
    out->size = (uint64_t)st.st_size;
    out->write_time = (uint64_t)st.st_mtim.tv_sec * 1000000000ull + (uint64_t)st.st_mtim.tv_nsec;
    out->create_time = (uint64_t)st.st_ctim.tv_sec * 1000000000ull + (uint64_t)st.st_ctim.tv_nsec;
    return 1;
}

const void *plat_file_map(PlatFile *f) {
    if (!f) return NULL;
    if (f->mapped) return f->mapped;
    struct stat st;
    if (fstat(f->fd, &st) != 0 || st.st_size <= 0) return NULL;
    void *p = mmap(NULL, (size_t)st.st_size, PROT_READ, MAP_PRIVATE, f->fd, 0);
    if (p == MAP_FAILED) return NULL;
    f->mapped = p;
    f->mapped_size = (size_t)st.st_size;
    return p;
}

int plat_fs_kind(const char *path) {
    struct stat st;
    if (stat(path, &st) != 0) { tl_fs_err = errno; return PLAT_FS_MISSING; }
    if (S_ISDIR(st.st_mode)) return PLAT_FS_DIR;
    return PLAT_FS_FILE;
}

int plat_fs_mkdir(const char *path) {
    if (mkdir(path, 0777) == 0) return PLAT_FS_OK;
    int e = errno;
    struct stat st;
    if (stat(path, &st) == 0) return PLAT_FS_EXISTS;
    return map_errno(e);
}
int plat_fs_rmdir(const char *path) { return rmdir(path) == 0 ? PLAT_FS_OK : map_errno(errno); }
int plat_fs_unlink(const char *path) { return unlink(path) == 0 ? PLAT_FS_OK : map_errno(errno); }

int plat_fs_rename(const char *from, const char *to, int durable) {
    (void)durable;
    struct stat st;
    if (stat(to, &st) == 0) return map_errno(EEXIST);
    return rename(from, to) == 0 ? PLAT_FS_OK : map_errno(errno);
}

int plat_fs_link(const char *existing, const char *path) {
    /* PS5 libkernel does not export hardlink link(); returning PLAT_FS_ERROR makes
     * fs_host.c fall back cleanly to copy_file(). */
    (void)existing;
    (void)path;
    tl_fs_err = ENOSYS;
    return PLAT_FS_ERROR;
}

int plat_fs_links(const char *path) {
    struct stat st;
    return stat(path, &st) == 0 ? (int)st.st_nlink : 0;
}

void plat_fs_sync_dir(const char *path) {
    (void)path;
}

void plat_fs_busy_reason(const char *dir, char *out, size_t cap) {
    (void)dir;
    if (out && cap) out[0] = '\0';
}

int plat_fs_list(const char *dir, int (*cb)(const char *name, int kind, uint64_t size, void *ctx), void *ctx) {
    DIR *d = opendir(dir);
    if (!d) return map_errno(errno);
    struct dirent *de;
    char full[PLAT_PATH_MAX];
    while ((de = readdir(d)) != NULL) {
        if (!strcmp(de->d_name, ".") || !strcmp(de->d_name, "..")) continue;
        snprintf(full, sizeof(full), "%s/%s", dir, de->d_name);
        struct stat st;
        int kind = PLAT_FS_FILE;
        uint64_t sz = 0;
        if (stat(full, &st) == 0) {
            kind = S_ISDIR(st.st_mode) ? PLAT_FS_DIR : PLAT_FS_FILE;
            sz = (uint64_t)st.st_size;
        }
        if (!cb(de->d_name, kind, sz, ctx)) break;
    }
    closedir(d);
    return PLAT_FS_OK;
}

PlatFile *plat_fs_open(const char *path, int write, int *err) {
    int fd = open(path, write ? O_RDWR : O_RDONLY);
    if (fd < 0) {
        if (err) *err = map_errno(errno);
        return NULL;
    }
    PlatFile *f = (PlatFile *)calloc(1, sizeof(*f));
    if (!f) { close(fd); if (err) *err = PLAT_FS_ERROR; return NULL; }
    f->fd = fd;
    if (err) *err = PLAT_FS_OK;
    return f;
}

PlatFile *plat_fs_create(const char *path, int *err) {
    int fd = open(path, O_RDWR | O_CREAT | O_EXCL, 0666);
    if (fd < 0) {
        if (err) *err = map_errno(errno);
        return NULL;
    }
    PlatFile *f = (PlatFile *)calloc(1, sizeof(*f));
    if (!f) { close(fd); if (err) *err = PLAT_FS_ERROR; return NULL; }
    f->fd = fd;
    if (err) *err = PLAT_FS_OK;
    return f;
}

int64_t plat_file_pwrite(PlatFile *f, const void *buf, uint32_t n, uint64_t off) {
    if (!f) return -1;
    return (int64_t)pwrite(f->fd, buf, n, (off_t)off);
}

int plat_file_set_size(PlatFile *f, uint64_t size) {
    if (!f) return PLAT_FS_ERROR;
    return ftruncate(f->fd, (off_t)size) == 0 ? PLAT_FS_OK : map_errno(errno);
}

int plat_file_fsync(PlatFile *f) {
    return (f && fsync(f->fd) == 0) ? 1 : 0;
}

int plat_temp_dir(char *out, size_t cap) {
    const char *d = "/data/totk-ps5/tmp";
    plat_file_mkdir_p(d);
    int n = snprintf(out, cap, "%s", d);
    return n > 0 && (size_t)n < cap;
}

int plat_exe_path(char *out, size_t cap) {
    int n = snprintf(out, cap, "/data/totk-ps5/eboot.bin");
    return n > 0 && (size_t)n < cap;
}

uintptr_t plat_exe_base(void) { return 0; }

int plat_module_of(uintptr_t addr, char *name, size_t cap, uintptr_t *base) {
    (void)addr;
    if (name && cap) name[0] = '\0';
    if (base) *base = 0;
    return 0;
}

size_t plat_getenv(const char *name, char *out, size_t cap) {
    const char *v = name ? getenv(name) : NULL;
    if (!v || !out || cap == 0) return 0;
    size_t len = strlen(v);
    if (len >= cap) len = cap - 1;
    memcpy(out, v, len);
    out[len] = '\0';
    return len;
}

const char *plat_ui_language(void) { return "en-US"; }
const char *plat_user_locale(void) { return "en-US"; }
int plat_font_path(const char *lang, char *out, size_t cap) {
    (void)lang;
    if (out && cap) out[0] = '\0';
    return 0;
}

int plat_os_version(char *out, size_t cap) {
    struct ps5_kernel_sw_version sw;
    memset(&sw, 0, sizeof(sw));
    sw.size = sizeof(sw);
    if (sceKernelGetSystemSwVersion(&sw) == 0) {
        snprintf(out, cap, "PS5 Prospero FW %s", sw.text);
        return 1;
    }
    snprintf(out, cap, "PS5 Prospero");
    return 1;
}

int plat_is_wine(void) { return 0; }
int plat_stderr_path(char *out, size_t cap) { if (out && cap) out[0] = '\0'; return 0; }
int plat_clipboard_set(const char *utf8) { (void)utf8; return 0; }
int plat_open_folder(const char *path) { (void)path; return 0; }

/* ---- Static Mesa RADV PS5 Vulkan bridge ---- */
static int g_vulkan_sentinel = 1;

void *plat_lib_open(const char *name) {
    if (name && strstr(name, "vulkan")) {
        return &g_vulkan_sentinel;
    }
    return NULL;
}

void *plat_lib_sym(void *lib, const char *name) {
    if (lib == &g_vulkan_sentinel && name &&
        (strcmp(name, "vkGetInstanceProcAddr") == 0 ||
         strcmp(name, "vk_icdGetInstanceProcAddr") == 0)) {
        return (void *)(uintptr_t)&vk_icdGetInstanceProcAddr;
    }
    return NULL;
}

void plat_lib_error(char *out, size_t cap) {
    snprintf(out, cap, "dynamic dlopen unsupported on PS5 (only static RADV Vulkan is provided)");
}

int plat_ngx_core_path(char *out, size_t cap) { if (out && cap) out[0] = '\0'; return 0; }
int plat_exe_dir_wide(wchar_t *out, size_t cap) { if (out && cap) out[0] = 0; return 0; }

/* ---- Telemetry & Memory Stats (via ps5_memory_query) ---- */
struct PlatLoad { int dummy; };
PlatLoad *plat_load_open(const uint8_t *gpu_luid, int pci_bus) {
    (void)gpu_luid; (void)pci_bus;
    return (PlatLoad *)calloc(1, sizeof(PlatLoad));
}
void plat_load_close(PlatLoad *l) { free(l); }
void plat_cpu_load(PlatLoad *l, float *total_pct, float *proc_pct, float *temp_c) {
    (void)l;
    if (total_pct) *total_pct = 0.0f;
    if (proc_pct) *proc_pct = 0.0f;
    if (temp_c) *temp_c = 0.0f;
}
void plat_gpu_load(PlatLoad *l, float *load_pct, float *vram_used_mb) {
    (void)l;
    if (load_pct) *load_pct = 0.0f;
    if (vram_used_mb) *vram_used_mb = 0.0f;
}

void plat_mem_info(float *used_mb, float *total_mb, float *proc_mb) {
    struct ps5_memory_stats s;
    if (ps5_memory_query(&s)) {
        float tot = (float)(s.total_bytes / (1024.0 * 1024.0));
        float used = (float)((s.total_bytes - s.free_bytes) / (1024.0 * 1024.0));
        if (total_mb) *total_mb = tot;
        if (used_mb) *used_mb = used;
        if (proc_mb) *proc_mb = used;
    } else {
        if (total_mb) *total_mb = 12288.0f;
        if (used_mb) *used_mb = 0.0f;
        if (proc_mb) *proc_mb = 0.0f;
    }
}

void plat_commit_info(double *proc_mb, double *used_mb, double *limit_mb) {
    float u = 0, t = 0, p = 0;
    plat_mem_info(&u, &t, &p);
    if (proc_mb) *proc_mb = p;
    if (used_mb) *used_mb = u;
    if (limit_mb) *limit_mb = t;
}

void plat_mem_room(uint64_t *commit_room, uint64_t *phys_room) {
    struct ps5_memory_stats s;
    if (ps5_memory_query(&s)) {
        if (commit_room) *commit_room = s.free_bytes;
        if (phys_room) *phys_room = s.free_bytes;
    } else {
        if (commit_room) *commit_room = 4ull << 30;
        if (phys_room) *phys_room = 4ull << 30;
    }
}

void plat_process_memory(uint64_t *resident, uint64_t *private_bytes) {
    struct ps5_memory_stats s;
    uint64_t used = 0;
    if (ps5_memory_query(&s) && s.total_bytes >= s.free_bytes) {
        used = s.total_bytes - s.free_bytes;
    }
    if (resident) *resident = used;
    if (private_bytes) *private_bytes = used;
}

/* ---- Child processes / IPC (PS5 forbids child process spawning) ---- */
struct PlatChild { int dummy; };
PlatChild *plat_child_start(const char *exe, const char *arg, uint32_t *err) {
    totk_ps5_klogf("[totk-ps5] plat_child_start(%s, %s): child processes unsupported on PS5; use pre-translated shader cache\n",
                   exe ? exe : "(null)", arg ? arg : "(null)");
    if (err) *err = EPERM;
    return NULL;
}
void plat_child_stop(PlatChild *c) { free(c); }
int plat_child_write(PlatChild *c, const void *data, size_t n) { (void)c; (void)data; (void)n; return 0; }
long plat_child_read(PlatChild *c, void *buf, size_t cap) { (void)c; (void)buf; (void)cap; return -1; }

struct PlatIpc { int dummy; };
PlatIpc *plat_ipc_connect(const char *name) { (void)name; return NULL; }
int plat_ipc_read(PlatIpc *p, void *buf, size_t n, uint32_t ms) { (void)p; (void)buf; (void)n; (void)ms; return -1; }
int plat_ipc_write(PlatIpc *p, const void *buf, size_t n) { (void)p; (void)buf; (void)n; return 0; }
void plat_ipc_close(PlatIpc *p) { free(p); }

int plat_restart(void) { return 0; }
int plat_spawn(const char *const *argv, const char *cwd) { (void)argv; (void)cwd; return 0; }
int plat_restart_wait(uint32_t timeout_ms) { (void)timeout_ms; return 0; }

/* PS5 libkernel does not export fork() or isatty(); keep hidden so eboot.bin has zero unexported imports. */
__attribute__((visibility("hidden")))
pid_t fork(void) {
    errno = ENOSYS;
    return -1;
}

__attribute__((visibility("hidden")))
int isatty(int fd) {
    (void)fd;
    return 0;
}
