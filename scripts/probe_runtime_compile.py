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
TOTK_ROOT = Path("/home/saul/Projects/totk-linux-native-recomp")
TOTK_RT = TOTK_ROOT / "runtime"
KIT_ROOT = PROJECT_ROOT / "third_party" / "ps5-kit"
GEN_DIR = PROJECT_ROOT / "build" / "gen"
PROBE_OBJ_DIR = PROJECT_ROOT / "build" / "probe_rt_obj"
VMA_SRC = Path("/home/saul/Projects/oot-linux-native-recomp/third_party/vma/vk_mem_alloc.h")
VMA_DIR = PROJECT_ROOT / "third_party" / "vma"


def ensure_generated_headers() -> None:
    GEN_DIR.mkdir(parents=True, exist_ok=True)
    if not (GEN_DIR / "layout.h").is_file():
        sys.path.insert(0, str(TOTK_ROOT / "recomp"))
        import layout  # type: ignore

        mods = layout.layout("/home/saul/Games/Hyrule/TOTK/ROM/exefs")
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
                '    static const UiTextId frame_gen[] = {UI_MENU_FRAME_GEN_OFF, UI_MENU_FRAME_GEN_FSR3};\n'
                '    opt_choice("TOTK_FRAME_GEN", UI_MENU_FRAME_GEN, frame_gen, 2, UI_MENU_FRAME_GEN_DESC);',
                '    /* PS5 port: FSR 3.1.5 Frame Generation is unsupported on PS5 and disabled to prevent crashes. */\n'
                '    (void)0;',
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
    if rel_posix == "vk_fg.cpp":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '#include <string.h>',
                '#include <string.h>\n#include <sys/stat.h>',
            ),
            (
                '    return nullptr;\n}',
                '    rt_log("fg-dbg: device_proc(%s) -> NULL", name);\n    return nullptr;\n}',
            ),
            (
                '    void *p = aligned_alloc(256, n);',
                '    void *p = nullptr;\n    if (posix_memalign(&p, 256, n) != 0) p = nullptr;',
            ),
            (
                'extern "C" VkFgEngine vk_fg_engine(void) {',
                'extern "C" VkFgEngine vk_fg_engine(void) {\n'
                '    static int ps5_fg_gate = -1;\n'
                '    if (ps5_fg_gate < 0) { struct stat st_; ps5_fg_gate = (stat("/data/totk-ps5/enable_fg_test", &st_) == 0) ? 1 : 0; }\n'
                '    if (!ps5_fg_gate) return VK_FG_OFF;',
            ),
            (
                'extern "C" int vk_fg_prepare(VkCommandBuffer cb, const VkFgScene *s) {\n    g.prepared = false;',
                'extern "C" int vk_fg_prepare(VkCommandBuffer cb, const VkFgScene *s) {\n'
                '    static int dbg_ent; if (!dbg_ent++) rt_log("fg-dbg: enter vk_fg_prepare w=%u h=%u ow=%u oh=%u live=%d cfg=(%u,%u,%u,%u,%d,%u,%u) inv=%d inf=%d", s->w, s->h, s->ow, s->oh, (int)g.live, g.cfg.display_w, g.cfg.display_h, g.cfg.render_w, g.cfg.render_h, (int)g.cfg.color_format, g.cfg.inverted, g.cfg.infinite, s->inverted, s->infinite);\n'
                '    g.prepared = false;',
            ),
            (
                '    rec_drain();   // the SDK records into cb itself: the recorder must have made every call queued before',
                '    static int dbg_rd; if (!dbg_rd) rt_log("fg-dbg: before rec_drain");\n'
                '    rec_drain();   // the SDK records into cb itself: the recorder must have made every call queued before\n'
                '    if (!dbg_rd++) rt_log("fg-dbg: after rec_drain");',
            ),
            (
                '    FfxErrorCode e = ffxFrameInterpolationPrepare(&g.fi, &pd);',
                '    static int dbg_p; if (!dbg_p) rt_log("fg-dbg: enter ffxFrameInterpolationPrepare cb=%p", (void*)cb);\n'
                '    FfxErrorCode e = ffxFrameInterpolationPrepare(&g.fi, &pd);\n'
                '    if (!dbg_p++) rt_log("fg-dbg: exit ffxFrameInterpolationPrepare e=%d", (int)e);',
            ),
            (
                '    g.hl_ok = true;\n    return 1;',
                '    static int dbg_h; if (!dbg_h++) rt_log("fg-dbg: vk_fg_hudless OK %ux%u", w, h);\n'
                '    g.hl_ok = true;\n    return 1;',
            ),
            (
                '    FfxErrorCode e = ffxOpticalflowContextDispatch(&g.of, &od);',
                '    static int dbg_g; if (!dbg_g) rt_log("fg-dbg: enter ffxOpticalflowContextDispatch");\n'
                '    FfxErrorCode e = ffxOpticalflowContextDispatch(&g.of, &od);\n'
                '    if (!dbg_g) rt_log("fg-dbg: exit opticalflow e=%d, enter interpolation", (int)e);',
            ),
            (
                '        e = ffxFrameInterpolationDispatch(&g.fi, &dd);',
                '        e = ffxFrameInterpolationDispatch(&g.fi, &dd);\n'
                '        if (!dbg_g++) rt_log("fg-dbg: exit interpolation e=%d", (int)e);',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 vk_fg.cpp override failed: missing {old!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "vk_dlaa.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '    int masked = 0, have = cam && mv_pass(ex, e, zv, 0.0f, 0.0f, 0.0f, &masked, fg_objects());',
                '    static int dbg_fgm; if (!dbg_fgm) rt_log("fg-dbg: fg_motion before mv_pass cam=%p objects=%d", (const void*)cam, fg_objects());\n'
                '    int masked = 0, have = cam && mv_pass(ex, e, zv, 0.0f, 0.0f, 0.0f, &masked, fg_objects());\n'
                '    if (!dbg_fgm) rt_log("fg-dbg: fg_motion after mv_pass have=%d", have);',
            ),
            (
                '    D.fg_mv_ok = vk_fg_prepare(cb, &s);',
                '    if (!dbg_fgm++) rt_log("fg-dbg: fg_motion calling vk_fg_prepare");\n'
                '    D.fg_mv_ok = vk_fg_prepare(cb, &s);',
            ),
        ]
        for old, new in repls:
            if old not in txt:
                raise RuntimeError(f"PS5 vk_dlaa.c override failed: missing {old!r}")
            txt = txt.replace(old, new, 1)
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt, encoding="utf-8")
        return dst
    if rel_posix == "cfg.c":
        txt = src.read_text(encoding="utf-8")
        repls = [
            (
                '{"PAD_LAYOUT", "auto", "auto|nintendo|xbox", LIVE}',
                '{"PAD_LAYOUT", "nintendo", "auto|nintendo|xbox", LIVE}',
            ),
            (
                '{"PROMPTS", "nintendo", "nintendo|xbox|playstation|pc", RESTART}',
                '{"PROMPTS", "playstation", "nintendo|xbox|playstation|pc", RESTART}',
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
    first_errors = []
    if res.returncode != 0:
        for line in res.stderr.splitlines():
            if "error:" in line or "fatal error:" in line:
                first_errors.append(line.strip())
                if len(first_errors) >= 3:
                    break
        if not first_errors:
            first_errors = res.stderr.strip().splitlines()[-3:]

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
        "-O2",
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
