/*
 * ps5/plat_ps5.h
 *
 * Core PS5 platform bridge declarations for porting totk-linux-native-recomp
 * onto PlayStation 5 via libps5platform + Mesa RADV PS5.
 *
 * Mirrors the contracts of:
 *   - totk-linux-native-recomp/runtime/platform/platform.h
 *   - totk-linux-native-recomp/runtime/gfx_wsys.h
 */

#ifndef TOTK_PS5_PLAT_H
#define TOTK_PS5_PLAT_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include <ps5platform/kernel.h>
#include <ps5platform/klog.h>
#include <ps5platform/memory.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Direct-memory reservation backed by PS5 sceKernelReserveVirtualRange +
 * on-demand sceKernelAllocateDirectMemory / sceKernelMapDirectMemory commits.
 * PS5 kernel page = 16 KiB, direct-memory allocation unit = 64 KiB. */
typedef struct TotkPs5Arena {
    void *base;
    size_t reserved_bytes;
    size_t committed_bytes;
    int64_t *phys_chunks;
    size_t chunk_count;
    size_t chunk_cap;
} TotkPs5Arena;

/* Initialize klog capture and query available PS5 direct/flexible memory. */
int totk_ps5_platform_init(struct ps5_memory_stats *out_stats);

/* Reserve an aligned virtual address range for Switch guest RAM (e.g. 4 GiB). */
int totk_ps5_arena_reserve(TotkPs5Arena *arena, size_t size_bytes, size_t alignment);

/* Commit a 64 KiB-aligned subrange within a reserved arena using PS5 direct memory. */
int totk_ps5_arena_commit(TotkPs5Arena *arena, size_t offset, size_t length, int prot);

/* Release all physical direct memory chunks and unmap the virtual reservation. */
void totk_ps5_arena_destroy(TotkPs5Arena *arena);

/* Logging helper routing formatted output to PS5 klog (klogsrv port 3232). */
void totk_ps5_klogf(const char *fmt, ...);

#ifdef __cplusplus
}
#endif

#endif /* TOTK_PS5_PLAT_H */
