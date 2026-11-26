/*
 * ps5/plat_ps5_mem.c
 *
 * PS5 direct-memory arena implementation replacing Linux mmap/userfaultfd
 * guest RAM reservations from totk-linux-native-recomp/runtime/platform/linux.c.
 */

#include "plat_ps5.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static size_t align_up(size_t value, size_t align) {
    return (value + align - 1u) & ~(align - 1u);
}

void totk_ps5_klogf(const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    sceKernelDebugOutText(0, buf);
}

int totk_ps5_platform_init(struct ps5_memory_stats *out_stats) {
    ps5_klog_capture_stderr("[totk-ps5] ");
    struct ps5_memory_stats stats;
    memset(&stats, 0, sizeof(stats));
    if (!ps5_memory_query(&stats)) {
        return -1;
    }
    if (out_stats) {
        *out_stats = stats;
    }
    return 0;
}

int totk_ps5_arena_reserve(TotkPs5Arena *arena, size_t size_bytes, size_t alignment) {
    if (!arena || size_bytes == 0) {
        return -1;
    }
    memset(arena, 0, sizeof(*arena));
    size_t aligned_align = alignment < PS5_KERNEL_DIRECT_ALIGNMENT
                               ? PS5_KERNEL_DIRECT_ALIGNMENT
                               : align_up(alignment, PS5_KERNEL_DIRECT_ALIGNMENT);
    size_t aligned_size = align_up(size_bytes, PS5_KERNEL_DIRECT_ALIGNMENT);

    void *addr = NULL;
    int32_t rc = sceKernelReserveVirtualRange(&addr, aligned_size, 0, aligned_align);
    if (rc != 0 || addr == NULL) {
        totk_ps5_klogf("[totk-ps5] sceKernelReserveVirtualRange(%zu) failed: 0x%x\n",
                       aligned_size, (unsigned)rc);
        return -1;
    }

    arena->base = addr;
    arena->reserved_bytes = aligned_size;
    return 0;
}

int totk_ps5_arena_commit(TotkPs5Arena *arena, size_t offset, size_t length, int prot) {
    if (!arena || !arena->base || length == 0) {
        return -1;
    }

    size_t aligned_off = offset & ~(PS5_KERNEL_DIRECT_ALIGNMENT - 1u);
    size_t end_off = align_up(offset + length, PS5_KERNEL_DIRECT_ALIGNMENT);
    if (end_off > arena->reserved_bytes) {
        return -1;
    }
    size_t commit_len = end_off - aligned_off;

    int64_t total_dmem = sceKernelGetDirectMemorySize();
    if (total_dmem <= 0) {
        return -1;
    }

    int64_t phys = 0;
    int32_t rc = sceKernelAllocateDirectMemory(
        0,
        total_dmem,
        commit_len,
        PS5_KERNEL_DIRECT_ALIGNMENT,
        PS5_KERNEL_DIRECT_TYPE_CPU,
        &phys
    );
    if (rc != 0) {
        totk_ps5_klogf("[totk-ps5] sceKernelAllocateDirectMemory(%zu) failed: 0x%x\n",
                       commit_len, (unsigned)rc);
        return -1;
    }

    void *target = (void *)((uintptr_t)arena->base + aligned_off);
    rc = sceKernelMapDirectMemory(
        &target,
        commit_len,
        prot,
        PS5_KERNEL_MAP_FIXED,
        phys,
        PS5_KERNEL_DIRECT_ALIGNMENT
    );
    if (rc != 0) {
        sceKernelReleaseDirectMemory(phys, commit_len);
        totk_ps5_klogf("[totk-ps5] sceKernelMapDirectMemory failed: 0x%x\n", (unsigned)rc);
        return -1;
    }

    if (arena->chunk_count == arena->chunk_cap) {
        size_t next_cap = arena->chunk_cap ? arena->chunk_cap * 2u : 32u;
        int64_t *next = (int64_t *)realloc(arena->phys_chunks, next_cap * 2u * sizeof(int64_t));
        if (!next) {
            return -1;
        }
        arena->phys_chunks = next;
        arena->chunk_cap = next_cap;
    }
    arena->phys_chunks[arena->chunk_count * 2u] = phys;
    arena->phys_chunks[arena->chunk_count * 2u + 1u] = (int64_t)commit_len;
    arena->chunk_count++;
    arena->committed_bytes += commit_len;
    return 0;
}

void totk_ps5_arena_destroy(TotkPs5Arena *arena) {
    if (!arena) {
        return;
    }
    if (arena->base && arena->reserved_bytes > 0) {
        sceKernelMunmap(arena->base, arena->reserved_bytes);
    }
    for (size_t i = 0; i < arena->chunk_count; ++i) {
        int64_t phys = arena->phys_chunks[i * 2u];
        size_t len = (size_t)arena->phys_chunks[i * 2u + 1u];
        sceKernelReleaseDirectMemory(phys, len);
    }
    free(arena->phys_chunks);
    memset(arena, 0, sizeof(*arena));
}
