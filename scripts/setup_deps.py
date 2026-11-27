#!/usr/bin/env python3
"""Bootstrap third_party/vk_headers/ and third_party/vma/ for building from source.

Fetches GPUOpen VulkanMemoryAllocator (v3.3.0, MIT) and links system Vulkan,
Opus, and Zstandard headers into third_party/vk_headers/ so `probe_runtime_compile.py`
and `make_appimage.py` work cleanly on a fresh clone.
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VK_HEADERS_DIR = PROJECT_ROOT / "third_party" / "vk_headers"
VMA_DIR = PROJECT_ROOT / "third_party" / "vma"

VMA_URL = "https://raw.githubusercontent.com/GPUOpen-LibrariesAndSDKs/VulkanMemoryAllocator/v3.3.0/include/vk_mem_alloc.h"


def setup_vma() -> None:
    VMA_DIR.mkdir(parents=True, exist_ok=True)
    dst = VMA_DIR / "vk_mem_alloc.h"
    if dst.is_file() and dst.stat().st_size > 100_000:
        print(f"[ok] VMA header already present: {dst}")
        return
    print(f"[dl] Fetching {VMA_URL} -> {dst}")
    req = urllib.request.Request(VMA_URL, headers={"User-Agent": "totk-ps5-recomp/setup"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    dst.write_bytes(data)
    print(f"[ok] Saved {dst} ({len(data):,} bytes)")


def setup_vk_headers() -> None:
    VK_HEADERS_DIR.mkdir(parents=True, exist_ok=True)
    needed = {
        "vulkan": Path("/usr/include/vulkan"),
        "vk_video": Path("/usr/include/vk_video"),
        "opus": Path("/usr/include/opus"),
        "zstd.h": Path("/usr/include/zstd.h"),
        "zstd_errors.h": Path("/usr/include/zstd_errors.h"),
    }
    missing: list[str] = []
    for name, sys_path in needed.items():
        dst = VK_HEADERS_DIR / name
        if dst.exists() or dst.is_symlink():
            continue
        if not sys_path.exists():
            missing.append(str(sys_path))
            continue
        os.symlink(sys_path, dst)
        print(f"[ok] Linked {dst} -> {sys_path}")
    if missing:
        raise RuntimeError(
            "Missing system development headers (install libvulkan-dev libopus-dev libzstd-dev / vulkan-headers opus zstd):\n  "
            + "\n  ".join(missing)
        )
    print(f"[ok] third_party/vk_headers ready at {VK_HEADERS_DIR}")


def main() -> int:
    setup_vma()
    setup_vk_headers()
    return 0


if __name__ == "__main__":
    sys.exit(main())
