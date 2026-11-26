// SPDX-License-Identifier: MIT
// RADV < 26.2.5 native MeshEXT NumWorkgroups liveness guard (adapted from Longshot #2338 / Mesa ac_nir_lower_ngg_ms):
// PS5 bundles Mesa RADV 26.2.0 (< 26.2.5). When a MeshEXT shader declares BuiltIn NumWorkgroups, keeps a live load
// of NumWorkgroups.x != 0 into OpSetMeshOutputsEXT's primitive count so NIR DCE cannot strip grid-size SGPRs.
// Complete no-op (zero allocation) for non-MeshEXT shaders.
#pragma once

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

static inline uint32_t *spirv_radv_keep_num_workgroups(const uint32_t *w, uint64_t n, uint64_t *out_n) {
    if (!w || n < 5 || w[0] != 0x07230203u) return NULL;

    enum {
        OP_ENTRY_POINT = 15,
        OP_TYPE_BOOL = 20,
        OP_TYPE_INT = 21,
        OP_TYPE_VECTOR = 23,
        OP_TYPE_POINTER = 32,
        OP_CONSTANT = 43,
        OP_FUNCTION = 54,
        OP_VARIABLE = 59,
        OP_LOAD = 61,
        OP_DECORATE = 71,
        OP_COMPOSITE_EXTRACT = 81,
        OP_I_NOT_EQUAL = 171,
        OP_SELECT = 169,
        OP_SET_MESH_OUTPUTS_EXT = 5295,
        MODEL_MESH_EXT = 5365,
        DEC_BUILTIN = 11,
        BI_NUM_WORKGROUPS = 24,
        SC_INPUT = 1
    };

    int is_mesh = 0;
    uint32_t bound = w[3];
    uint32_t nwg_var = 0;
    uint32_t t_bool = 0, t_u32 = 0, t_v3u32 = 0, c_u32_zero = 0;
    uint64_t set_mesh_at = 0;
    uint64_t first_func = 0;

    for (uint64_t i = 5; i < n;) {
        uint32_t wc = w[i] >> 16, op = w[i] & 0xFFFFu;
        if (!wc || i + wc > n) return NULL;
        if (op == OP_ENTRY_POINT && wc >= 3 && w[i + 1] == MODEL_MESH_EXT) {
            is_mesh = 1;
        } else if (op == OP_DECORATE && wc == 4 && w[i + 2] == DEC_BUILTIN && w[i + 3] == BI_NUM_WORKGROUPS) {
            nwg_var = w[i + 1];
        } else if (op == OP_TYPE_BOOL && wc == 2) {
            t_bool = w[i + 1];
        } else if (op == OP_TYPE_INT && wc == 4 && w[i + 2] == 32 && w[i + 3] == 0) {
            t_u32 = w[i + 1];
        } else if (op == OP_TYPE_VECTOR && wc == 4 && t_u32 && w[i + 2] == t_u32 && w[i + 3] == 3) {
            t_v3u32 = w[i + 1];
        } else if (op == OP_CONSTANT && wc == 4 && t_u32 && w[i + 1] == t_u32 && w[i + 3] == 0) {
            c_u32_zero = w[i + 2];
        } else if (op == OP_FUNCTION && !first_func) {
            first_func = i;
        } else if (op == OP_SET_MESH_OUTPUTS_EXT && wc == 3 && !set_mesh_at) {
            set_mesh_at = i;
        }
        i += wc;
    }

    if (!is_mesh || !nwg_var || !t_u32 || !set_mesh_at || !first_func) return NULL;

    uint32_t nwg_ptr_ty = 0;
    for (uint64_t i = 5; i < first_func;) {
        uint32_t wc = w[i] >> 16, op = w[i] & 0xFFFFu;
        if (op == OP_VARIABLE && wc >= 4 && w[i + 2] == nwg_var && w[i + 3] == SC_INPUT) {
            nwg_ptr_ty = w[i + 1];
        } else if (op == OP_TYPE_VECTOR && wc == 4 && w[i + 2] == t_u32 && w[i + 3] == 3) {
            t_v3u32 = w[i + 1];
        }
        i += wc;
    }
    if (!nwg_ptr_ty || !t_v3u32) return NULL;

    int ptr_ok = 0;
    for (uint64_t i = 5; i < first_func;) {
        uint32_t wc = w[i] >> 16, op = w[i] & 0xFFFFu;
        if (op == OP_TYPE_POINTER && wc == 4 && w[i + 1] == nwg_ptr_ty && w[i + 2] == SC_INPUT && w[i + 3] == t_v3u32) {
            ptr_ok = 1;
            break;
        }
        i += wc;
    }
    if (!ptr_ok) return NULL;

    uint64_t pre_words = 0;
    uint32_t new_bool = 0, new_zero = 0;
    if (!t_bool) {
        new_bool = bound++;
        t_bool = new_bool;
        pre_words += 2;
    }
    if (!c_u32_zero) {
        new_zero = bound++;
        c_u32_zero = new_zero;
        pre_words += 4;
    }

    uint32_t id_load = bound++;
    uint32_t id_x = bound++;
    uint32_t id_nz = bound++;
    uint32_t id_sel = bound++;

    const uint64_t body_words = 20;
    uint64_t total = n + pre_words + body_words;
    uint32_t *o = (uint32_t *)malloc((size_t)(total * sizeof(uint32_t)));
    if (!o) return NULL;

    uint64_t p = 0;
    memcpy(o, w, (size_t)(first_func * sizeof(uint32_t)));
    p = first_func;
    o[3] = bound;

    if (new_bool) {
        o[p++] = (2u << 16) | OP_TYPE_BOOL;
        o[p++] = new_bool;
    }
    if (new_zero) {
        o[p++] = (4u << 16) | OP_CONSTANT;
        o[p++] = t_u32;
        o[p++] = new_zero;
        o[p++] = 0u;
    }

    memcpy(o + p, w + first_func, (size_t)((set_mesh_at - first_func) * sizeof(uint32_t)));
    p += (set_mesh_at - first_func);

    uint32_t max_v = w[set_mesh_at + 1];
    uint32_t orig_count = w[set_mesh_at + 2];

    o[p++] = (4u << 16) | OP_LOAD;
    o[p++] = t_v3u32;
    o[p++] = id_load;
    o[p++] = nwg_var;

    o[p++] = (5u << 16) | OP_COMPOSITE_EXTRACT;
    o[p++] = t_u32;
    o[p++] = id_x;
    o[p++] = id_load;
    o[p++] = 0u;

    o[p++] = (5u << 16) | OP_I_NOT_EQUAL;
    o[p++] = t_bool;
    o[p++] = id_nz;
    o[p++] = id_x;
    o[p++] = c_u32_zero;

    o[p++] = (6u << 16) | OP_SELECT;
    o[p++] = t_u32;
    o[p++] = id_sel;
    o[p++] = id_nz;
    o[p++] = orig_count;
    o[p++] = c_u32_zero;

    o[p++] = (3u << 16) | OP_SET_MESH_OUTPUTS_EXT;
    o[p++] = max_v;
    o[p++] = id_sel;

    memcpy(o + p, w + set_mesh_at + 3, (size_t)((n - (set_mesh_at + 3)) * sizeof(uint32_t)));
    p += (n - (set_mesh_at + 3));

    *out_n = p;
    return o;
}
