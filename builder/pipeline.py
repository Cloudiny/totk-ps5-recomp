#!/usr/bin/env python3
"""PS5 TOTK Builder Pipeline — modeled after PS5LongshotPlusBuilder.

Supports:
  1. Building the reusable game-free PS5 runtime archive (`libtotkrt_ps5.a`).
  2. Building a full PS5 TOTK title (`PPSA99199/eboot.bin` + `sce_sys/` + `sce_module/`
     + `/data/totk-ps5/` data bundle with `romfs-index.bin`, `totk.ini`, and
     pre-translated shader cache) from either:
       - A single TOTK game file (`.xci` / `.nsp` / `.totk` + `prod.keys`), OR
       - An already extracted `--exefs` + `--romfs` directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .deploy import PS5_LAYOUT_TEXT

TITLE_ID = "PPSA99199"
CONTENT_ID = "UP9000-PPSA99199_00-PS5TOTKRECOMP001"
DEFAULT_PS5_XLATE_ID = "7f4216ce85b6de657221eda09f48870e00f71fb520e465b10182667918f8d9a2"

SKIP_RT_FILES = {
    "platform/linux.c",
    "gfx_window_sdl.c",
    "folder_pick_sdl.c",
    "input_sdl.c",
    "ui/menu_sdl.cpp",
}

INSTALL_SIDE = {
    "romfs.c",
    "patches.c",
    "ov_zstd.c",
    "mouse_direct.c",
    "ov_ability.c",
    "plugin_init.c",
    "freecam.c",
}

PS5_BACKEND_SOURCES = [
    "ps5/plat_ps5_mem.c",
    "ps5/platform_ps5.c",
    "ps5/gfx_window_ps5.c",
    "ps5/sdl3_ps5.c",
    "ps5/vpx_ps5.c",
    "ps5/folder_pick_ps5.c",
    "ps5/input_host_ps5.c",
    "ps5/vk_ps5_trampolines.c",
]

VERSION_MAP = {
    "1.0.0": ("v0", 100, None),
    "1.1.0": ("v110", 110, "patches-v110.txt"),
    "1.1.2": ("v112", 112, "patches-v110.txt"),
    "1.2.1": ("v121", 121, "patches-v121.txt"),
    "1.4.3": ("v143", 143, "patches-v143.txt"),
}


@dataclass
class KitPaths:
    project_root: Path
    kit_root: Path
    totk_src_root: Path
    ps5_src_root: Path
    compat_inc: Path
    vk_inc: Path
    vma_inc: Path
    assets_sce_sys: Path
    python_bin: Path

    @property
    def kit(self) -> Path:
        return self.kit_root / "kit"

    @property
    def tools(self) -> Path:
        return self.kit_root / "tools" / "bin"

    @property
    def clang(self) -> Path:
        return self.tools / "clang"

    @property
    def lld(self) -> Path:
        return self.tools / "ld.lld"

    @property
    def nm(self) -> Path:
        return self.tools / "llvm-nm"

    @property
    def native_tool(self) -> Path:
        return self.tools / "ps5-native-tool"

    @property
    def runtime_dir(self) -> Path:
        return self.totk_src_root / "runtime"

    @property
    def recomp_dir(self) -> Path:
        return self.totk_src_root / "recomp"

    @property
    def totk_tools_dir(self) -> Path:
        return self.totk_src_root / "tools"


def default_kit_paths(project_root: Path | None = None) -> KitPaths:
    root = (project_root or Path(__file__).resolve().parent.parent).resolve()
    appdir_kit = root / "kit_bundle"
    if appdir_kit.is_dir():
        return KitPaths(
            project_root=root,
            kit_root=appdir_kit / "ps5-kit",
            totk_src_root=appdir_kit / "totk-src",
            ps5_src_root=appdir_kit,
            compat_inc=appdir_kit / "ps5_compat_inc",
            vk_inc=appdir_kit / "vk_headers",
            vma_inc=appdir_kit / "vma",
            assets_sce_sys=appdir_kit / "sce_sys",
            python_bin=Path(sys.executable),
        )

    venv_py = root / ".venv" / "bin" / "python"
    return KitPaths(
        project_root=root,
        kit_root=root / "third_party" / "ps5-kit",
        totk_src_root=Path("/home/saul/Projects/totk-linux-native-recomp"),
        ps5_src_root=root,
        compat_inc=root / "third_party" / "ps5_compat_inc",
        vk_inc=root / "third_party" / "vk_headers",
        vma_inc=root / "third_party" / "vma",
        assets_sce_sys=root / "assets" / "sce_sys",
        python_bin=venv_py if venv_py.is_file() else Path(sys.executable),
    )


def run_cmd(cmd: list[str], what: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    print(f"[ps5-totk] {what}")
    res = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR during {what} (rc={res.returncode}):", file=sys.stderr)
        if res.stdout:
            print(res.stdout[-3000:], file=sys.stderr)
        if res.stderr:
            print(res.stderr[-3000:], file=sys.stderr)
        raise RuntimeError(f"{what} failed with exit code {res.returncode}")
    return res


def ninja_esc(p: Path) -> str:
    return p.as_posix().replace("$", "$$").replace(" ", "$ ").replace(":", "$:")


def cmd_quote(s: str) -> str:
    s = s.replace("$", "$$")
    return f'"{s}"' if " " in s else s


def write_rsp(path: Path, args: list[str]) -> str:
    path.write_text(
        "".join('"' + a.replace("\\", "/").replace('"', '\\"') + '"\n' for a in args),
        encoding="utf-8",
    )
    return f"@{path}"


def detect_totk_version(paths: KitPaths, exefs_dir: Path) -> tuple[str, int, Path | None, dict[str, str]]:
    """Identify TOTK version from exefs/main SHA-256 and return (ver_tag, ver_num, patches_txt, hashes)."""
    main_file = exefs_dir / "main"
    if not main_file.is_file():
        raise FileNotFoundError(f"Missing ExeFS main binary: {main_file}")

    actual_hashes: dict[str, str] = {}
    for name in ("main", "main.npdm", "sdk", "subsdk0"):
        f = exefs_dir / name
        if f.is_file():
            actual_hashes[name] = hashlib.sha256(f.read_bytes()).hexdigest()

    main_sha = actual_hashes["main"]
    data_dir = paths.totk_tools_dir / "data"
    for exp_json in sorted(data_dir.glob("expected-*.json")):
        d = json.loads(exp_json.read_text(encoding="utf-8"))
        if d.get("exefs_sha256", {}).get("main") == main_sha:
            disp = d.get("display_version", "1.4.3")
            ver_tag, ver_num, patch_name = VERSION_MAP.get(disp, ("v143", 143, "patches-v143.txt"))
            patch_path = (paths.recomp_dir / patch_name) if patch_name else None
            print(f"[ps5-totk] Detected TOTK v{disp} ({ver_tag}, main={main_sha[:12]}...)")
            return ver_tag, ver_num, patch_path, actual_hashes

    print(f"[ps5-totk] Unknown ExeFS hash {main_sha[:12]}..., defaulting to v143 layout")
    return "v143", 143, paths.recomp_dir / "patches-v143.txt", actual_hashes


def build_runtime_archive(paths: KitPaths, out_lib: Path, work_dir: Path) -> Path:
    """Archive all game-independent PS5 TOTK runtime objects into libtotkrt_ps5.a."""
    out_lib.parent.mkdir(parents=True, exist_ok=True)
    rt_obj_dir = paths.project_root / "build" / "probe_rt_obj"
    ps5_obj_dir = paths.project_root / "build" / "link_rt"

    if not rt_obj_dir.is_dir() or len(list(rt_obj_dir.rglob("*.o"))) < 120:
        raise RuntimeError("Missing compiled runtime objects in build/probe_rt_obj — run scripts/probe_runtime_compile.py first")

    objs: list[str] = []
    for p in sorted(rt_obj_dir.rglob("*.o")):
        rel_c = p.relative_to(rt_obj_dir).with_suffix(".c").as_posix()
        rel_cpp = p.relative_to(rt_obj_dir).with_suffix(".cpp").as_posix()
        if rel_c in SKIP_RT_FILES or rel_cpp in SKIP_RT_FILES:
            continue
        if p.with_suffix(".c").name in INSTALL_SIDE:
            continue
        objs.append(str(p))

    for src_rel in PS5_BACKEND_SOURCES:
        obj = ps5_obj_dir / f"{Path(src_rel).stem}.o"
        if not obj.is_file():
            raise RuntimeError(f"Missing PS5 backend object {obj} — run scripts/link_runtime_ps5.py first")
        objs.append(str(obj))

    objs.extend(sorted(str(p) for p in (paths.kit / "obj").glob("opus_*.o")))

    ar_bin = shutil.which("llvm-ar") or shutil.which("ar")
    if not ar_bin:
        raise RuntimeError("Neither llvm-ar nor ar found on PATH")
    if out_lib.exists():
        out_lib.unlink()

    rsp = work_dir / "ar_rt.rsp"
    work_dir.mkdir(parents=True, exist_ok=True)
    run_cmd([ar_bin, "rcs", str(out_lib), write_rsp(rsp, objs)], f"archive {out_lib.name} ({len(objs)} objects)")
    return out_lib


def write_romfs_config(paths: KitPaths, romfs_dir: Path | None, work_dir: Path) -> Path | None:
    """Generate exact romfs_config.h + romfs-index.bin from extracted RomFS index.json."""
    cfg_path = work_dir / "romfs_config.h"
    idx_out = work_dir / "romfs-index.bin"
    if romfs_dir and (romfs_dir / "index.json").is_file():
        sys.path.insert(0, str(paths.totk_tools_dir))
        import romfs_index  # type: ignore

        romfs_index.write(romfs_dir, work_dir)
        print(f"[ps5-totk] Generated romfs_config.h & romfs-index.bin from {romfs_dir}")
        return idx_out

    cfg_path.write_text(
        "#pragma once\n"
        "#define ROMFS_MISSING 1\n"
        "#define ROMFS_IMAGE_SIZE 0ull\n"
        '#define ROMFS_IMAGE_SHA256 ""\n'
        '#define ROMFS_INDEX_SHA256 ""\n'
        "#define ROMFS_FILE_COUNT 0ull\n",
        encoding="utf-8",
    )
    return None


def write_modules_c(
    gen_dir: Path,
    hashes: dict[str, str],
    ver_num: int,
    out_c: Path,
) -> list[str]:
    layout_data = json.loads((gen_dir / "layout.json").read_text(encoding="utf-8"))
    mods = [(m["name"], int(m["base"], 16), int(m["size"], 16)) for m in layout_data]
    mod_names = [m[0] for m in mods]

    lines = [
        "// Generated by builder/pipeline.py for PS5 TOTK (PPSA99199)",
        '#include "dispatch.h"',
        '#include "host.h"',
        '#include "layout.h"',
        "",
    ]
    for name, base, size in mods:
        u = name.upper()
        lines.append(
            f'_Static_assert(MOD_{u}_BASE == {base:#x}ull && MOD_{u}_SIZE == {size:#x}ull, '
            f'"layout mismatch for {name}");'
        )
    lines += ["", "const RtLayoutEntry rt_layout[] = {"]
    for name, _, _ in mods:
        lines.append(f'    {{"{name}", MOD_{name.upper()}_BASE, MOD_{name.upper()}_SIZE}},')
    lines += ["};", f"const int rt_layout_count = {len(mods)};", ""]

    for name in mod_names:
        lines += [
            f"extern const uint64_t {name}_fn_addrs[];",
            f"extern const GuestFn {name}_fn_ptrs[];",
            f"extern const uint64_t {name}_fn_count;",
        ]

    lines += ["", "int rt_linked_modules(RtModule *out, int max) {", "    int n = 0;"]
    for name in mod_names:
        u = name.upper()
        lines.append(
            f'    if (n < max) out[n++] = (RtModule){{"{name}", MOD_{u}_BASE, MOD_{u}_SIZE, '
            f"{name}_fn_addrs, {name}_fn_ptrs, {name}_fn_count}};"
        )
    lines += ["    return n;", "}", "", "const RtFileHash rt_exefs_sha256[] = {"]
    for fname, sha in sorted(hashes.items()):
        lines.append(f'    {{"{fname}", "{sha}"}},')
    lines += [
        "};",
        f"const int rt_exefs_sha256_count = {len(hashes)};",
        'const char rt_default_exefs[] = "/data/totk-ps5/exefs";',
        'const char rt_default_romfs[] = "/data/totk-ps5/romfs";',
        'const char rt_default_profile[] = "/data/totk-ps5/saves";',
        f"const int rt_game_version = {ver_num};",
        'const char rt_port_version[] = "0.1.0-ps5";',
        "",
    ]
    out_c.write_text("\n".join(lines), encoding="utf-8")
    return mod_names


def chunk_files(gen_dir: Path, mod: str) -> list[Path]:
    d = gen_dir / mod
    data = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    entries = data if isinstance(data, list) else data.get("chunks", data.get("files", []))
    names = [Path(e if isinstance(e, str) else e.get("file", e.get("path", e.get("name")))).name for e in entries]
    table = f"{mod}_table.c"
    if table not in names:
        names.append(table)
    return [d / n for n in names]


def _python_with_fonttools(paths: KitPaths) -> str:
    """Pick a Python interpreter that can import fontTools (for button_icons.py)."""
    candidates = [str(paths.python_bin), sys.executable, shutil.which("python3") or "python3"]
    for py in candidates:
        res = subprocess.run([py, "-c", "import fontTools"], capture_output=True)
        if res.returncode == 0:
            return py
    return str(paths.python_bin)


def generate_ps5_prompts(paths: KitPaths, ver_tag: str, romfs_dir: Path | None, data_out: Path) -> bool:
    """Generate PlayStation button prompt RomFS overlays (△ ○ × □) for both Nintendo & Xbox face layouts."""
    if not romfs_dir or not (romfs_dir / "romfs.bin").is_file():
        print("[ps5-totk] Skipping PlayStation prompts generation (romfs.bin not provided)")
        return False
    script = paths.totk_tools_dir / "make_romfs_patches.py"
    if not script.is_file():
        print(f"[ps5-totk] Skipping PlayStation prompts generation ({script} not found)")
        return False

    py = _python_with_fonttools(paths)
    ps_dir = data_out / "romfs-patches-playstation"
    ps_xbox_dir = data_out / "romfs-patches-playstation-xbox"

    if (ps_dir / "manifest.tsv").is_file() and (ps_xbox_dir / "manifest.tsv").is_file():
        print(f"[ps5-totk] Reusing existing PlayStation button prompts in {data_out}")
        return True

    print("[ps5-totk] Generating PlayStation button prompts (romfs-patches-playstation: ○=A, ×=B)...")
    run_cmd(
        [py, str(script), "--version", ver_tag, "--romfs", str(romfs_dir), "--prompts", "playstation", "--out", str(ps_dir)],
        "generate romfs-patches-playstation",
    )
    print("[ps5-totk] Generating PlayStation Xbox-layout prompts (romfs-patches-playstation-xbox: ×=A, ○=B)...")
    run_cmd(
        [
            py,
            str(script),
            "--version",
            ver_tag,
            "--romfs",
            str(romfs_dir),
            "--prompts",
            "playstation-xbox",
            "--reuse",
            str(ps_dir),
            "--out",
            str(ps_xbox_dir),
        ],
        "generate romfs-patches-playstation-xbox",
    )
    return True


def pretranslate_ps5_shaders(
    paths: KitPaths,
    ver_tag: str,
    romfs_dir: Path | None,
    data_out: Path,
    work_dir: Path,
    shader_src_dir: Path | None = None,
    jobs: int = 8,
) -> str:
    """Pre-translate & pack all RomFS shaders for PS5 RADV (TOTK_ZERO_LOCALS=0) or reuse existing pack."""
    xlate_id = DEFAULT_PS5_XLATE_ID
    sc_out = data_out / "shader-cache"
    sc_out.mkdir(parents=True, exist_ok=True)

    # Check if shader_src_dir already has a pre-built PS5 shader-cache.pack
    if shader_src_dir and shader_src_dir.is_dir():
        for cand in (shader_src_dir / "shader-cache" / "shader-cache.pack", shader_src_dir / "shader-cache.pack"):
            if cand.is_file():
                dst = sc_out / "shader-cache.pack"
                if dst.resolve() != cand.resolve():
                    shutil.copy2(cand, dst)
                print(f"[ps5-totk] Bundled PS5 shader-cache.pack ({cand.stat().st_size / (1024**2):.1f} MiB)")
                break
        id_file = shader_src_dir / "totk_xlate.id"
        if id_file.is_file():
            xlate_id = id_file.read_text(encoding="utf-8").strip() or xlate_id
            shutil.copy2(id_file, data_out / "totk_xlate.id")
        for fname in ("shader-prepared.bin", "shader-programs.bin", "shader-answers.bin"):
            src = shader_src_dir / fname
            if src.is_file():
                shutil.copy2(src, data_out / fname)
                print(f"[ps5-totk] Bundled shader file: {fname} ({src.stat().st_size / (1024**2):.2f} MiB)")

    if (sc_out / "shader-cache.pack").is_file() and (data_out / "shader-prepared.bin").is_file():
        return xlate_id

    # Otherwise, run full PC-side pre-translation targeting PS5 RADV (TOTK_ZERO_LOCALS=0)
    prep_py = paths.totk_tools_dir / "prepare_shaders.py"
    pack_py = paths.totk_tools_dir / "pack_shader_cache.py"
    linux_totk = None
    for cand in (
        paths.project_root / "kit_bundle" / "linux-tools" / "totk",
        Path("/home/saul/Games/Hyrule/TOTK/totk-runtime/totk"),
        paths.totk_tools_dir.parent / "build" / ver_tag / "totk",
    ):
        if cand.is_file():
            linux_totk = cand
            break

    if not romfs_dir or not prep_py.is_file() or not pack_py.is_file() or not linux_totk:
        print(
            "[ps5-totk] Note: full RomFS shader pre-translation skipped "
            "(provide --shaders dir with shader-cache.pack or Linux totk + totk_xlate binaries)."
        )
        return xlate_id

    stage_dir = work_dir / f"ps5_shaders_{ver_tag}"
    stage_dir.mkdir(parents=True, exist_ok=True)
    for bin_name in ("totk", "totk_xlate", "totk_xlate.id"):
        src_b = linux_totk.parent / bin_name
        if src_b.is_file():
            dst_b = stage_dir / bin_name
            if not dst_b.exists():
                shutil.copy2(src_b, dst_b)

    print(f"[ps5-totk] Preparing RomFS shader inventory ({ver_tag}) -> {stage_dir}...")
    run_cmd(
        [str(paths.python_bin), str(prep_py), str(stage_dir), "--version", ver_tag, "--romfs", str(romfs_dir), "--no-run"],
        "prepare_shaders.py (--no-run)",
    )

    env = os.environ.copy()
    env["TOTK_ZERO_LOCALS"] = "0"
    env["TOTK_XLATE_PROCS"] = str(max(1, min(jobs, 8)))
    print("[ps5-totk] Translating shaders for PS5 RADV (TOTK_ZERO_LOCALS=0)...")
    res = subprocess.run([str(stage_dir / "totk"), "--prepare-shaders"], cwd=str(stage_dir), env=env)
    if res.returncode != 0:
        raise RuntimeError(f"totk --prepare-shaders failed with exit code {res.returncode}")

    print("[ps5-totk] Packing shader-cache.pack for PS5...")
    run_cmd(
        [str(paths.python_bin), str(pack_py), str(stage_dir / "shader-cache"), str(sc_out / "shader-cache.pack")],
        "pack_shader_cache.py",
    )
    for fname in ("shader-prepared.bin", "totk_xlate.id"):
        src = stage_dir / fname
        if src.is_file():
            shutil.copy2(src, data_out / fname)
    if (data_out / "totk_xlate.id").is_file():
        xlate_id = (data_out / "totk_xlate.id").read_text(encoding="utf-8").strip() or xlate_id
    return xlate_id


def stage_ps5_mods(mod_sources: list[Path] | None, data_out: Path) -> list[str]:
    """Stage user RomFS mod folders or .zip archives into data_out/mods/<mod_name>/."""
    if not mod_sources:
        return []
    mods_root = data_out / "mods"
    mods_root.mkdir(parents=True, exist_ok=True)
    staged: list[str] = []

    for src in mod_sources:
        if not src.exists():
            print(f"[ps5-totk] WARNING: mod path not found, skipping: {src}")
            continue
        mod_name = src.stem if src.is_file() else src.name
        dst = mods_root / mod_name
        if dst.exists():
            shutil.rmtree(dst)
        if src.is_file() and src.suffix.lower() == ".zip":
            tmp_dir = mods_root / f".extract_{mod_name}"
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
            tmp_dir.mkdir(parents=True)
            with zipfile.ZipFile(src, "r") as zf:
                zf.extractall(tmp_dir)
            children = [c for c in tmp_dir.iterdir() if c.name != "__MACOSX"]
            if len(children) == 1 and children[0].is_dir():
                shutil.move(str(children[0]), str(dst))
                shutil.rmtree(tmp_dir, ignore_errors=True)
            else:
                shutil.move(str(tmp_dir), str(dst))
            staged.append(mod_name)
            print(f"[ps5-totk] Staged ZIP mod: {mod_name} -> {dst}")
        elif src.is_dir():
            shutil.copytree(src, dst)
            staged.append(mod_name)
            print(f"[ps5-totk] Staged folder mod: {mod_name} -> {dst}")
    return staged


def write_ps5_totk_ini(
    data_out: Path,
    *,
    xlate_id: str = DEFAULT_PS5_XLATE_ID,
    output_res: str = "2560x1440",
    render_scale: str = "100",
    lang: str = "es-419",
    pad_layout: str = "nintendo",
    prompts: str = "playstation",
    replay_async: int = 1,
) -> Path:
    ini_path = data_out / "totk.ini"
    ini_path.write_text(
        "# PS5 Tears of the Kingdom configuration (/data/totk-ps5/totk.ini)\n"
        "TOTK_FULLSCREEN=1\n"
        "TOTK_ASSUME_FOCUS=1\n"
        "TOTK_ROMFS_VERIFY=off\n"
        "TOTK_ASYNC_PREEMPT=0\n"
        "TOTK_ZERO_LOCALS=0\n"
        f"TOTK_XLATE_ID={xlate_id}\n"
        "TOTK_MODS_DIR=/data/totk-ps5/mods\n"
        "\n"
        "[display]\n"
        "perf_overlay = fps\n"
        f"window_size = {output_res}\n"
        f"output_res = {output_res}\n"
        f"render_scale = {render_scale}\n"
        "upscaler = fsr\n"
        "sharpness = 40\n"
        "\n"
        "[frame rate]\n"
        "frame_gen = off\n"
        "\n"
        "[input]\n"
        f"pad_layout = {pad_layout}\n"
        f"prompts = {prompts}\n"
        "\n"
        "[language]\n"
        f"lang = {lang}\n"
        "\n"
        "[performance]\n"
        f"replay_async = {replay_async}\n",
        encoding="utf-8",
    )
    return ini_path


def build_full_ps5_game(
    paths: KitPaths,
    exefs_dir: Path,
    romfs_dir: Path | None,
    gen_dir: Path,
    work_dir: Path,
    out_root: Path,
    runtime_lib: Path,
    shader_src_dir: Path | None = None,
    jobs: int = 8,
    skip_lift: bool = False,
    build_prompts: bool = True,
    pretranslate_shaders: bool = False,
    mods: list[Path] | None = None,
    output_res: str = "2560x1440",
    render_scale: str = "100",
    lang: str = "es-419",
) -> Path:
    t0 = time.time()
    work_dir.mkdir(parents=True, exist_ok=True)
    title_out = out_root / TITLE_ID
    data_out = out_root / "data_totk_ps5"
    title_out.mkdir(parents=True, exist_ok=True)
    data_out.mkdir(parents=True, exist_ok=True)

    ver_tag, ver_num, patch_txt, hashes = detect_totk_version(paths, exefs_dir)

    # Step 1: Lift ExeFS if not already lifted
    if not skip_lift or not (gen_dir / "layout.json").is_file():
        lift_cmd = [
            str(paths.python_bin),
            "-u",
            str(paths.recomp_dir / "gen.py"),
            "--exefs",
            str(exefs_dir),
            "--out",
            str(gen_dir),
            "--jobs",
            str(jobs),
        ]
        if patch_txt and patch_txt.is_file():
            lift_cmd += ["--patches", str(patch_txt)]
        run_cmd(lift_cmd, f"lift ExeFS ({ver_tag}) -> {gen_dir}")

    # Step 2: Generate romfs_config.h + romfs-index.bin + modules.c
    idx_bin = write_romfs_config(paths, romfs_dir, work_dir)
    modules_c = work_dir / "modules.c"
    mod_names = write_modules_c(gen_dir, hashes, ver_num, modules_c)

    # Step 3: Write Ninja build for all lifted chunks + install-side runtime sources + modules.c
    info = json.loads((paths.kit / "kit.json").read_text(encoding="utf-8"))
    place = lambda s: s.replace("{kit}", str(paths.kit))
    target_flags = [place(f) for f in info["target_flags"]]

    common_flags = target_flags + [
        "-march=znver2",
        "-fno-strict-aliasing",
        "-DRT_CPU_LEVEL=3",
        "-Dpreserve_most=noinline",
        "-Dvk_sync_finish=totk_vk_sync_finish",
        "-ffunction-sections",
        "-fdata-sections",
        "-I",
        str(paths.compat_inc),
        "-I",
        str(paths.runtime_dir),
        "-I",
        str(gen_dir),
        "-I",
        str(work_dir),
        "-I",
        str(paths.vma_inc),
        "-isystem",
        str(paths.vk_inc),
    ]

    gen_flags = common_flags + [
        "-O1",
        "-g0",
        "-Wno-everything",
        "-fvisibility=hidden",
        "-mllvm",
        "-rotation-max-header-size=0",
        "-mllvm",
        "-capture-tracking-max-uses-to-explore=5000",
    ]
    rt_flags = common_flags + ["-O2", "-Wno-unused-function", "-Wno-unused-variable"]

    ninja_lines = [
        "ninja_required_version = 1.10",
        f"cc = {cmd_quote(paths.clang.as_posix())}",
        f"genflags = {' '.join(cmd_quote(f) for f in gen_flags)}",
        f"rtflags = {' '.join(cmd_quote(f) for f in rt_flags)}",
        "",
        "pool gen",
        f"  depth = {max(1, jobs)}",
        "",
        "rule cc_gen",
        "  command = $cc $genflags -MD -MF $out.d -c $in -o $out",
        "  deps = gcc",
        "  depfile = $out.d",
        "  description = CC_GEN $out",
        "",
        "rule cc_rt",
        "  command = $cc $rtflags -MD -MF $out.d -c $in -o $out",
        "  deps = gcc",
        "  depfile = $out.d",
        "  description = CC_RT $out",
        "",
    ]

    compiled_objs: list[Path] = []
    obj_root = work_dir / "obj"

    for mod in mod_names:
        for src in chunk_files(gen_dir, mod):
            obj = obj_root / mod / f"{src.stem}.o"
            obj.parent.mkdir(parents=True, exist_ok=True)
            compiled_objs.append(obj)
            ninja_lines += [
                f"build {ninja_esc(obj)}: cc_gen {ninja_esc(src)}",
                "  pool = gen",
            ]

    install_srcs = [paths.runtime_dir / name for name in sorted(INSTALL_SIDE)] + [modules_c]
    for src in install_srcs:
        obj = obj_root / "install" / f"{src.stem}.o"
        obj.parent.mkdir(parents=True, exist_ok=True)
        compiled_objs.append(obj)
        ninja_lines.append(f"build {ninja_esc(obj)}: cc_rt {ninja_esc(src)}")

    ninja_path = work_dir / "build.ninja"
    ninja_path.write_text("\n".join(ninja_lines) + "\n", encoding="utf-8")

    print(f"[ps5-totk] Compiling {len(compiled_objs)} PS5 objects with ninja -j {jobs}...")
    t_cc = time.time()
    res = subprocess.run(["ninja", "-f", str(ninja_path), "-j", str(jobs)])
    if res.returncode != 0:
        raise RuntimeError(f"ninja compile failed with exit code {res.returncode}")
    print(f"[ps5-totk] Compiled {len(compiled_objs)} objects in {time.time() - t_cc:.1f}s")

    # Step 4: Link with ld.lld against libtotkrt_ps5.a + RADV + PS5 SDK
    local_map = work_dir / "local.map"
    local_map.write_text("{\n    local:\n        fork;\n        isatty;\n};\n", encoding="utf-8")

    lk = info["link"]
    sdk_lib = paths.kit / "sdk" / "target" / "lib"
    stubs = [str(paths.kit / "lib" / "stubs" / n) for n in ("libSceAgc.so", "libSceAgcDriver.so")]
    elf = work_dir / "totk_ps5_pie.elf"
    link_map = work_dir / "totk_ps5.map"

    totk_ld = paths.ps5_src_root / "ps5" / "ps5-totk.ld"
    if not totk_ld.is_file():
        totk_ld = paths.project_root / "ps5" / "ps5-totk.ld"
    script_args = ["-T", str(totk_ld)] if totk_ld.is_file() else [place(a) for a in lk["script"]]

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
        + script_args
        + [place(a) for a in lk["flags"]]
        + [
            "--version-script",
            str(paths.kit / "link" / "native" / "app-symbols.map"),
            "--version-script",
            str(local_map),
            "--exclude-libs=ALL",
            "--gc-sections",
            "-e",
            "_start",
            f"-Map={link_map}",
            "-o",
            str(elf),
            str(paths.kit / "obj" / "app_crt.o"),
        ]
        + [str(o) for o in compiled_objs]
        + [
            "--whole-archive",
            str(runtime_lib),
            "--no-whole-archive",
            str(paths.kit / "lib" / "libzstd.a"),
            str(paths.kit / "lib" / "libavcodec.a"),
            str(paths.kit / "lib" / "libdav1d.a"),
            str(paths.kit / "lib" / "libavutil.a"),
        ]
        + stubs
        + [place(a) for a in lk["inputs"]]
        + ["--as-needed"]
        + sorted(str(sdk_lib / f) for f in os.listdir(sdk_lib) if f.endswith(".so"))
        + ["--hash-style=gnu"]
    )

    rsp = work_dir / "link.rsp"
    t_lk = time.time()
    run_cmd([str(paths.lld), write_rsp(rsp, link_args)], "ld.lld link full TOTK PS5 binary")

    exported = set((paths.kit / "link" / "exported.txt").read_text(encoding="utf-8").split())

    def undefined(kinds: tuple[str, ...]) -> list[str]:
        out = run_cmd([str(paths.nm), "-D", "--undefined-only", str(elf)], "inspect dynamic imports").stdout
        syms: set[str] = set()
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[0] in kinds:
                syms.add(parts[1].split("@")[0])
        return sorted(syms)

    weak_unexported = [s for s in undefined(("w", "v")) if s not in exported]
    if weak_unexported:
        run_cmd(
            [str(paths.lld), write_rsp(rsp, link_args + [f"--defsym={s}=0" for s in weak_unexported])],
            f"re-link resolving {len(weak_unexported)} unexported weak symbols",
        )

    unresolved = [s for s in undefined(("U",)) if s not in exported]
    if unresolved:
        raise RuntimeError(f"Unexported PS5 dynamic imports ({len(unresolved)}): {', '.join(unresolved[:20])}")

    print(f"[ps5-totk] Linked {elf.stat().st_size / (1024*1024):.1f} MiB ELF in {time.time() - t_lk:.1f}s")

    # Step 5: ps5-native-tool link + FSELF sign
    eboot_elf = work_dir / "eboot.elf.new"
    eboot_bin = title_out / "eboot.bin"
    run_cmd(
        [
            str(paths.native_tool),
            "link",
            "--in",
            str(elf),
            "--out",
            str(eboot_elf),
            "--stub-dir",
            str(sdk_lib),
            "--stub",
            str(paths.kit / "lib" / "stubs" / "libSceAgc.so"),
            "--stub",
            str(paths.kit / "lib" / "stubs" / "libSceAgcDriver.so"),
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
            str(paths.native_tool),
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
    insp = run_cmd([str(paths.native_tool), "self", "--inspect", "--file", str(eboot_bin)], "verify FSELF integrity")
    print(insp.stdout.strip())

    # Step 6: Package sce_sys (custom TOTK cover + icon + param.json) & sce_module/libc.prx
    sce_mod_out = title_out / "sce_module"
    sce_sys_out = title_out / "sce_sys"
    sce_mod_out.mkdir(parents=True, exist_ok=True)
    sce_sys_out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(paths.kit / "title" / "sce_module" / "libc.prx", sce_mod_out / "libc.prx")
    for fname in ("icon0.png", "pic0.dds", "pic1.dds", "param.json"):
        src = paths.assets_sce_sys / fname
        if src.is_file():
            shutil.copy2(src, sce_sys_out / fname)

    # Step 7: Stage /data/totk-ps5/ payload (romfs-index.bin, PS prompts, shaders, mods, PS5 totk.ini)
    if idx_bin and idx_bin.is_file():
        shutil.copy2(idx_bin, data_out / "romfs-index.bin")

    if build_prompts:
        generate_ps5_prompts(paths, ver_tag, romfs_dir, data_out)

    xlate_id = DEFAULT_PS5_XLATE_ID
    if pretranslate_shaders or (shader_src_dir and shader_src_dir.is_dir()):
        xlate_id = pretranslate_ps5_shaders(
            paths,
            ver_tag,
            romfs_dir,
            data_out,
            work_dir,
            shader_src_dir=shader_src_dir,
            jobs=jobs,
        )

    stage_ps5_mods(mods, data_out)

    write_ps5_totk_ini(
        data_out,
        xlate_id=xlate_id,
        output_res=output_res,
        render_scale=render_scale,
        lang=lang,
    )
    (out_root / "PS5_LAYOUT.txt").write_text(PS5_LAYOUT_TEXT, encoding="utf-8")

    print(
        f"[ok] BUILT FULL TOTK PS5 TITLE ({TITLE_ID}) in {time.time() - t0:.1f}s -> "
        f"{eboot_bin} ({eboot_bin.stat().st_size / (1024*1024):.2f} MiB)"
    )
    return eboot_bin
