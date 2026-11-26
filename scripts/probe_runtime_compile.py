#!/usr/bin/env python3
"""Empirically cross-compile EVERY runtime file of totk-linux-native-recomp
for PS5 (x86_64-sie-ps5, -march=znver2) to map exact compile passes and failures.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOTK_ROOT = Path(os.environ.get("TOTK_UPSTREAM_SRC", str(Path(__file__).resolve().parent.parent.parent / "totk-linux-native-recomp")))
TOTK_RT = TOTK_ROOT / "runtime"
KIT_ROOT = PROJECT_ROOT / "third_party" / "ps5-kit"
GEN_DIR = PROJECT_ROOT / "build" / "gen"
PROBE_OBJ_DIR = PROJECT_ROOT / "build" / "probe_rt_obj"
VMA_SRC = Path(os.environ.get("VMA_HEADER", str(Path(__file__).resolve().parent.parent / "third_party" / "vma" / "vk_mem_alloc.h")))
VMA_DIR = PROJECT_ROOT / "third_party" / "vma"


def ensure_generated_headers() -> None:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    if not (GEN_DIR / "layout.h").is_file():
        sys.path.insert(0, str(TOTK_ROOT / "recomp"))
        import layout  # type: ignore

        mods = layout.layout(os.environ.get("TOTK_EXEFS", "./exefs"))
        layout.write(mods, str(GEN_DIR))

    patches_h = GEN_DIR / "patches.h"
    if not patches_h.is_file():
        patches_h.write_text(
            "#pragma once\n"
            "#define RT_PATCH_PAGE 0x7003b00000ull\n"
            "#define RT_PATCH_COUNT 0\n"
            "#define RT_PATCH_PICK_COUNT 0\n"
            "#define RT_PATCH_SETS(X)\n"
            "#define RT_PATCH_PICKS(X)\n"
            "#define RT_PLUGIN_COUNT 0\n"
            "#define RT_PLUGINS(X)\n"
            "#define RT_PLUGIN_WRITES(X)\n",
            encoding="utf-8",
        )

    romfs_cfg = GEN_DIR / "romfs_config.h"
    romfs_cfg.write_text(
        '#pragma once\n'
        '#define ROMFS_IMAGE_SHA256 "0000000000000000000000000000000000000000000000000000000000000000"\n'
        '#define ROMFS_INDEX_SHA256 "0000000000000000000000000000000000000000000000000000000000000000"\n'
        '#define ROMFS_FILE_COUNT 0\n'
        '#define ROMFS_IMAGE_SIZE 0ull\n',
        encoding="utf-8",
    )

    VMA_DIR.mkdir(parents=True, exist_ok=True)
    if not (VMA_DIR / "vk_mem_alloc.h").is_file() and VMA_SRC.is_file():
        shutil.copy2(VMA_SRC, VMA_DIR / "vk_mem_alloc.h")


def collect_sources() -> list[tuple[Path, str]]:
    """Return [(source_path, kind)] mirroring tools/build_game.py runtime_sources()."""
    pats = (
        ("*.c", "rt_c"),
        ("*.cpp", "rt_cpp"),
        ("platform/*.c", "plat"),
        ("ui/*.cpp", "ui"),
        ("third_party/imgui/*.cpp", "imgui"),
        ("third_party/imgui/backends/*.cpp", "imgui_backend"),
        ("third_party/FidelityFX/sdk/src/shared/*.cpp", "ffx"),
        ("third_party/FidelityFX/sdk/src/backends/vk/*.cpp", "ffx"),
        ("third_party/FidelityFX/sdk/src/components/*/*.cpp", "ffx"),
    )
    out: list[tuple[Path, str]] = []
    for pat, kind in pats:
        for p in sorted(TOTK_RT.glob(pat)):
            stem = p.stem
            if stem.endswith("_win") or p.name in ("win32.c", "totk.rc"):
                continue
            out.append((p, kind))
    return out


def prepare_ps5_override(src: Path, rel: Path) -> Path:
    """Create PS5-specific compile-time copies of menu.cpp / cfg.c inside build/ without touching upstream."""
    rel_posix = rel.as_posix()
    override_dir = PROJECT_ROOT / "build" / "ps5_rt_overrides"
    if rel_posix == "ui/menu.cpp":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '#include "ui/menu.h"',
                '#include "ui/menu.h"\n#include "trophies_ps5.h"',
            ),
            (
                'enum { TAB_SCREEN, TAB_GAME, TAB_SOUND, TAB_CONTROLS, TAB_AMIIBO, TAB_MENU, TAB_ADVANCED, TAB_MODS, TAB_CHEATS, TAB_COUNT };',
                'enum { TAB_SCREEN, TAB_GAME, TAB_SOUND, TAB_CONTROLS, TAB_AMIIBO, TAB_MENU, TAB_ADVANCED, TAB_MODS, TAB_CHEATS, TAB_TROPHIES, TAB_COUNT };',
            ),
            (
                'static const UiTextId kTabNames[TAB_COUNT] = {UI_MENU_TAB_SCREEN,   UI_MENU_TAB_GAME,   UI_MENU_TAB_SOUND,\n'
                '                                              UI_MENU_TAB_CONTROLS, UI_MENU_TAB_AMIIBO, UI_MENU_TAB_MENU,\n'
                '                                              UI_MENU_TAB_ADVANCED, UI_MENU_TAB_MODS,   UI_MENU_TAB_CHEATS};',
                'static const UiTextId kTabNames[TAB_COUNT] = {UI_MENU_TAB_SCREEN,   UI_MENU_TAB_GAME,   UI_MENU_TAB_SOUND,\n'
                '                                              UI_MENU_TAB_CONTROLS, UI_MENU_TAB_AMIIBO, UI_MENU_TAB_MENU,\n'
                '                                              UI_MENU_TAB_ADVANCED, UI_MENU_TAB_MODS,   UI_MENU_TAB_CHEATS, UI_MENU_TAB_CHEATS};\n'
                'static const char *ps5_tab_label(int k) { return k == TAB_TROPHIES ? "Trofeos" : menu_text(kTabNames[k]); }\n'
                'static ImVec4 ps5_trophy_color(Ps5TrophyTier tier, float a) {\n'
                '    switch (tier) {\n'
                '    case PS5_TROPHY_PLATINUM: return ImVec4(0.50f, 0.86f, 1.00f, a);\n'
                '    case PS5_TROPHY_GOLD:     return ImVec4(1.00f, 0.84f, 0.25f, a);\n'
                '    case PS5_TROPHY_SILVER:   return ImVec4(0.80f, 0.84f, 0.88f, a);\n'
                '    default:                  return ImVec4(0.84f, 0.54f, 0.30f, a);\n'
                '    }\n'
                '}\n'
                'static const char *ps5_trophy_tier_tag(Ps5TrophyTier tier) {\n'
                '    switch (tier) {\n'
                '    case PS5_TROPHY_PLATINUM: return "PLATINO";\n'
                '    case PS5_TROPHY_GOLD:     return "ORO";\n'
                '    case PS5_TROPHY_SILVER:   return "PLATA";\n'
                '    default:                  return "BRONCE";\n'
                '    }\n'
                '}\n'
                'static void tab_trophies(float scale) {\n'
                '    int total = ps5_trophies_count(), unlocked = 0, b = 0, s = 0, g = 0, p = 0;\n'
                '    ps5_trophies_summary(&unlocked, &b, &s, &g, &p);\n'
                '    float pct = total > 0 ? (float)unlocked / (float)total : 0.0f;\n'
                '    ImGui::TextColored(ImVec4(0.50f, 0.86f, 1.00f, 1.0f),\n'
                '                       "Trofeos PS5 (%s)  —  %d / %d (%.0f%%)",\n'
                '                       ps5_trophies_user_label(), unlocked, total, pct * 100.0f);\n'
                '    ImGui::TextDisabled("Platino: %d   |   Oro: %d   |   Plata: %d   |   Bronce: %d", p, g, s, b);\n'
                '    ImGui::ProgressBar(pct, ImVec2(-1.0f, 10.0f * scale), "");\n'
                '    ImGui::Spacing();\n'
                '    if (ImGui::BeginChild("##trophy_list", ImVec2(0, -48.0f * scale), false)) {\n'
                '        for (int i = 0; i < total; ++i) {\n'
                '            Ps5TrophyView tv;\n'
                '            if (!ps5_trophies_get(i, &tv)) continue;\n'
                '            ImVec4 col = tv.unlocked ? ps5_trophy_color(tv.tier, 1.0f) : ImVec4(0.50f, 0.53f, 0.56f, 0.85f);\n'
                '            ImGui::PushID(i);\n'
                '            ImGui::TextColored(col, "%s  [%s]  %s", tv.unlocked ? "[OK]" : "[  ]", ps5_trophy_tier_tag(tv.tier), tv.title);\n'
                '            if (tv.target > 1) {\n'
                '                ImGui::SameLine();\n'
                '                ImGui::TextDisabled("(%d / %d)", tv.cur > tv.target ? tv.target : tv.cur, tv.target);\n'
                '            }\n'
                '            ImGui::Indent(20.0f * scale);\n'
                '            ImGui::TextDisabled("%s", tv.desc);\n'
                '            ImGui::Unindent(20.0f * scale);\n'
                '            ImGui::Separator();\n'
                '            ImGui::PopID();\n'
                '        }\n'
                '    }\n'
                '    ImGui::EndChild();\n'
                '}\n'
                'static void ps5_trophies_draw_banner(uint32_t w, uint32_t h, float scale) {\n'
                '    Ps5TrophyView tv;\n'
                '    float alpha = 0.0f;\n'
                '    if (!ps5_trophies_current_banner(&tv, &alpha) || alpha <= 0.01f) return;\n'
                '    (void)h;\n'
                '    float bw = 460.0f * scale;\n'
                '    float pad = 24.0f * scale;\n'
                '    ImGui::SetNextWindowPos(ImVec2((float)w - bw - pad, pad), ImGuiCond_Always);\n'
                '    ImGui::SetNextWindowSize(ImVec2(bw, 0.0f), ImGuiCond_Always);\n'
                '    ImGui::SetNextWindowBgAlpha(0.88f * alpha);\n'
                '    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, 10.0f * scale);\n'
                '    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, 2.5f * scale);\n'
                '    ImGui::PushStyleColor(ImGuiCol_Border, ps5_trophy_color(tv.tier, alpha));\n'
                '    if (ImGui::Begin("##ps5_trophy_toast", nullptr,\n'
                '                     ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoInputs |\n'
                '                     ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoSavedSettings |\n'
                '                     ImGuiWindowFlags_AlwaysAutoResize)) {\n'
                '        ImGui::TextColored(ps5_trophy_color(tv.tier, alpha), "TROFEO %s DESBLOQUEADO", ps5_trophy_tier_tag(tv.tier));\n'
                '        ImGui::TextColored(ImVec4(1.0f, 1.0f, 1.0f, alpha), "%s", tv.title);\n'
                '        ImGui::TextColored(ImVec4(0.78f, 0.82f, 0.86f, alpha), "%s", tv.desc);\n'
                '    }\n'
                '    ImGui::End();\n'
                '    ImGui::PopStyleColor(1);\n'
                '    ImGui::PopStyleVar(2);\n'
                '}',
            ),
            (
                'snprintf(label, sizeof label, "  %s  ###tab%d", menu_text(kTabNames[k]), k);',
                'snprintf(label, sizeof label, "  %s  ###tab%d", ps5_tab_label(k), k);',
            ),
            (
                '            case TAB_ADVANCED: tab_advanced(scale); break;\n            }',
                '            case TAB_ADVANCED: tab_advanced(scale); break;\n            case TAB_TROPHIES: tab_trophies(scale); break;\n            }',
            ),
            (
                '        } else if (!g_perf_mode && !toast_live()) {',
                '        } else if (!g_perf_mode && !toast_live() && !ps5_trophies_toast_active()) {',
            ),
            (
                '    toast_draw(t, scale);\n    ImGui::Render();',
                '    toast_draw(t, scale);\n    ps5_trophies_draw_banner(t->width, t->height, scale);\n    ImGui::Render();',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 menu.cpp override failed: missing {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "fs_host.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '#include "host.h"',
                '#include "host.h"\nextern void ps5_trophies_scan_save(const char *save_root) __attribute__((weak));',
            ),
            (
                '    rt_log("host save storage: %s", save_root);\n    return;',
                '    rt_log("host save storage: %s", save_root);\n    if (ps5_trophies_scan_save) ps5_trophies_scan_save(save_root);\n    return;',
            ),
            (
                '    rt_log("fs commit save: %d files, %d changed (%.1f MiB written), %d unchanged linked, in %.0f ms%s", nfiles,\n'
                '           nfiles - linked, bytes / 1048576.0, linked, (plat_now_ns() - t0) / 1e6, waits ? "; waits in save-tx" : "");\n'
                '    return 0;',
                '    rt_log("fs commit save: %d files, %d changed (%.1f MiB written), %d unchanged linked, in %.0f ms%s", nfiles,\n'
                '           nfiles - linked, bytes / 1048576.0, linked, (plat_now_ns() - t0) / 1e6, waits ? "; waits in save-tx" : "");\n'
                '    if (ps5_trophies_scan_save) ps5_trophies_scan_save(save_root);\n'
                '    return 0;',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 fs_host.c override failed: missing {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "third_party/FidelityFX/sdk/src/backends/vk/ffx_vk.cpp":
        txt = src.read_text(encoding="utf-8")
        old_conv = (
            "void ConvertUTF8ToUTF16(const char* inputName, wchar_t* outputBuffer, size_t outputLen)\n"
            "{\n"
            "    memset(outputBuffer, 0, outputLen * sizeof(wchar_t));\n"
            "    std::wstring_convert<std::codecvt_utf8<wchar_t>, wchar_t> converter;\n"
            "    wcscpy_s(outputBuffer, outputLen, converter.from_bytes(inputName).c_str());\n"
            "}\n"
            "void ConvertUTF16ToUTF8(const wchar_t* inputName, char* outputBuffer, size_t outputLen)\n"
            "{\n"
            "    memset(outputBuffer, 0, outputLen * sizeof(char));\n"
            "    std::wstring_convert<std::codecvt_utf8<wchar_t>, wchar_t> converter;\n"
            "    strcpy_s(outputBuffer, outputLen, converter.to_bytes(inputName).c_str());\n"
            "}"
        )
        new_conv = (
            "/* PS5 fix: x86_64-sie-ps5 has 2-byte wchar_t, while ps5-kit libc++.a compiled\n"
            " * std::codecvt_utf8<wchar_t> with 4-byte ucs4_to_utf8/utf8_to_ucs4, which throws\n"
            " * std::range_error -> std::terminate() -> SIGABRT on UTF-16 input and corrupts\n"
            " * CreatePipelineVK binding names. Use simple exception-free 2-byte conversion. */\n"
            "void ConvertUTF8ToUTF16(const char* inputName, wchar_t* outputBuffer, size_t outputLen)\n"
            "{\n"
            "    if (!outputBuffer || outputLen == 0) return;\n"
            "    memset(outputBuffer, 0, outputLen * sizeof(wchar_t));\n"
            "    if (!inputName) return;\n"
            "    size_t i = 0;\n"
            "    for (; i + 1 < outputLen && inputName[i]; ++i)\n"
            "        outputBuffer[i] = (wchar_t)(unsigned char)inputName[i];\n"
            "    outputBuffer[i] = 0;\n"
            "}\n"
            "void ConvertUTF16ToUTF8(const wchar_t* inputName, char* outputBuffer, size_t outputLen)\n"
            "{\n"
            "    if (!outputBuffer || outputLen == 0) return;\n"
            "    memset(outputBuffer, 0, outputLen * sizeof(char));\n"
            "    if (!inputName) return;\n"
            "    size_t i = 0;\n"
            "    for (; i + 1 < outputLen && inputName[i]; ++i)\n"
            "        outputBuffer[i] = (inputName[i] < 0x80) ? (char)inputName[i] : '?';\n"
            "    outputBuffer[i] = 0;\n"
            "}"
        )
        if old_conv not in txt:
            raise RuntimeError("PS5 ffx_vk.cpp override failed: ConvertUTF8ToUTF16/ConvertUTF16ToUTF8 not found")
        txt = txt.replace(old_conv, new_conv, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "gfx_shader.c":
        txt = src.read_text(encoding="utf-8")
        old_tx = '    if (look && (s = disk_load(look, look_iid))) return plat_inc64(&n_hits), mem_insert(s);\n\n    uint64_t skip = stage == GFX_STAGE_CS ? 0 : CODE_SKIP;'
        new_tx = (
            '    if (look && (s = disk_load(look, look_iid))) return plat_inc64(&n_hits), mem_insert(s);\n'
            '    /* PS5 port: no runtime totk_xlate binary exists on console. Avoid writing/deleting\n'
            '     * temp .code files and spamming rt_log on rare cache misses (e.g. unseen mvprev variants). */\n'
            '    if (!xlate_exe[0]) {\n'
            '        static volatile int32_t ps5_no_xlate_log;\n'
            '        if (plat_inc32(&ps5_no_xlate_log) <= 5)\n'
            '            rt_log("gfx_shader: PS5 cache miss (no runtime translator); suppressing further miss logs");\n'
            '        return NULL;\n'
            '    }\n\n'
            '    uint64_t skip = stage == GFX_STAGE_CS ? 0 : CODE_SKIP;'
        )
        if old_tx not in txt:
            raise RuntimeError("PS5 gfx_shader.c override failed: translate_one anchor not found")
        txt = txt.replace(old_tx, new_tx, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "gfx_present.c":
        txt = src.read_text(encoding="utf-8")
        old_sc = (
            '    vk_queue_lock();\n'
            '    vkDeviceWaitIdle(c->device);\n'
            '    VkSwapchainKHR old = g_sc;\n'
            '    VkSwapchainLatencyCreateInfoNV sci = {\n'
            '        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_LATENCY_CREATE_INFO_NV,\n'
            '        .latencyModeEnable = VK_TRUE\n'
            '    };\n'
            '    VkSwapchainCreateInfoKHR ci = {\n'
            '        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,\n'
            '        .pNext = (c->has_nv_reflex) ? &sci : NULL,\n'
            '        .surface = g_surface, .minImageCount = count,\n'
            '        .imageFormat = sf.format, .imageColorSpace = sf.colorSpace, .imageExtent = ext, .imageArrayLayers = 1,\n'
            '        .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |\n'
            '                      VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,   // every surface supports it (the menu overlay draws into it)\n'
            '        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE, .preTransform = caps.currentTransform,\n'
            '        .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, .presentMode = pick_present_mode(c->phys), .clipped = VK_TRUE,\n'
            '        .oldSwapchain = old};\n'
            '    VkResult r = vkCreateSwapchainKHR(c->device, &ci, NULL, &g_sc);\n'
            '    if (r != VK_SUCCESS) {\n'
            '        rt_log("gfx: vkCreateSwapchainKHR failed (%d)", (int)r);\n'
            '        g_sc = old;\n'
            '        vk_queue_unlock();\n'
            '        return 0;\n'
            '    }\n'
            '    for (uint32_t i = 0; i < g_sc_n; i++) {\n'
            '        vkDestroySemaphore(c->device, g_render_done[i], NULL);\n'
            '        if (g_sc_view[i]) vkDestroyImageView(c->device, g_sc_view[i], NULL);\n'
            '        g_sc_view[i] = VK_NULL_HANDLE;\n'
            '    }\n'
            '    if (old) vkDestroySwapchainKHR(c->device, old, NULL);'
        )
        new_sc = (
            '    vk_queue_lock();\n'
            '    vkDeviceWaitIdle(c->device);\n'
            '    for (uint32_t i = 0; i < g_sc_n; i++) {\n'
            '        vkDestroySemaphore(c->device, g_render_done[i], NULL);\n'
            '        if (g_sc_view[i]) vkDestroyImageView(c->device, g_sc_view[i], NULL);\n'
            '        g_sc_view[i] = VK_NULL_HANDLE;\n'
            '    }\n'
            '    g_sc_n = 0;\n'
            '    VkSwapchainKHR old = g_sc;\n'
            '    if (old) {\n'
            '        vkDestroySwapchainKHR(c->device, old, NULL);\n'
            '        g_sc = VK_NULL_HANDLE;\n'
            '    }\n'
            '    VkSwapchainLatencyCreateInfoNV sci = {\n'
            '        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_LATENCY_CREATE_INFO_NV,\n'
            '        .latencyModeEnable = VK_TRUE\n'
            '    };\n'
            '    VkSwapchainCreateInfoKHR ci = {\n'
            '        .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,\n'
            '        .pNext = (c->has_nv_reflex) ? &sci : NULL,\n'
            '        .surface = g_surface, .minImageCount = count,\n'
            '        .imageFormat = sf.format, .imageColorSpace = sf.colorSpace, .imageExtent = ext, .imageArrayLayers = 1,\n'
            '        .imageUsage = VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |\n'
            '                      VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,   // every surface supports it (the menu overlay draws into it)\n'
            '        .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE, .preTransform = caps.currentTransform,\n'
            '        .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR, .presentMode = pick_present_mode(c->phys), .clipped = VK_TRUE,\n'
            '        .oldSwapchain = VK_NULL_HANDLE};\n'
            '    VkResult r = vkCreateSwapchainKHR(c->device, &ci, NULL, &g_sc);\n'
            '    if (r != VK_SUCCESS) {\n'
            '        rt_log("gfx: vkCreateSwapchainKHR failed (%d)", (int)r);\n'
            '        g_sc = VK_NULL_HANDLE;\n'
            '        vk_queue_unlock();\n'
            '        return 0;\n'
            '    }'
        )
        if old_sc not in txt:
            raise RuntimeError("PS5 gfx_present.c override failed: build_swapchain block not found")
        txt = txt.replace(old_sc, new_sc, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_fg.cpp":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '    void *p = aligned_alloc(256, n);',
                '    void *p = nullptr;\n    if (posix_memalign(&p, 256, n) != 0) p = nullptr;',
            ),
            (
                '    g.sync_ahead = cfg_bool("TOTK_SYNC_AHEAD") && strcmp(cfg_value("TOTK_SYNC_AHEAD"), "check") != 0;   // check: exact',
                '    g.sync_ahead = 0; /* PS5: nvnSyncWait yields sync_ahead dynamically while vk_fg_engine() != VK_FG_OFF */',
            ),
            (
                '        vk_present_drain();\n        vk_queue_lock();',
                '        vk_present_drain();\n        rec_drain();\n        vk_queue_lock();',
            ),
            (
                '        VkCtx *c = vk_ctx();\n'
                '        vk_queue_lock();\n'
                '        vkDeviceWaitIdle(c->device);\n'
                '        vk_queue_unlock();\n'
                '        sdk_destroy();',
                '        VkCtx *c = vk_ctx();\n'
                '        if (g.live) vk_present_drain();\n'
                '        rec_drain();\n'
                '        vk_queue_lock();\n'
                '        vkDeviceWaitIdle(c->device);\n'
                '        vk_queue_unlock();\n'
                '        g.show_out = g.show_hl = g.show_win = VK_NULL_HANDLE;\n'
                '        sdk_destroy();',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 vk_fg.cpp override failed: missing {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "nvn_api_core.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                'NVN_API(nvnSyncWait) {',
                'extern int vk_fg_engine(void) __attribute__((weak));\n\nNVN_API(nvnSyncWait) {',
            ),
            (
                '    int mode = timeout && c->x[30] == frame_wait_lr() ? sync_mode() : 0, behind = b->fence_done() < want;',
                '    int mode = ((!vk_fg_engine || vk_fg_engine() == 0) && timeout && c->x[30] == frame_wait_lr()) ? sync_mode() : 0, behind = b->fence_done() < want;',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 nvn_api_core.c override failed: missing {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_fsr3.cpp":
        txt = src.read_text(encoding="utf-8")
        old_alloc = '    void *p = aligned_alloc(256, n);'
        new_alloc = '    void *p = nullptr;\n    if (posix_memalign(&p, 256, n) != 0) p = nullptr;'
        if old_alloc not in txt:
            raise RuntimeError("PS5 vk_fsr3.cpp override failed: aligned_alloc not found")
        txt = txt.replace(old_alloc, new_alloc, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_astc.c":
        txt = src.read_text(encoding="utf-8")
        old_inc = '#include "astc_decode_spv.h"'
        new_inc = '#include "ps5_astc_decode_spv.h"'
        if old_inc not in txt:
            raise RuntimeError("PS5 vk_astc.c override failed: astc_decode_spv.h include not found")
        txt = txt.replace(old_inc, new_inc, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_pipeline.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '#include "tex.h"',
                '#include "tex.h"\n#include "prepare_threads.h"\n#include "spirv_radv_mesh_nwg.h"',
            ),
            (
                '    uint64_t demoted_n = 0;\n'
                '    uint32_t *demoted = spirv_demote(w, words, &demoted_n);\n'
                '    if (demoted) free(fixed), fixed = demoted, w = demoted, words = demoted_n;',
                '    uint64_t demoted_n = 0;\n'
                '    uint32_t *demoted = spirv_demote(w, words, &demoted_n);\n'
                '    if (demoted) free(fixed), fixed = demoted, w = demoted, words = demoted_n;\n'
                '    /* RADV < 26.2.5 MeshEXT NumWorkgroups liveness guard (PS5 ships Mesa RADV 26.2.0; Longshot #2338). */\n'
                '    if (vk_caps.mesa && vk_caps.amd) {\n'
                '        VkCtx *vc = vk_ctx();\n'
                '        if (vc && vc->props.driverVersion < VK_MAKE_VERSION(26, 2, 5)) {\n'
                '            uint64_t nwg_n = 0;\n'
                '            uint32_t *nwg = spirv_radv_keep_num_workgroups(w, words, &nwg_n);\n'
                '            if (nwg) free(fixed), fixed = nwg, w = nwg, words = nwg_n;\n'
                '        }\n'
                '    }',
            ),
            (
                '    int cpus = (int)plat_cpu_usable(), k = 0;',
                '    const char *pt_env = cfg_get("TOTK_PREPARE_THREADS");\n'
                '    if (!pt_env || !*pt_env) pt_env = cfg_get("PS5_PREPARE_THREADS");\n'
                '    int cpus = ps5_prepare_threads((int)plat_cpu_usable(), pt_env && *pt_env ? atoi(pt_env) : 0), k = 0;',
            ),
            (
                '    int cpus = (int)plat_cpu_usable();\n'
                '    const char *pe = cfg_get("TOTK_PREWARM_XLATE");',
                '    const char *pt_env = cfg_get("TOTK_PREPARE_THREADS");\n'
                '    if (!pt_env || !*pt_env) pt_env = cfg_get("PS5_PREPARE_THREADS");\n'
                '    int cpus = ps5_prepare_threads((int)plat_cpu_usable(), pt_env && *pt_env ? atoi(pt_env) : 0);\n'
                '    const char *pe = cfg_get("TOTK_PREWARM_XLATE");',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 vk_pipeline.c override failed: missing anchor {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "ov_movie.c":
        txt = src.read_text(encoding="utf-8")
        old_gcount = "static volatile int32_t g_count;                // live host decoders: movie_tick returns at once when 0"
        new_gcount = (
            "static volatile int32_t g_count;                // live host decoders: movie_tick returns at once when 0\n"
            "int ps5_movie_active(void) { return __atomic_load_n(&g_count, __ATOMIC_RELAXED) > 0; }"
        )
        if old_gcount not in txt:
            raise RuntimeError("PS5 ov_movie.c override failed: g_count anchor not found")
        txt = txt.replace(old_gcount, new_gcount, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_texture.c":
        txt = src.read_text(encoding="utf-8")
        old_samp = (
            "        s->sp = sampler_for(c, &k);\n"
            "    }\n"
            "    return s->sp;\n"
            "}"
        )
        new_samp = (
            "        s->sp = sampler_for(c, &k);\n"
            "    }\n"
            "    return s->sp;\n"
            "}\n"
            "\n"
            "VkSampler vk_sampler_movie_linear_locked(int id) {\n"
            "    VkCtx *c = vk_ctx();\n"
            "    if (!c) return VK_NULL_HANDLE;\n"
            "    samp_par k;\n"
            "    memset(&k, 0, sizeof k);\n"
            "    if (id >= 0 && id < nsslots && sslots[id].used) k = sslots[id].p;\n"
            "    else k.ws = k.wt = k.wr = NVN_WRAP_MODE_CLAMP_TO_EDGE;\n"
            "    k.magf = NVN_MAG_FILTER_LINEAR;\n"
            "    k.minf = NVN_MIN_FILTER_LINEAR;\n"
            "    k.aniso = 1;\n"
            "    k.ws = NVN_WRAP_MODE_CLAMP_TO_EDGE;\n"
            "    k.wt = NVN_WRAP_MODE_CLAMP_TO_EDGE;\n"
            "    return sampler_for(c, &k);\n"
            "}"
        )
        if old_samp not in txt:
            raise RuntimeError("PS5 vk_texture.c override failed: vk_sampler_point_by_id_locked anchor not found")
        txt = txt.replace(old_samp, new_samp, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_exec_draw.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                "static void tex_info_full(VkExec *ex, const GfxShaderRes *r, uint64_t h, int storage, int separate,",
                "extern int ps5_movie_active(void) __attribute__((weak));\n"
                "extern VkSampler vk_sampler_movie_linear_locked(int id);\n"
                "static void tex_info_full(VkExec *ex, const GfxShaderRes *r, uint64_t h, int storage, int separate,",
            ),
            (
                "            samp = point ? vk_sampler_point_by_id_locked(sid) : vk_sampler_by_id_locked(sid);",
                "            int movie_plane = !point && ps5_movie_active && ps5_movie_active() && img && img->levels == 1 && img->layers == 1 &&\n"
                "                              ((img->format == VK_FORMAT_R8_UNORM && img->width == 1920 && img->height == 1080) ||\n"
                "                               (img->format == VK_FORMAT_R8G8_UNORM && img->width == 960 && img->height == 540));\n"
                "            samp = point ? vk_sampler_point_by_id_locked(sid)\n"
                "                 : movie_plane ? vk_sampler_movie_linear_locked(sid)\n"
                "                 : vk_sampler_by_id_locked(sid);",
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 vk_exec_draw.c override failed: missing {old[:60]!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "cfg.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '    "ZSTD_CHECK", "ZSTD_NATIVE",',
                '    "PS5_CCX", "PS5_DISPLAY", "PS5_HZ", "PS5_PREPARE_THREADS", "PS5_WATCHDOG", "ZERO_LOCALS", "ZSTD_CHECK", "ZSTD_NATIVE",',
            ),
            (
                '{"PAD_LAYOUT", "auto", "auto|nintendo|xbox", LIVE}',
                '{"PAD_LAYOUT", "nintendo", "auto|nintendo|xbox", LIVE}',
            ),
            (
                '{"PROMPTS", "nintendo", "nintendo|xbox|playstation|pc", RESTART}',
                '{"PROMPTS", "playstation", "nintendo|xbox|playstation|pc", RESTART}',
            ),
            (
                '{"ASYNC_PREEMPT", "1", "0|1|2", RESTART}, {"REPLAY_ASYNC", "0", "0|1", RESTART},',
                '{"ASYNC_PREEMPT", "2", "0|1|2", RESTART}, {"REPLAY_ASYNC", "1", "0|1", RESTART},',
            ),
            (
                '{"SYNC_AHEAD", "0", "0|1|check", RESTART},',
                '{"SYNC_AHEAD", "1", "0|1|check", RESTART},',
            ),
            (
                '{"BIND_INC", "0", "0|1|check", RESTART},',
                '{"BIND_INC", "1", "0|1|check", RESTART},',
            ),
            (
                '{"WINDOW_SIZE", "1920x1080", NULL, LIVE}',
                '{"WINDOW_SIZE", "2560x1440", NULL, LIVE}',
            ),
            (
                '{"OUTPUT_RES", "1920x1080", NULL, RESTART}, {"RENDER_SCALE", "game", "game|50|67|75|100|125|150|200", RESTART},',
                '{"OUTPUT_RES", "2560x1440", NULL, RESTART}, {"RENDER_SCALE", "75", "game|50|67|75|100|125|150|200", RESTART},',
            ),
            (
                '{"DYNAMIC_RES", "1", "0|1", LIVE},',
                '{"DYNAMIC_RES", "0", "0|1", LIVE},',
            ),
            (
                '{"UPSCALER", "fsr", "fsr|bilinear", LIVE}, {"SHARPNESS", "80", "0..100", LIVE},',
                '{"UPSCALER", "fsr", "fsr|bilinear", LIVE}, {"SHARPNESS", "35", "0..100", LIVE},',
            ),
            (
                '{"ANISO", "game", "game|2|4|8|16", RESTART},',
                '{"ANISO", "8", "game|2|4|8|16", RESTART},',
            ),
            (
                '{"FRAME_GEN", "off", "off|fsr3", LIVE},',
                '{"FRAME_GEN", "fsr3", "off|fsr3", LIVE},',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 cfg.c override failed: missing {old}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    return src


def compile_one(
    src: Path, kind: str, clang: str, base_flags: list[str], inc_flags: list[str]
) -> dict:
    rel = src.relative_to(TOTK_RT)
    actual_src = prepare_ps5_override(src, rel)
    obj = PROBE_OBJ_DIR / rel.with_suffix(".o")
    obj.parent.mkdir(parents=True, exist_ok=True)

    cmd = [clang, *base_flags, *inc_flags]
    if src.suffix == ".cpp":
        cmd += ["-std=c++20"]
    if kind == "ffx" or src.name in ("vk_fg.cpp", "vk_fsr3.cpp"):
        ffx = TOTK_RT / "third_party" / "FidelityFX"
        cmd += [
            "-include",
            "ffx_compat.h",
            "-I",
            str(ffx),
            "-I",
            str(ffx / "sdk" / "src" / "shared"),
            "-w",
        ]
    else:
        cmd += ["-Wno-unused-function", "-Wno-unused-variable"]

    if actual_src != src:
        cmd += ["-I", str(src.parent), "-I", str(PROJECT_ROOT / "ps5"), f"--embed-dir={src.parent}"]
    cmd += ["-c", str(actual_src), "-o", str(obj)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    def sanitize(s: str) -> str:
        return s.replace(str(TOTK_ROOT), "<TOTK_UPSTREAM_SRC>").replace(
            str(PROJECT_ROOT), "<PS5_PROJECT_ROOT>"
        )

    first_errors = []
    if res.returncode != 0:
        for line in res.stderr.splitlines():
            if "error:" in line or "fatal error:" in line:
                first_errors.append(sanitize(line.strip()))
                if len(first_errors) >= 3:
                    break
        if not first_errors:
            first_errors = [sanitize(line) for line in res.stderr.strip().splitlines()[-3:]]

    return {
        "file": rel.as_posix(),
        "kind": kind,
        "ok": res.returncode == 0,
        "errors": first_errors,
    }


def main() -> int:
    ensure_generated_headers()
    PROBE_OBJ_DIR.mkdir(parents=True, exist_ok=True)

    kit = KIT_ROOT / "kit"
    clang = str(KIT_ROOT / "tools" / "bin" / "clang")
    info = json.loads((kit / "kit.json").read_text())
    place = lambda s: s.replace("{kit}", str(kit))

    base_flags = [place(f) for f in info["target_flags"]] + [
        "-march=znver2",
        "-O3",
        "-DNDEBUG",
        "-mcx16",
        "-fno-omit-frame-pointer",
        "-fno-strict-aliasing",
        "-DRT_CPU_LEVEL=3",
        # PS5 SIE target rejects preserve_most even though clang __has_attribute(preserve_most)==1
        "-Dpreserve_most=noinline",
        # Avoid symbol collision with Mesa RADV's internal src/vulkan/runtime/vk_sync.c:vk_sync_finish
        "-Dvk_sync_finish=totk_vk_sync_finish",
        "-ffunction-sections",
        "-fdata-sections",
    ]

    ffx = TOTK_RT / "third_party" / "FidelityFX"
    inc_flags = [
        "-I",
        str(PROJECT_ROOT / "third_party" / "ps5_compat_inc"),
        "-I",
        str(TOTK_RT),
        "-I",
        str(GEN_DIR),
        "-I",
        str(VMA_DIR),
        "-I",
        str(TOTK_RT / "third_party" / "imgui"),
        "-I",
        str(ffx / "sdk" / "include"),
        "-I",
        str(ffx / "sdk" / "src" / "backends" / "shared"),
        "-I",
        str(ffx / "spirv"),
        # Provide Vulkan headers (types) cleanly via host /usr/include/vulkan ONLY via wrapper dir?
        # Let's expose ONLY vulkan/ and vk_video/ in a clean shim include dir so Linux glibc headers never leak!
    ]

    # Create a clean Vulkan-only header dir (symlinks to /usr/include/vulkan & /usr/include/vk_video)
    vk_inc = PROJECT_ROOT / "third_party" / "vk_headers"
    vk_inc.mkdir(parents=True, exist_ok=True)
    for sub in ("vulkan", "vk_video"):
        dst = vk_inc / sub
        src_hdr = Path("/usr/include") / sub
        if src_hdr.exists() and not dst.exists():
            dst.symlink_to(src_hdr)
    # Also symlink zstd.h from system (we link against kit/lib/libzstd.a!)
    for hdr in ("zstd.h", "zstd_errors.h"):
        src_hdr = Path("/usr/include") / hdr
        dst = vk_inc / hdr
        if src_hdr.exists() and not dst.exists():
            dst.symlink_to(src_hdr)
    # Also symlink opus headers if installed on host (we link against kit/obj/opus_*.o!)
    if Path("/usr/include/opus").is_dir() and not (vk_inc / "opus").exists():
        (vk_inc / "opus").symlink_to(Path("/usr/include/opus"))

    inc_flags += ["-isystem", str(vk_inc)]

    sources = collect_sources()
    print(f"[probe] Cross-compiling {len(sources)} TOTK runtime files for x86_64-sie-ps5...")

    results = []
    workers = min(12, os.cpu_count() or 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [
            ex.submit(compile_one, src, kind, clang, base_flags, inc_flags)
            for src, kind in sources
        ]
        for fut in concurrent.futures.as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: r["file"])
    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]

    report_json = PROJECT_ROOT / "docs" / "compile_probe_ps5.json"
    report_json.write_text(
        json.dumps(
            {
                "total": len(results),
                "passed": len(passed),
                "failed": len(failed),
                "results": results,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"\n=== PS5 CROSS-COMPILE PROBE RESULT: {len(passed)}/{len(results)} PASSED, {len(failed)} FAILED ===\n")
    for r in failed:
        print(f"FAIL [{r['kind']}] {r['file']}")
        for e in r["errors"]:
            print(f"     {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
