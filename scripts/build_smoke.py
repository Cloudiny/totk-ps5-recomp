#!/usr/bin/env python3
"""Build & sign the Phase 0 PS5 Vulkan/RADV smoke FSELF (out/PPSA99199/eboot.bin)."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KIT_ROOT = PROJECT_ROOT / "third_party" / "ps5-kit"
BUILD_DIR = PROJECT_ROOT / "build" / "smoke"
OUT_DIR = PROJECT_ROOT / "out" / "PPSA99199"
TITLE_ID = "PPSA99199"


def run_cmd(cmd: list[str], what: str) -> subprocess.CompletedProcess[str]:
    print(f"[build] {what}: {' '.join(cmd[:6])}{' ...' if len(cmd) > 6 else ''}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR during {what} (rc={res.returncode}):", file=sys.stderr)
        if res.stdout:
            print(res.stdout[-2000:], file=sys.stderr)
        if res.stderr:
            print(res.stderr[-2000:], file=sys.stderr)
        raise SystemExit(res.returncode)
    return res


def write_rsp(path: Path, args: list[str]) -> str:
    lines = []
    for a in args:
        escaped = a.replace("\\", "/").replace('"', '\\"')
        lines.append(f'"{escaped}"\n')
    path.write_text("".join(lines), encoding="utf-8")
    return f"@{path}"


def build_smoke() -> Path:
    kit = KIT_ROOT / "kit"
    tools = KIT_ROOT / "tools" / "bin"
    kit_json_path = kit / "kit.json"
    if not kit_json_path.is_file():
        raise FileNotFoundError(
            f"PS5 kit not found at {kit}. Run scripts/extract_ps5_kit.py first."
        )

    info = json.loads(kit_json_path.read_text())
    place = lambda s: s.replace("{kit}", str(kit))

    clang = str(tools / "clang")
    lld = str(tools / "ld.lld")
    nm = str(tools / "llvm-nm")
    native_tool = str(tools / "ps5-native-tool")

    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    src = PROJECT_ROOT / "smoke" / "hello_ps5_vk.c"
    obj = BUILD_DIR / "hello_ps5_vk.o"

    # Compile with the PS5 kit target flags + system Vulkan headers (types/typedefs only via VK_NO_PROTOTYPES)
    cflags = (
        [place(f) for f in info["target_flags"]]
        + [
            "-march=znver2",
            "-O2",
            "-ffunction-sections",
            "-fdata-sections",
            "-Wall",
            "-Wextra",
            "-isystem",
            "/usr/include",
            "-c",
            str(src),
            "-o",
            str(obj),
        ]
    )
    run_cmd([clang, *cflags], "compile smoke/hello_ps5_vk.c")

    lk = info["link"]
    sdk_lib = kit / "sdk" / "target" / "lib"
    stubs = [str(kit / "lib" / "stubs" / n) for n in ("libSceAgc.so", "libSceAgcDriver.so")]
    elf = BUILD_DIR / "llvm-pie.elf"
    link_map = BUILD_DIR / "smoke.map"

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
            "--exclude-libs=ALL",
            "--gc-sections",
            "-e",
            "_start",
            f"-Map={link_map}",
            "-o",
            str(elf),
            str(kit / "obj" / "app_crt.o"),
            str(obj),
        ]
        + stubs
        + [place(a) for a in lk["inputs"]]
        + ["--as-needed"]
        + sorted(str(sdk_lib / f) for f in os.listdir(sdk_lib) if f.endswith(".so"))
        + ["--hash-style=gnu"]
    )

    rsp_path = BUILD_DIR / "link.rsp"
    run_cmd([lld, write_rsp(rsp_path, link_args)], "link llvm-pie.elf")

    exported = set((kit / "link" / "exported.txt").read_text().split())

    def undefined(kinds: tuple[str, ...]) -> list[str]:
        out = run_cmd([nm, "-D", "--undefined-only", str(elf)], "inspect dynamic imports").stdout
        syms: set[str] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in kinds:
                syms.add(parts[1].split("@")[0])
        return sorted(syms)

    weak_unexported = [s for s in undefined(("w", "v")) if s not in exported]
    if weak_unexported:
        link_args_weak = link_args + [f"--defsym={s}=0" for s in weak_unexported]
        run_cmd([lld, write_rsp(rsp_path, link_args_weak)], "re-link resolving weak symbols")

    unresolved = [s for s in undefined(("U",)) if s not in exported]
    if unresolved:
        print(
            "ERROR: unresolved imports not in PS5 exported.txt:\n  "
            + "\n  ".join(unresolved[:30]),
            file=sys.stderr,
        )
        raise SystemExit(1)

    eboot_elf = BUILD_DIR / "eboot.elf.new"
    eboot_bin = OUT_DIR / "eboot.bin"
    run_cmd(
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
    run_cmd(
        [
            native_tool,
            "self",
            "--sign",
            "--in",
            str(eboot_elf),
            "--out",
            str(eboot_bin),
            "--magic",
            "0x1D3D154F",
        ],
        "ps5-native-tool self --sign",
    )
    inspect = run_cmd(
        [native_tool, "self", "--inspect", "--file", str(eboot_bin)],
        "ps5-native-tool self --inspect",
    )
    print(inspect.stdout.strip())

    # Package minimal title metadata + libc.prx for ShadowMountPlus 1.7beta12
    sce_mod_out = OUT_DIR / "sce_module"
    sce_sys_out = OUT_DIR / "sce_sys"
    sce_mod_out.mkdir(parents=True, exist_ok=True)
    sce_sys_out.mkdir(parents=True, exist_ok=True)

    shutil.copy2(kit / "title" / "sce_module" / "libc.prx", sce_mod_out / "libc.prx")
    param = json.loads((kit / "title" / "sce_sys" / "param.json").read_text(encoding="utf-8-sig"))
    param["titleId"] = TITLE_ID
    param["conceptId"] = "99199"
    param["contentId"] = f"UP9000-{TITLE_ID}_00-PS5TOTKRECOMP001"
    param["localizedParameters"] = {
        "defaultLanguage": "en-US",
        "en-US": {"titleName": "TOTK PS5 (Phase 0 Smoke)"},
        "es-MX": {"titleName": "TOTK PS5 (Prueba Fase 0)"},
    }
    (sce_sys_out / "param.json").write_text(json.dumps(param, indent=2) + "\n", encoding="utf-8")

    # Copy placeholder icon so PS5 Home screen displays the title cleanly if mounted
    icon_src = kit / "title" / "sce_sys" / "icon0.png"
    if icon_src.is_file():
        shutil.copy2(icon_src, sce_sys_out / "icon0.png")

    size_mb = eboot_bin.stat().st_size / (1024 * 1024)
    print(f"[ok] Built signed PS5 FSELF: {eboot_bin} ({size_mb:.2f} MiB)")
    return eboot_bin


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 0 PS5 Vulkan smoke FSELF")
    parser.parse_args()
    build_smoke()
    return 0


if __name__ == "__main__":
    sys.exit(main())
