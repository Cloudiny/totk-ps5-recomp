#!/usr/bin/env python3
"""Empirically audit <TOTK_UPSTREAM_SRC>/ for PS5 porting blockers.

Scans runtime/ and tools/xlate/ for OS/window/audio/media/process/Vulkan dependencies
and outputs a structured JSON + Markdown summary.
"""

from __future__ import annotations

import os

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_TOTK_ROOT = Path(os.environ.get("TOTK_UPSTREAM_SRC", str(Path(__file__).resolve().parent.parent.parent / "totk-linux-native-recomp")))

PATTERNS: dict[str, re.Pattern[str]] = {
    "linux_futex": re.compile(r"linux/futex\.h|SYS_futex|FUTEX_WAIT|FUTEX_WAKE"),
    "linux_userfaultfd": re.compile(r"linux/userfaultfd\.h|UFFDIO_|userfaultfd"),
    "linux_epoll_eventfd": re.compile(r"sys/epoll\.h|sys/eventfd\.h|sys/inotify\.h|linux/"),
    "process_spawn": re.compile(r"\b(posix_spawn|fork|execv|execvp|popen)\s*\("),
    "dlopen_vulkan": re.compile(r"dlopen\s*\(|libvulkan\.so"),
    "sdl3": re.compile(r"<SDL3/|SDL_"),
    "libopus": re.compile(r"<opus/|opus_decoder"),
    "libvpx_or_ffmpeg": re.compile(r"<vpx/|vpx_codec|libavcodec"),
    "win32_only": re.compile(r"<windows\.h>|VirtualAlloc|CreateWindow"),
    "vulkan_ext": re.compile(r"VK_(?:KHR|EXT)_[A-Za-z0-9_]+"),
    "mmap_direct": re.compile(r"\b(mmap|mprotect|munmap|madvise)\s*\("),
    "pthreads": re.compile(r"<pthread\.h>|pthread_create"),
    "signals": re.compile(r"sigaction\s*\(|SIGSEGV|ucontext_t"),
}


def scan_tree(root: Path, subdirs: tuple[str, ...] = ("runtime", "tools/xlate")) -> dict:
    files_report = []
    totals: dict[str, int] = {k: 0 for k in PATTERNS}
    vulkan_exts: set[str] = set()
    total_loc = 0

    for sub in subdirs:
        base = root / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in {".c", ".h", ".cc", ".cpp", ".hpp"}:
                continue
            text = path.read_text(errors="replace")
            loc = text.count("\n") + 1
            total_loc += loc
            rel = str(path.relative_to(root))
            hits: dict[str, int] = {}
            for name, rx in PATTERNS.items():
                matches = rx.findall(text)
                if matches:
                    hits[name] = len(matches)
                    totals[name] += 1
                    if name == "vulkan_ext":
                        for m in re.finditer(rx, text):
                            vulkan_exts.add(m.group(0))
            if hits:
                files_report.append(
                    {
                        "path": rel,
                        "loc": loc,
                        "hits": hits,
                    }
                )

    return {
        "totk_root": str(root),
        "scanned_subdirs": list(subdirs),
        "total_loc": total_loc,
        "files_with_platform_deps": len(files_report),
        "category_file_counts": totals,
        "vulkan_extensions_referenced": sorted(vulkan_exts),
        "files": files_report,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# TOTK → PS5 Empirical Porting Inventory",
        "",
        f"- **Source scanned:** `{report['totk_root']}` (`{', '.join(report['scanned_subdirs'])}`)",
        f"- **Total scanned LOC:** `{report['total_loc']:,}`",
        f"- **Files with platform dependencies:** `{report['files_with_platform_deps']}`",
        "",
        "## Dependency Category Summary (file counts)",
        "",
        "| Category | Files | PS5 Replacement Strategy |",
        "|---|---:|---|",
    ]
    strategy = {
        "linux_futex": "FreeBSD/PS5 `_umtx_op` or `pthread_cond`/`sceKernelWaitEventFlag`",
        "linux_userfaultfd": "PS5 `sceKernelReserveVirtualRange` + `SIGSEGV` handler + `sceKernelMapDirectMemory`",
        "linux_epoll_eventfd": "PS5 `kqueue` / `poll` / `libps5platform.a`",
        "process_spawn": "**BLOCKER on PS5** — link `tools/xlate` in-process as static library",
        "dlopen_vulkan": "Static `libvulkan_radeon.ps5.a` via `vk_icdGetInstanceProcAddr`",
        "sdl3": "Native `VK_KHR_display` + `libScePad` + `libSceAudioOut`",
        "libopus": "Already precompiled in PS5 kit (`kit/obj/opus_*.o`!)",
        "libvpx_or_ffmpeg": "Replace `libvpx` with kit's precompiled `kit/lib/libavcodec.a`",
        "win32_only": "Excluded from PS5 build",
        "vulkan_ext": "Verify each required ext against `libvulkan_radeon.ps5.a`",
        "mmap_direct": "Map guest RAM via `sceKernelAllocateDirectMemory` + `sceKernelMapDirectMemory`",
        "pthreads": "Native `libkernel` + `libps5platform.a` `--wrap=pthread_*`",
        "signals": "PS5 `sigaction(SIGSEGV, ...)` + `ucontext_t` (`mc_rip`/`mc_rax`)",
    }
    for cat, count in report["category_file_counts"].items():
        if count > 0:
            lines.append(f"| `{cat}` | {count} | {strategy.get(cat, '')} |")

    lines += [
        "",
        "## Vulkan Extensions Referenced in TOTK Runtime",
        "",
    ]
    for ext in report["vulkan_extensions_referenced"]:
        lines.append(f"- `{ext}`")

    lines += [
        "",
        "## Key Files Requiring PS5 Porting Attention",
        "",
        "| File | LOC | Tags |",
        "|---|---:|---|",
    ]
    priority = {
        "linux_futex",
        "linux_userfaultfd",
        "process_spawn",
        "dlopen_vulkan",
        "sdl3",
        "libopus",
        "libvpx_or_ffmpeg",
    }
    for entry in report["files"]:
        if any(k in priority for k in entry["hits"]):
            tags = ", ".join(f"`{k}`({v})" for k, v in sorted(entry["hits"].items()))
            lines.append(f"| `{entry['path']}` | {entry['loc']} | {tags} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit TOTK runtime for PS5 porting")
    parser.add_argument("--totk-root", type=Path, default=DEFAULT_TOTK_ROOT)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--md-out", type=Path, default=None)
    args = parser.parse_args()

    if not args.totk_root.is_dir():
        print(f"error: TOTK repo not found at {args.totk_root}", file=sys.stderr)
        return 1

    report = scan_tree(args.totk_root)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
    if args.md_out:
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(report))

    print(
        f"[ok] audited {report['total_loc']:,} LOC across {report['files_with_platform_deps']} files "
        f"({len(report['vulkan_extensions_referenced'])} Vulkan extensions referenced)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
