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
        old = (
            '    static const UiTextId frame_gen[] = {UI_MENU_FRAME_GEN_OFF, UI_MENU_FRAME_GEN_FSR3};\n'
            '    opt_choice("TOTK_FRAME_GEN", UI_MENU_FRAME_GEN, frame_gen, 2, UI_MENU_FRAME_GEN_DESC);'
        )
        new = (
            '    /* PS5 port: FSR 3.1.5 Frame Generation is unsupported on PS5 and disabled to prevent crashes. */\n'
            '    (void)0;'
        )
        if old not in txt:
            raise RuntimeError("PS5 menu.cpp override failed: TOTK_FRAME_GEN block not found")
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt.replace(old, new, 1), encoding="utf-8")
        return dst
    if rel_posix == "vk_fg.cpp":
        txt = src.read_text(encoding="utf-8")
        old = 'extern "C" VkFgEngine vk_fg_engine(void) {'
        new = 'extern "C" VkFgEngine vk_fg_engine(void) {\n    return VK_FG_OFF; /* PS5 port: FSR 3.1.5 Frame Generation disabled */'
        if old not in txt:
            raise RuntimeError("PS5 vk_fg.cpp override failed: vk_fg_engine not found")
        dst = override_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(txt.replace(old, new, 1), encoding="utf-8")
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
    if kind == "ffx":
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
        cmd += ["-I", str(src.parent), f"--embed-dir={src.parent}"]
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
