#!/usr/bin/env python3
"""PS5 TOTK Builder CLI (used both directly and as the AppImage entrypoint).

Examples:
  # Self-check kit, clang, ld.lld, ps5-native-tool, and libtotkrt_ps5.a:
  python3 -m builder.cli --check

  # Print exact PS5 directory layout (/data/homebrew/PPSA99199 & /data/totk-ps5):
  python3 -m builder.cli --show-layout

  # Full build (eboot + PS prompts + shaders + mods) and direct FTP deploy to PS5:
  python3 -m builder.cli --exefs /path/to/exefs --romfs /path/to/romfs \
      --pretranslate-shaders --mod /path/to/mod.zip --deploy-ftp <PS5_IP> --out ./out
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from .deploy import PS5_LAYOUT_TEXT, deploy_to_ps5
from .pipeline import (
    build_full_ps5_game,
    build_runtime_archive,
    default_kit_paths,
)


def extract_single_game_file(
    paths,
    game_file: Path,
    keys_file: Path | None,
    work_dir: Path,
    update_file: Path | None = None,
) -> tuple[Path, Path]:
    """Extract a .xci/.nsp base game (and optional update .nsp) into work_dir/extracted/v*/{exefs,romfs}."""
    extract_py = paths.totk_tools_dir / "extract.py"
    if not extract_py.is_file():
        raise FileNotFoundError(f"Extractor script missing: {extract_py}")
    if not game_file.is_file():
        raise FileNotFoundError(f"Game file not found: {game_file}")
    if not keys_file or not keys_file.is_file():
        raise FileNotFoundError("Switch prod.keys (--keys) is required to extract .xci/.nsp game files")
    cmd = [
        str(paths.python_bin),
        str(extract_py),
        "--base",
        str(game_file),
        "--keys",
        str(keys_file),
        "--work",
        str(work_dir),
    ]
    if update_file and update_file.is_file():
        cmd += ["--update", str(update_file)]
    hactool = paths.totk_tools_dir.parent / "toolchain" / "hactool" / "hactool"
    if hactool.is_file():
        cmd += ["--hactool", str(hactool)]
    print(f"[ps5-totk] Extracting {game_file.name} -> {work_dir / 'extracted'}...")
    subprocess.run(cmd, check=True)
    ex_root = work_dir / "extracted"
    for ver in ("v143", "v121", "v112", "v110", "v0"):
        cand = ex_root / ver
        if (cand / "exefs" / "main").is_file() and (cand / "romfs" / "romfs.bin").is_file():
            return cand / "exefs", cand / "romfs"
    raise FileNotFoundError(f"Extraction finished but no valid exefs/romfs found under {ex_root}")


def run_check(paths) -> int:
    print(f"[check] project_root : {paths.project_root}")
    print(f"[check] ps5-kit      : {paths.kit_root}")
    for tool in (paths.clang, paths.lld, paths.nm, paths.native_tool):
        if not tool.is_file():
            print(f"[FAIL] missing tool: {tool}", file=sys.stderr)
            return 1
    res = subprocess.run([str(paths.clang), "--version"], capture_output=True, text=True, check=True)
    print(f"[check] clang        : {res.stdout.splitlines()[0]}")
    print(f"[check] radv         : {paths.kit / 'lib' / 'libvulkan_radeon.ps5.a'}")
    print(f"[check] libavcodec   : {paths.kit / 'lib' / 'libavcodec.a'}")
    print(f"[check] sce_sys art  : {paths.assets_sce_sys}")
    print("[ok] PS5 TOTK Builder kit self-check PASSED")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PS5 Tears of the Kingdom Builder (PPSA99199)")
    parser.add_argument("--check", action="store_true", help="Verify kit & toolchain")
    parser.add_argument("--show-layout", action="store_true", help="Print exact PS5 directory layout")
    parser.add_argument("--build-runtime-lib", action="store_true", help="Build reusable libtotkrt_ps5.a only")
    parser.add_argument("--game", type=Path, default=None, help="Base TOTK game file (.xci / .nsp)")
    parser.add_argument("--update", type=Path, default=None, help="Optional TOTK update file (.nsp, e.g. v1.4.3)")
    parser.add_argument("--keys", type=Path, default=None, help="Switch prod.keys (for --game)")
    parser.add_argument("--exefs", type=Path, default=None, help="Extracted ExeFS directory")
    parser.add_argument("--romfs", type=Path, default=None, help="Extracted RomFS directory")
    parser.add_argument("--gen-dir", type=Path, default=None, help="Existing lifted C directory")
    parser.add_argument("--skip-lift", action="store_true", help="Reuse existing --gen-dir without re-lifting")
    parser.add_argument("--shaders", type=Path, default=None, help="Directory with pre-translated shader caches")
    parser.add_argument(
        "--pretranslate-shaders",
        action="store_true",
        help="Run full PC-side RomFS shader pre-translation for PS5 RADV (TOTK_ZERO_LOCALS=0)",
    )
    parser.add_argument(
        "--no-prompts",
        action="store_true",
        help="Skip PlayStation button prompt overlay generation (default: enabled)",
    )
    parser.add_argument(
        "--mod",
        dest="mods",
        action="append",
        type=Path,
        default=[],
        help="RomFS mod folder or .zip archive to stage into /data/totk-ps5/mods/ (repeatable)",
    )
    parser.add_argument(
        "--res",
        default="2560x1440",
        help="Default PS5 output resolution (default: 2560x1440; 1920x1080 / 3840x2160 supported)",
    )
    parser.add_argument(
        "--hz",
        type=int,
        default=120,
        choices=(60, 120),
        help="Default PS5 display refresh rate (60 or 120 Hz; default: 120)",
    )
    parser.add_argument(
        "--frame-gen",
        default="fsr3",
        choices=("off", "fsr3"),
        help="Default AMD FSR 3.1.5 Frame Generation mode (off or fsr3; default: fsr3)",
    )
    parser.add_argument(
        "--fps-limit",
        default="60",
        help="Target frame rate limit (60 locks 2-vblank 60 FPS on 120 Hz FIFO; 90/120/display for VRR)",
    )
    parser.add_argument("--scale", default="75", help="Default 3D render scale (default: 75)")
    parser.add_argument("--lang", default="es-419", help="Default game language (default: es-419)")
    parser.add_argument("--work", type=Path, default=None, help="Working build directory")
    parser.add_argument("--out", type=Path, default=None, help="Output directory (receives PPSA99199/ & data_totk_ps5/)")
    parser.add_argument("--runtime-lib", type=Path, default=None, help="Prebuilt libtotkrt_ps5.a path")
    parser.add_argument("--jobs", type=int, default=8, help="Parallel compile jobs")

    # Direct PS5 FTP deployment options
    parser.add_argument("--deploy-ftp", default=None, help="PS5 IP address to upload built output via ftpsrv")
    parser.add_argument("--ftp-port", type=int, default=2121, help="PS5 ftpsrv port (default: 2121)")
    parser.add_argument("--deploy-only", action="store_true", help="Skip building; upload existing --out to PS5")
    parser.add_argument("--deploy-romfs", action="store_true", help="Also upload 15.86 GiB romfs.bin over FTP")
    parser.add_argument("--skip-ftp-shaders", action="store_true", help="Skip shader-cache.pack upload over FTP")
    parser.add_argument("--skip-ftp-ini", action="store_true", help="Keep existing /data/totk-ps5/totk.ini on PS5")
    args = parser.parse_args(argv)

    paths = default_kit_paths()
    if args.show_layout:
        print(PS5_LAYOUT_TEXT)
        return 0
    if args.check:
        return run_check(paths)

    work_dir = (args.work or (paths.project_root / "build" / "game_ps5")).resolve()
    out_root = (args.out or (paths.project_root / "out")).resolve()

    default_rt_lib = paths.project_root / "build" / "libtotkrt_ps5.a"
    bundled_rt_lib = paths.project_root / "kit_bundle" / "libtotkrt_ps5.a"
    rt_lib = args.runtime_lib or (bundled_rt_lib if bundled_rt_lib.is_file() else default_rt_lib)

    if args.build_runtime_lib or (not args.deploy_only and not rt_lib.is_file()):
        build_runtime_archive(paths, rt_lib, work_dir)
        if args.build_runtime_lib:
            return 0

    exefs_dir = args.exefs
    romfs_dir = args.romfs

    if not args.deploy_only:
        if args.game:
            exefs_dir, romfs_dir = extract_single_game_file(paths, args.game, args.keys, work_dir, args.update)
        if not exefs_dir:
            parser.error("Provide --game <totk.xci|nsp> or --exefs <dir> (or --deploy-only)")

        gen_dir = (args.gen_dir or (work_dir / "generated")).resolve()
        build_full_ps5_game(
            paths=paths,
            exefs_dir=exefs_dir.resolve(),
            romfs_dir=romfs_dir.resolve() if romfs_dir else None,
            gen_dir=gen_dir,
            work_dir=work_dir,
            out_root=out_root,
            runtime_lib=rt_lib.resolve(),
            shader_src_dir=args.shaders.resolve() if args.shaders else None,
            jobs=args.jobs,
            skip_lift=args.skip_lift,
            build_prompts=not args.no_prompts,
            pretranslate_shaders=args.pretranslate_shaders,
            mods=[m.resolve() for m in args.mods],
            output_res=args.res,
            render_scale=args.scale,
            lang=args.lang,
            ps5_hz=args.hz,
            frame_gen=args.frame_gen,
            fps_limit=args.fps_limit,
        )

    if args.deploy_ftp:
        romfs_bin = (romfs_dir / "romfs.bin") if romfs_dir and (romfs_dir / "romfs.bin").is_file() else None
        deploy_to_ps5(
            host=args.deploy_ftp,
            port=args.ftp_port,
            out_root=out_root,
            exefs_dir=exefs_dir.resolve() if exefs_dir and exefs_dir.is_dir() else None,
            romfs_bin=romfs_bin,
            upload_shaders=not args.skip_ftp_shaders,
            upload_ini=not args.skip_ftp_ini,
            upload_romfs=args.deploy_romfs,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
