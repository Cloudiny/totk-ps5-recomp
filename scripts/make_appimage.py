#!/usr/bin/env python3
"""Package PS5TotkBuilder-v0.1.0-linux-x64.AppImage (modeled after PS5LongshotPlusBuilder).

Contains ZERO Nintendo game data:
  - Prebuilt game-free libtotkrt_ps5.a (all TOTK runtime + PS5 backends + Opus)
  - PS5 toolchain (clang, ld.lld, llvm-nm, ps5-native-tool) + Mesa RADV PS5 + PS5 SDK
  - TOTK lifter (recomp/), romfs_index.py, extract.py, install-side runtime .c & headers
  - Custom TOTK PS5 branding (icon0.png, 4K BC7 pic0/pic1.dds, param.json for PPSA99199)
  - CLI + Tkinter GUI entrypoint (AppRun)
"""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOTK_SRC = Path(os.environ.get("TOTK_UPSTREAM_SRC", str(PROJECT_ROOT.parent / "totk-linux-native-recomp")))
APPDIR = PROJECT_ROOT / "AppDir"
OUT_APPIMAGE = PROJECT_ROOT / "out" / "PS5TotkBuilder-v0.1.0-linux-x64.AppImage"
CACHE_DIR = PROJECT_ROOT / ".local" / "builder-downloads"
APPIMAGETOOL = Path(shutil.which("appimagetool") or (Path.home() / ".local" / "bin" / "appimagetool"))

PYTHON_STANDALONE_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/20261110/"
    "cpython-3.13.18+20261110-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
)
PYTHON_STANDALONE_SHA256 = "f2d2199eb25880e07863b391cf7124e7ffa1338b0d65600dfcec117c4223a7fb"
BUNDLED_PACKAGES = [
    "PyQt6==6.12.1",
    "Pillow>=10.4.0",
    "capstone==5.0.9",
    "lz4==4.4.5",
    "zstandard==0.25.0",
    "numpy==2.5.4",
    "fonttools>=4.53.0",
]

INSTALL_SIDE = {
    "romfs.c",
    "patches.c",
    "ov_zstd.c",
    "mouse_direct.c",
    "ov_ability.c",
    "plugin_init.c",
    "freecam.c",
}


def copy_clean_tree(src: Path, dst: Path, ignore_fn=None) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True, ignore=ignore_fn)


