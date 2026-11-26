#!/usr/bin/env python3
"""Extract the local PS5 clang/lld/ps5-native-tool + Mesa RADV PS5 kit
from PS5LongshotPlusBuilder AppImage into third_party/ps5-kit/.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_APPIMAGE = Path(
    "/home/saul/AppImages/PS5LongshotPlusBuilder-v0.3.4-plus-linux-x64.AppImage"
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DEST = PROJECT_ROOT / "third_party" / "ps5-kit"


def get_appimage_offset(appimage: Path) -> int:
    res = subprocess.run(
        [str(appimage), "--appimage-offset"],
        check=True,
        capture_output=True,
        text=True,
    )
    return int(res.stdout.strip())


def extract_kit(appimage: Path, dest: Path, force: bool = False) -> None:
    if not appimage.is_file():
        raise FileNotFoundError(f"AppImage not found: {appimage}")

    if dest.exists():
        if not force:
            kit_json = dest / "kit" / "kit.json"
            clang = dest / "tools" / "bin" / "clang"
            if kit_json.is_file() and clang.is_file():
                print(f"[ok] PS5 kit already extracted at {dest}")
                verify_kit(dest)
                return
        shutil.rmtree(dest)

    offset = get_appimage_offset(appimage)
    print(f"[info] AppImage SquashFS offset: {offset}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ps5kit_extract_") as tmp:
        tmp_dir = Path(tmp)
        sq_root = tmp_dir / "sq"
        cmd = [
            "unsquashfs",
            "-o",
            str(offset),
            "-d",
            str(sq_root),
            str(appimage),
            "usr/PS5LongshotPlusBuilder/kit",
            "usr/PS5LongshotPlusBuilder/tools",
            "usr/PS5LongshotPlusBuilder/VERSION",
            "usr/PS5LongshotPlusBuilder/app/pipeline.py",
        ]
        print(f"[run] {' '.join(cmd)}")
        subprocess.run(cmd, check=True)

        base = sq_root / "usr" / "PS5LongshotPlusBuilder"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(base / "kit"), str(dest / "kit"))
        shutil.move(str(base / "tools"), str(dest / "tools"))
        ref_dir = dest / "ref"
        ref_dir.mkdir(exist_ok=True)
        for rel in ("VERSION", "app/pipeline.py"):
            src = base / rel
            if src.is_file():
                shutil.copy2(src, ref_dir / src.name)

    verify_kit(dest)


def verify_kit(dest: Path) -> None:
    required = [
        dest / "kit" / "kit.json",
        dest / "kit" / "lib" / "libvulkan_radeon.ps5.a",
        dest / "kit" / "sdk" / "target" / "lib" / "libps5platform.a",
        dest / "kit" / "link" / "native" / "ps5-pie.ld",
        dest / "kit" / "obj" / "app_crt.o",
        dest / "tools" / "bin" / "clang",
        dest / "tools" / "bin" / "ld.lld",
        dest / "tools" / "bin" / "ps5-native-tool",
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(f"Missing expected PS5 kit files:\n  " + "\n  ".join(missing))

    kit_cfg = json.loads((dest / "kit" / "kit.json").read_text())
    print(f"[ok] kit.json loaded (keys: {', '.join(sorted(kit_cfg.keys()))})")

    for tool, args in (
        ("clang", ["--version"]),
        ("ld.lld", ["--version"]),
        ("ps5-native-tool", ["--help"]),
    ):
        tool_path = dest / "tools" / "bin" / tool
        res = subprocess.run(
            [str(tool_path), *args],
            capture_output=True,
            text=True,
        )
        first_line = (res.stdout or res.stderr).strip().splitlines()[0]
        print(f"[ok] {tool}: {first_line}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract PS5 toolchain + RADV kit")
    parser.add_argument("--appimage", type=Path, default=DEFAULT_APPIMAGE)
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    extract_kit(args.appimage, args.dest, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
