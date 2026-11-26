#!/usr/bin/env python3
"""Compile our PS5 platform/SDL3/VPX backends and link ALL 131 compiled
totk-linux-native-recomp runtime objects into a signed PS5 FSELF
(out/PPSA99199/totk_rt_probe.bin) to uncover every real link/import gap.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOTK_RT = Path("/home/saul/Projects/totk-linux-native-recomp/runtime")
KIT_ROOT = PROJECT_ROOT / "third_party" / "ps5-kit"
GEN_DIR = PROJECT_ROOT / "build" / "gen"
RT_OBJ_DIR = PROJECT_ROOT / "build" / "probe_rt_obj"
LINK_DIR = PROJECT_ROOT / "build" / "link_rt"
OUT_DIR = PROJECT_ROOT / "out" / "PPSA99199"

# Linux/SDL desktop adapter files replaced by ps5/*
SKIP_RT_FILES = {
    "platform/linux.c",
    "gfx_window_sdl.c",
    "folder_pick_sdl.c",
    "input_sdl.c",
    "ui/menu_sdl.cpp",
}

PS5_SOURCES = [
    "ps5/plat_ps5_mem.c",
    "ps5/platform_ps5.c",
    "ps5/gfx_window_ps5.c",
    "ps5/sdl3_ps5.c",
    "ps5/vpx_ps5.c",
    "ps5/trophies_ps5.c",
    "ps5/folder_pick_ps5.c",
    "ps5/input_host_ps5.c",
    "ps5/vk_ps5_trampolines.c",
]


def run(cmd: list[str], what: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    print(f"[link-rt] {what}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"ERROR during {what} (rc={res.returncode}):", file=sys.stderr)
        if res.stdout:
            print(res.stdout[-3500:], file=sys.stderr)
        if res.stderr:
            print(res.stderr[-3500:], file=sys.stderr)
        raise SystemExit(res.returncode)
    return res


def write_rsp(path: Path, args: list[str]) -> str:
    path.write_text(
        "".join('"' + a.replace("\\", "/").replace('"', '\\"') + '"\n' for a in args),
        encoding="utf-8",
    )
    return f"@{path}"


def generate_stub_modules_c() -> Path:
    """Minimal modules.c matching build_game.py module_glue() for link testing."""
    path = LINK_DIR / "modules_stub.c"
    path.write_text(
        '#include "dispatch.h"\n'
        '#include "host.h"\n'
        '#include "layout.h"\n\n'
        "const RtLayoutEntry rt_layout[] = {\n"
        '    {"main", MOD_MAIN_BASE, MOD_MAIN_SIZE},\n'
        '    {"subsdk0", MOD_SUBSDK0_BASE, MOD_SUBSDK0_SIZE},\n'
        '    {"sdk", MOD_SDK_BASE, MOD_SDK_SIZE},\n'
        "};\n"
        "const int rt_layout_count = 3;\n"
        "int rt_linked_modules(RtModule *out, int max) { (void)out; (void)max; return 0; }\n"
        "const RtFileHash rt_exefs_sha256[] = { {0, 0} };\n"
        "const int rt_exefs_sha256_count = 0;\n"
        'const char rt_default_exefs[] = "/data/totk-ps5/exefs";\n'
        'const char rt_default_romfs[] = "/data/totk-ps5/romfs";\n'
        'const char rt_default_profile[] = "/data/totk-ps5/saves";\n'
        "const int rt_game_version = 121;\n"
        'const char rt_port_version[] = "0.1.0-ps5-phase1";\n',
        encoding="utf-8",
    )
    return path


def main() -> int:
    LINK_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    kit = KIT_ROOT / "kit"
    tools = KIT_ROOT / "tools" / "bin"
    clang = str(tools / "clang")
    lld = str(tools / "ld.lld")
    nm = str(tools / "llvm-nm")
    native_tool = str(tools / "ps5-native-tool")

    info = json.loads((kit / "kit.json").read_text())
    place = lambda s: s.replace("{kit}", str(kit))

    base_flags = [place(f) for f in info["target_flags"]] + [
        "-march=znver2",
        "-O2",
        "-fno-strict-aliasing",
        "-DRT_CPU_LEVEL=3",
        "-Dpreserve_most=noinline",
        "-ffunction-sections",
        "-fdata-sections",
        "-I",
        str(PROJECT_ROOT / "third_party" / "ps5_compat_inc"),
        "-I",
        str(PROJECT_ROOT / "ps5"),
        "-I",
        str(TOTK_RT),
        "-I",
        str(GEN_DIR),
        "-isystem",
        str(PROJECT_ROOT / "third_party" / "vk_headers"),
    ]

    # 1. Compile ps5/* backends + modules_stub.c
    ps5_objs: list[str] = []
    stub_mod = generate_stub_modules_c()
    for src_path in [PROJECT_ROOT / p for p in PS5_SOURCES] + [stub_mod]:
        obj = LINK_DIR / f"{src_path.stem}.o"
        run(
            [clang, *base_flags, "-Wall", "-Wextra", "-c", str(src_path), "-o", str(obj)],
            f"compile {src_path.name}",
        )
        ps5_objs.append(str(obj))

    # 2. Collect all 131 compiled TOTK runtime objects
    rt_objs: list[str] = []
    for p in sorted(RT_OBJ_DIR.rglob("*.o")):
        rel_c = p.relative_to(RT_OBJ_DIR).with_suffix(".c").as_posix()
        rel_cpp = p.relative_to(RT_OBJ_DIR).with_suffix(".cpp").as_posix()
        if rel_c in SKIP_RT_FILES or rel_cpp in SKIP_RT_FILES:
            continue
        rt_objs.append(str(p))

    print(f"[link-rt] Collected {len(rt_objs)} TOTK runtime .o + {len(ps5_objs)} PS5 backend .o")

    # 3. Collect precompiled PS5 opus objects from the kit
    opus_objs = sorted(str(p) for p in (kit / "obj").glob("opus_*.o"))
    print(f"[link-rt] Adding {len(opus_objs)} precompiled PS5 Opus .o from kit")

    local_map = LINK_DIR / "local.map"
    local_map.write_text("{\n    local:\n        fork;\n        isatty;\n};\n", encoding="utf-8")

    lk = info["link"]
    sdk_lib = kit / "sdk" / "target" / "lib"
    stubs = [str(kit / "lib" / "stubs" / n) for n in ("libSceAgc.so", "libSceAgcDriver.so")]
    elf = LINK_DIR / "totk_rt_pie.elf"
    link_map = LINK_DIR / "totk_rt.map"

    link_args = (
        [
            "-m",
            "elf_x86_64",
            "-pie",
            "--eh-frame-hdr",
            "-z",
            "max-page-size=0x4000",
            "-mllvm",
            "-emulated-tls",
        ]
        + [place(a) for a in lk["script"]]
        + [place(a) for a in lk["flags"]]
        + [
            "--version-script",
            str(kit / "link" / "native" / "app-symbols.map"),
            "--version-script",
            str(local_map),
            "--exclude-libs=ALL",
            "--gc-sections",
            "-e",
            "_start",
            f"-Map={link_map}",
            "-o",
            str(elf),
            str(kit / "obj" / "app_crt.o"),
        ]
        + rt_objs
        + ps5_objs
        + opus_objs
        + [
            str(kit / "lib" / "libzstd.a"),
            str(kit / "lib" / "libavcodec.a"),
            str(kit / "lib" / "libdav1d.a"),
            str(kit / "lib" / "libavutil.a"),
        ]
        + stubs
        + [place(a) for a in lk["inputs"]]
        + ["--as-needed"]
        + sorted(str(sdk_lib / f) for f in os.listdir(sdk_lib) if f.endswith(".so"))
        + ["--hash-style=gnu"]
    )

    rsp = LINK_DIR / "link.rsp"
    res = run([lld, write_rsp(rsp, link_args)], "ld.lld link full TOTK runtime", check=False)
    if res.returncode != 0:
        print("\n=== LD.LLD LINK ERRORS ===")
        print((res.stdout + "\n" + res.stderr)[-4500:])
        return res.returncode

    exported = set((kit / "link" / "exported.txt").read_text().split())

    def undefined(kinds: tuple[str, ...]) -> list[str]:
        out = run([nm, "-D", "--undefined-only", str(elf)], "nm dynamic imports").stdout
        syms: set[str] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in kinds:
                syms.add(parts[1].split("@")[0])
        return sorted(syms)

    weak_unexported = [s for s in undefined(("w", "v")) if s not in exported]
    if weak_unexported:
        print(f"[link-rt] Binding {len(weak_unexported)} unexported weak symbols to 0")
        run(
            [lld, write_rsp(rsp, link_args + [f"--defsym={s}=0" for s in weak_unexported])],
            "re-link resolving weak symbols",
        )

    unresolved = [s for s in undefined(("U",)) if s not in exported]
    if unresolved:
        print(f"\n=== UNEXPORTED PS5 IMPORTS ({len(unresolved)}) ===")
        for s in unresolved:
            print("  MISSING:", s)
        return 2

    eboot_elf = LINK_DIR / "totk_rt.elf.new"
    out_bin = OUT_DIR / "totk_rt_probe.bin"
    run(
        [
            native_tool,
            "link",
            "--in",
            str(elf),
            "--out",
            str(eboot_elf),
            "--stub-dir",
            str(sdk_lib),
            "--stub",
            str(kit / "lib" / "stubs" / "libSceAgc.so"),
            "--stub",
            str(kit / "lib" / "stubs" / "libSceAgcDriver.so"),
            "--module-sdk",
            "0x02000009",
            "--companion-sdk",
            "0x08050001",
            "--file-name",
            "eboot.elf",
        ],
        "ps5-native-tool link",
    )
    run(
        [
            native_tool,
            "self",
            "--sign",
            "--in",
            str(eboot_elf),
            "--out",
            str(out_bin),
            "--magic",
            "0x1D3D154F",
        ],
        "ps5-native-tool self --sign",
    )
    insp = run([native_tool, "self", "--inspect", "--file", str(out_bin)], "self --inspect")
    print(insp.stdout.strip())
    size_mb = out_bin.stat().st_size / (1024 * 1024)
    print(f"[ok] FULL TOTK RUNTIME SIGNED PS5 FSELF: {out_bin} ({size_mb:.2f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