def _prepare_standalone_python() -> Path:
    """Download & cache CPython 3.13 standalone with PyQt6 + all lifter wheels."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    env_dir = CACHE_DIR / "python313-env"
    marker = env_dir / ".totk_pkgs_ready_v1"
    if marker.is_file() and (env_dir / "bin" / "python3").is_file():
        return env_dir

    tar_path = CACHE_DIR / "cpython-3.13-linux-x64.tar.gz"
    if not tar_path.is_file():
        print(f"[dl] Fetching CPython 3.13 standalone -> {tar_path}")
        req = urllib.request.Request(PYTHON_STANDALONE_URL, headers={"User-Agent": "PS5TotkBuilder/0.1"})
        tmp_dl = tar_path.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=120) as resp, tmp_dl.open("wb") as out_f:
            shutil.copyfileobj(resp, out_f, length=524288)
        h = hashlib.sha256(tmp_dl.read_bytes()).hexdigest()
        if h != PYTHON_STANDALONE_SHA256:
            tmp_dl.unlink(missing_ok=True)
            raise RuntimeError(f"SHA-256 mismatch for CPython standalone: {h} != {PYTHON_STANDALONE_SHA256}")
        os.replace(tmp_dl, tar_path)

    if env_dir.exists():
        shutil.rmtree(env_dir)
    unpack_tmp = CACHE_DIR / "python313-unpack"
    if unpack_tmp.exists():
        shutil.rmtree(unpack_tmp)
    unpack_tmp.mkdir(parents=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        tf.extractall(unpack_tmp)
    shutil.move(str(unpack_tmp / "python"), str(env_dir))
    shutil.rmtree(unpack_tmp, ignore_errors=True)

    py_bin = env_dir / "bin" / "python3"
    print(f"[pip] Installing bundled wheels into standalone Python 3.13...")
    subprocess.run(
        [str(py_bin), "-I", "-m", "pip", "install", "--no-cache-dir", "--disable-pip-version-check", *BUNDLED_PACKAGES],
        check=True,
    )
    shutil.rmtree(env_dir / "share", ignore_errors=True)
    shutil.rmtree(env_dir / "include", ignore_errors=True)
    marker.write_text("ok\n", encoding="utf-8")
    return env_dir


def stage_appdir() -> Path:
    rt_lib = PROJECT_ROOT / "build" / "libtotkrt_ps5.a"
    if not rt_lib.is_file():
        raise FileNotFoundError(f"Missing {rt_lib} — run python3 -m builder.cli --build-runtime-lib first")

    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    APPDIR.mkdir(parents=True)

    app_root = APPDIR / "usr" / "PS5TotkBuilder"
    bundle = app_root / "kit_bundle"
    bundle.mkdir(parents=True)

    # 1. Builder Python package
    copy_clean_tree(
        PROJECT_ROOT / "builder",
        app_root / "builder",
        ignore_fn=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )

    # 2. Prebuilt game-free PS5 runtime archive
    shutil.copy2(rt_lib, bundle / "libtotkrt_ps5.a")

    # 3. Lean PS5 kit (omit Longshot's OOT-specific .o files; keep app_crt.o + RADV + SDK + tools)
    ps5_kit_dst = bundle / "ps5-kit"
    ps5_kit_src = PROJECT_ROOT / "third_party" / "ps5-kit"
    copy_clean_tree(ps5_kit_src / "tools", ps5_kit_dst / "tools")
    for sub in ("lib", "link", "sdk"):
        copy_clean_tree(ps5_kit_src / "kit" / sub, ps5_kit_dst / "kit" / sub)
    obj_dst = ps5_kit_dst / "kit" / "obj"
    obj_dst.mkdir(parents=True)
    shutil.copy2(ps5_kit_src / "kit" / "obj" / "app_crt.o", obj_dst / "app_crt.o")
    for opus_obj in sorted((ps5_kit_src / "kit" / "obj").glob("opus_*.o")):
        shutil.copy2(opus_obj, obj_dst / opus_obj.name)
    (ps5_kit_dst / "kit" / "title" / "sce_module").mkdir(parents=True)
    shutil.copy2(
        ps5_kit_src / "kit" / "title" / "sce_module" / "libc.prx",
        ps5_kit_dst / "kit" / "title" / "sce_module" / "libc.prx",
    )
    shutil.copy2(ps5_kit_src / "kit" / "kit.json", ps5_kit_dst / "kit" / "kit.json")

    # 4. Compat headers, Vulkan headers, VMA, PS5 linker script, custom TOTK sce_sys
    copy_clean_tree(PROJECT_ROOT / "third_party" / "ps5_compat_inc", bundle / "ps5_compat_inc")
    copy_clean_tree(PROJECT_ROOT / "third_party" / "vma", bundle / "vma")
    # Dereference symlinks for Vulkan/zstd/opus headers so AppImage is 100% self-contained
    shutil.copytree(PROJECT_ROOT / "third_party" / "vk_headers", bundle / "vk_headers", symlinks=False)
    copy_clean_tree(PROJECT_ROOT / "assets" / "sce_sys", bundle / "sce_sys")
    (bundle / "ps5").mkdir(parents=True, exist_ok=True)
    shutil.copy2(PROJECT_ROOT / "ps5" / "ps5-totk.ld", bundle / "ps5" / "ps5-totk.ld")

    # 4b. Host Linux shader pre-translation tools (100% game-free: prep_mvprev + totk_xlate with mvprev patch 0015)
    xlate_dir = PROJECT_ROOT / "build" / "xlate_mvprev"
    if (xlate_dir / "prep_mvprev").is_file() and (xlate_dir / "totk_xlate").is_file():
        lt_dst = bundle / "linux-tools"
        lt_dst.mkdir(parents=True, exist_ok=True)
        for bname in ("prep_mvprev", "totk_xlate", "totk_xlate.id"):
            src_b = xlate_dir / bname
            if src_b.is_file():
                shutil.copy2(src_b, lt_dst / bname)

    # 5. TOTK lifter (recomp/), minimal tools/ (+ vendor/macnativegames + hactool for .xci/.nsp), and runtime headers
    totk_dst = bundle / "totk-src"
    copy_clean_tree(
        TOTK_SRC / "recomp",
        totk_dst / "recomp",
        ignore_fn=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    tools_dst = totk_dst / "tools"
    tools_dst.mkdir(parents=True)
    for tname in (
        "button_icons.py",
        "check_content.py",
        "extract.py",
        "hostmem.py",
        "make_romfs_patches.py",
        "ncz.py",
        "pack_shader_cache.py",
        "prepare_shaders.py",
        "romfs_index.py",
        "shader_census.py",
        "shader_list.py",
        "ultrawide_layout.py",
    ):
        src_t = TOTK_SRC / "tools" / tname
        if src_t.is_file():
            shutil.copy2(src_t, tools_dst / tname)
    if (TOTK_SRC / "tools" / "data").is_dir():
        copy_clean_tree(TOTK_SRC / "tools" / "data", tools_dst / "data")
    if (TOTK_SRC / "tools" / "vendor" / "macnativegames").is_dir():
        copy_clean_tree(
            TOTK_SRC / "tools" / "vendor" / "macnativegames",
            tools_dst / "vendor" / "macnativegames",
            ignore_fn=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
    hactool_bin = PROJECT_ROOT / "build" / "hactool" / "hactool"
    if hactool_bin.is_file():
        ht_dst = totk_dst / "toolchain" / "hactool"
        ht_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(hactool_bin, ht_dst / "hactool")

    rt_dst = totk_dst / "runtime"
    rt_dst.mkdir(parents=True)
    for p in (TOTK_SRC / "runtime").rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(TOTK_SRC / "runtime")
        if p.suffix in (".h", ".inc") or (len(rel.parts) == 1 and p.name in INSTALL_SIDE):
            dst_p = rt_dst / rel
            dst_p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst_p)

    # 6. Bundle standalone CPython 3.13 + PyQt6 + Pillow + capstone + lz4 + zstandard + numpy + fontTools
    standalone_py = _prepare_standalone_python()
    copy_clean_tree(
        standalone_py,
        app_root / "python",
        ignore_fn=shutil.ignore_patterns("__pycache__", "*.pyc", "tests", "test", ".totk_pkgs_ready_v1"),
    )

    # 7. Desktop entry, icon, and AppRun
    icon_src = PROJECT_ROOT / "assets" / "sce_sys" / "icon0.png"
    shutil.copy2(icon_src, APPDIR / "ps5-totk-builder.png")
    shutil.copy2(icon_src, APPDIR / ".DirIcon")

    (APPDIR / "ps5-totk-builder.desktop").write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=PS5 TOTK Builder\n"
        "Comment=Build Tears of the Kingdom for PlayStation 5 (PPSA99199)\n"
        "Exec=AppRun\n"
        "Icon=ps5-totk-builder\n"
        "Categories=Game;Utility;\n"
        "Terminal=false\n",
        encoding="utf-8",
    )

    apprun = APPDIR / "AppRun"
    apprun.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'HERE="$(dirname "$(readlink -f "$0")")"\n'
        'APP="$HERE/usr/PS5TotkBuilder"\n'
        'export PYTHONHOME="$APP/python"\n'
        'export PYTHONPATH="$APP"\n'
        "export PYTHONDONTWRITEBYTECODE=1\n"
        'if [ "$#" -eq 0 ]; then\n'
        '    exec "$APP/python/bin/python3" -s -P -m builder.gui\n'
        "else\n"
        '    exec "$APP/python/bin/python3" -s -P -m builder.cli "$@"\n'
        "fi\n",
        encoding="utf-8",
    )
    apprun.chmod(apprun.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"[ok] Staged AppDir at {APPDIR}")
    return APPDIR


def build_appimage() -> Path:
    stage_appdir()
    OUT_APPIMAGE.parent.mkdir(parents=True, exist_ok=True)
    if not APPIMAGETOOL.is_file():
        raise FileNotFoundError(f"appimagetool not found at {APPIMAGETOOL}")

    tmp_out = OUT_APPIMAGE.with_suffix(".AppImage.tmp")
    if tmp_out.exists():
        tmp_out.unlink()
    env = os.environ.copy()
    env["ARCH"] = "x86_64"
    cmd = [str(APPIMAGETOOL), "--no-appstream", str(APPDIR), str(tmp_out)]
    print(f"[run] {' '.join(cmd)}")
    subprocess.run(cmd, env=env, check=True)
    os.replace(tmp_out, OUT_APPIMAGE)
    size_mb = OUT_APPIMAGE.stat().st_size / (1024 * 1024)
    print(f"[ok] Built AppImage: {OUT_APPIMAGE} ({size_mb:.1f} MiB)")
    return OUT_APPIMAGE


if __name__ == "__main__":
    build_appimage()
