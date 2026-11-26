// SPDX-License-Identifier: MIT
// 75% logical-CPU thermal thread cap for shader preparation (adapted from Triforce v0.8.3).
// Leaves thermal/OS headroom on 8-core PS5 Zen 2 (8 -> 6 threads) and PC builder hosts while
// allowing explicit override via TOTK_PREPARE_THREADS / PS5_PREPARE_THREADS.
#pragma once

static inline int ps5_prepare_threads(int cpus, int asked) {
    if (cpus < 1) cpus = 1;
    if (asked > 0) return asked > 64 ? 64 : asked;
    int t = cpus - cpus / 4;
    int half = cpus / 2;
    if (half < 1) half = 1;
    if (t < half) t = half;
    if (t > 64) t = 64;
    return t;
}
