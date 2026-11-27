"""MacNativeGames shader list downloader, seed builder, and PS5 shader cache repacker.

Downloads the MIT-licensed MacNativeGames shared shader variant list
(`games/totk/assets/shader_list.tsv` including git history of pruned `V` rows),
merges all matching non-default bind-state variants + `mvprev=1` VS copies into
`seed-answers.bin`, translates any missing variants for PS5 RADV
(`TOTK_ZERO_LOCALS=0`), and repacks `shader-cache.pack` + `shader-prepared.bin`.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Callable

MACNATIVEGAMES_REPO_URL = "https://github.com/ly05010419/MacNativeGames.git"
MACNATIVEGAMES_PINNED_COMMIT = "d1509b4b62211265fad5449cf53cc9f13484ecc5"
MACNATIVEGAMES_LIST_PATH = "games/totk/assets/shader_list.tsv"

TEX_KINDS = [
    None,
    "1d",
    "1darray",
    "buffer",
    "2d",
    "2darray",
    "2dms",
    "2dmsarray",
    "3d",
    "cube",
    "cubearray",
]
IMG_FORMATS = [
    None,
    "R8Unorm",
    "R8Snorm",
    "R8Uint",
    "R8Sint",
    "R16Float",
    "R16Unorm",
    "R16Snorm",
    "R16Uint",
    "R16Sint",
    "R32Float",
    "R32Uint",
    "R32Sint",
    "R8G8Unorm",
    "R8G8Snorm",
    "R8G8Uint",
    "R8G8Sint",
    "R16G16Float",
    "R16G16Unorm",
    "R16G16Snorm",
    "R16G16Uint",
    "R16G16Sint",
    "R32G32Float",
    "R32G32Uint",
    "R32G32Sint",
    "R8G8B8A8Unorm",
    "R8G8B8A8Snorm",
    "R8G8B8A8Uint",
    "R8G8B8A8Sint",
    "R16G16B16A16Float",
    "R16G16B16A16Unorm",
    "R16G16B16A16Snorm",
    "R16G16B16A16Uint",
    "R16G16B16A16Sint",
    "R32G32B32A32Float",
    "R32G32B32A32Uint",
    "R32G32B32A32Sint",
    "R10G10B10A2Unorm",
    "R10G10B10A2Uint",
    "R11G11B10Float",
]
IO_TYPES = {"float": 0, "sint": 1, "uint": 2}
DEFAULT_DEPS = {"tex": {str(slot): "2d" for slot in range(32)}}
CONTROL_SIZE = 0x880
ANS_REC_SIZE = 4 + 32 + 32 + 147 + 1


def default_cache_dir() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    return base / "ps5-totk-builder"


def default_shader_list_cache_path() -> Path:
    return default_cache_dir() / "shader_list.tsv"


def resolve_shader_list(paths, explicit_list: Path | None = None) -> Path | None:
    """Resolve the best available non-empty shader_list.tsv (explicit > user cache > bundled)."""
    candidates: list[Path] = []
    if explicit_list is not None:
        candidates.append(explicit_list)
    candidates.append(default_shader_list_cache_path())
    candidates.append(paths.totk_tools_dir / "data" / "shader_list.tsv")
    candidates.append(paths.totk_src_root / "data" / "shader_list.tsv")
    for cand in candidates:
        if cand.is_file() and cand.stat().st_size > 0:
            return cand
    return None


def inspect_shader_list(tsv_path: Path) -> dict[str, int]:
    """Return summary counts for a shader_list.tsv file."""
    if not tsv_path.is_file():
        return {"total_lines": 0, "v_rows": 0, "warm_prios": 0, "size_bytes": 0}
    txt = tsv_path.read_text(encoding="utf-8", errors="replace")
    variants, prio = parse_shader_list(txt)
    return {
        "total_lines": len(txt.splitlines()),
        "v_rows": len(variants),
        "warm_prios": len(prio),
        "size_bytes": tsv_path.stat().st_size,
    }


def _git_out(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout


def extract_shader_list_history_from_repo(repo_dir: Path, rev: str = "origin/HEAD") -> str:
    """Read rev's shader_list.tsv plus every V row pruned from older commits in git history."""
    if _git_out(repo_dir, "rev-parse", "--is-shallow-repository").strip() == "true":
        raise RuntimeError(
            f"{repo_dir} is a shallow clone without shader_list.tsv history; re-download with full history"
        )
    lines = _git_out(repo_dir, "show", f"{rev}:{MACNATIVEGAMES_LIST_PATH}").splitlines()
    seen = set(lines)
    commits = _git_out(repo_dir, "log", "--format=%H", rev, "--", MACNATIVEGAMES_LIST_PATH).split()
    for commit_hash in commits[1:]:
        for line in _git_out(repo_dir, "show", f"{commit_hash}:{MACNATIVEGAMES_LIST_PATH}").splitlines():
            if line.startswith("V\t") and line not in seen:
                seen.add(line)
                lines.append(line)
    return "\n".join(lines) + "\n"


def download_shader_list(
    dest_tsv: Path | None = None,
    *,
    repo_url: str = MACNATIVEGAMES_REPO_URL,
    commit: str = MACNATIVEGAMES_PINNED_COMMIT,
    work_repo_dir: Path | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[Path, dict[str, int]]:
    """Fetch MacNativeGames git history and materialize the combined shader_list.tsv."""
    log = log_fn or (lambda msg: print(msg, flush=True))
    if not shutil.which("git"):
        raise RuntimeError("git is required to download the MacNativeGames shader_list.tsv history")

    out_path = (dest_tsv or default_shader_list_cache_path()).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    repo_dir = (work_repo_dir or (default_cache_dir() / "MacNativeGames")).resolve()

    need_clone = True
    if (repo_dir / ".git").exists():
        try:
            cur_head = _git_out(repo_dir, "rev-parse", "HEAD").strip()
            cur_origin = _git_out(repo_dir, "rev-parse", "-q", "--verify", "refs/remotes/origin/HEAD").strip()
            is_shallow = _git_out(repo_dir, "rev-parse", "--is-shallow-repository").strip()
            if cur_head == commit and cur_origin == commit and is_shallow == "false":
                need_clone = False
                log(f"[shaders] MacNativeGames cache already at {commit[:12]}")
        except Exception:
            need_clone = True

    if need_clone:
        if repo_dir.exists():
            shutil.rmtree(repo_dir)
        repo_dir.mkdir(parents=True, exist_ok=True)
        log(f"[shaders] Downloading MacNativeGames shader list history ({commit[:12]})...")
        subprocess.run(["git", "-C", str(repo_dir), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "remote", "add", "origin", repo_url], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "fetch", "-q", "origin", commit], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "checkout", "-q", "FETCH_HEAD"], check=True)
        subprocess.run(["git", "-C", str(repo_dir), "update-ref", "refs/remotes/origin/HEAD", commit], check=True)

    log("[shaders] Extracting full shader_list.tsv variant history...")
    combined = extract_shader_list_history_from_repo(repo_dir, rev="origin/HEAD")
    tmp = out_path.with_suffix(".tsv.tmp")
    tmp.write_text(combined, encoding="utf-8")
    os.replace(tmp, out_path)

    stats = inspect_shader_list(out_path)
    log(
        f"[ok] Saved shader_list.tsv -> {out_path} "
        f"({stats['v_rows']:,} V variants, {stats['warm_prios']:,} warm priorities)"
    )
    return out_path, stats


def _pipeline_variants(key: str) -> list[str]:
    if ":" in key:
        return key.split(":", 2)[:2]
    try:
        return [n.decode("ascii", "replace") for n in bytes.fromhex(key).split(b"\0")[:2]]
    except ValueError:
        return []


def parse_shader_list(text: str) -> tuple[list[tuple[str, dict]], dict[str, int]]:
    """Parse MacNativeGames shader_list.tsv V rows and warm priority flags."""
    variants: list[tuple[str, dict]] = []
    prio: dict[str, int] = {}

    def warm(key: str, flags: str) -> None:
        p = 0 if "t" in flags else 1
        prio[key] = min(prio.get(key, 2), p)

    for line in text.splitlines():
        if not line:
            continue
        f = line.split("\t")
        tag = f[0]
        if tag == "V" and len(f) == 3:
            variants.append((f[1], json.loads(f[2])))
        elif tag == "S" and len(f) == 4:
            warm(f[1][:64], f[3])
        elif tag == "C" and len(f) == 3:
            warm(f[1][:64], f[2])
        elif tag in ("R", "B") and len(f) >= 3:
            for n in _pipeline_variants(f[1]):
                if len(n) >= 64:
                    warm(n[:64], f[-1])
    return variants, prio


def pack_shader_answers(deps: dict, stage: int, control: bytes) -> bytes:
    """Pack GfxShaderAnswers (147 bytes) matching runtime/gfx_shader.c pack_answers."""
    tex, img, fmt, attr, fout = bytearray(32), bytearray(32), bytearray(32), bytearray(32), bytearray(8)
    for slot, t in deps.get("tex", {}).items():
        t = str(t).removesuffix("_depth")
        tex[int(slot)] = TEX_KINDS.index("2d" if t == "*" else t)
    for slot, o in deps.get("img", {}).items():
        img[int(slot)] = TEX_KINDS.index(o["type"])
        fmt[int(slot)] = IMG_FORMATS.index(o["fmt"]) if o.get("fmt") in IMG_FORMATS else 0
    for loc, t in deps.get("attr", {}).items():
        attr[int(loc)] = IO_TYPES[t]
    for idx, t in deps.get("fout", {}).items():
        fout[int(idx)] = IO_TYPES[t]
    local = [0, 0, 0]
    if stage == 5:
        local = [v or 1 for v in struct.unpack_from("<III", control, 0x748)]
    packed = bytes(tex + img + fmt + attr + fout) + struct.pack("<HHHIB", *local, 0, 0)
    assert len(packed) == 147
    return packed


def build_seed_answers_from_programs(
    seed_programs_bin: Path,
    shader_list_tsv: Path,
    out_seed_answers_bin: Path,
    *,
    add_mvprev: bool = True,
) -> dict[str, int]:
    """Generate TOTKSANS v1 seed-answers.bin directly from TOTKSPRG v1 + shader_list.tsv."""
    raw = seed_programs_bin.read_bytes()
    magic, ver, _ = struct.unpack_from("<8sII", raw, 0)
    if magic != b"TOTKSPRG" or ver != 1:
        raise ValueError(f"Invalid seed-programs.bin header in {seed_programs_bin}: {magic!r} v{ver}")

    off = 16
    progs: dict[str, tuple[int, bytes, bytes]] = {}
    while off < len(raw):
        stage_id, length, c1_len = struct.unpack_from("<III", raw, off)
        off += 12
        h = raw[off : off + 32]
        off += 32
        control = raw[off : off + CONTROL_SIZE]
        off += CONTROL_SIZE
        code = raw[off : off + length]
        off += length
        off += c1_len
        key = hashlib.sha256(control + code).hexdigest()
        progs[key] = (stage_id, h, control)

    variants, prio = parse_shader_list(shader_list_tsv.read_text(encoding="utf-8", errors="replace"))
    matched_v = 0
    for key, _ in variants:
        if key in progs:
            matched_v += 1

    all_variants = list(variants) + [(key, DEFAULT_DEPS) for key in sorted(progs)]
    recs: list[tuple[int, bytes]] = []
    seen: set[tuple[bytes, bytes]] = set()
    nd_tex = nd_attr = nd_fout = 0

    for key, deps in all_variants:
        prog = progs.get(key)
        if not prog:
            continue
        stage_id, h, control = prog
        packed = pack_shader_answers(deps, stage_id, control)
        if (h, packed) in seen:
            continue
        seen.add((h, packed))
        if any(b not in (0, 4) for b in packed[0:32]):
            nd_tex += 1
        if any(b != 0 for b in packed[96:128]):
            nd_attr += 1
        if any(b != 0 for b in packed[128:136]):
            nd_fout += 1
        pr = prio.get(key, 2)
        rec = struct.pack("<I", stage_id) + h + bytes(32) + packed + bytes([pr])
        assert len(rec) == ANS_REC_SIZE
        recs.append((pr, rec))

    recs.sort(key=lambda r: r[0])

    mv_recs: list[bytes] = []
    if add_mvprev:
        for _pr, rec in recs:
            if struct.unpack_from("<I", rec, 0)[0] == 0:
                mv = bytearray(rec)
                mv[68 + 146] |= 0x80
                mv[36:68] = b"\x00" * 32
                mv[ANS_REC_SIZE - 1] = 2
                mv_key = (bytes(mv[4:36]), bytes(mv[68 : 68 + 147]))
                if mv_key not in seen:
                    seen.add(mv_key)
                    mv_recs.append(bytes(mv))

    out_buf = bytearray(b"TOTKSANS" + struct.pack("<II", 1, ANS_REC_SIZE))
    for _pr, rec in recs:
        out_buf.extend(rec)
    for mv in mv_recs:
        out_buf.extend(mv)

    out_seed_answers_bin.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_seed_answers_bin.with_suffix(".bin.tmp")
    tmp.write_bytes(bytes(out_buf))
    os.replace(tmp, out_seed_answers_bin)

    return {
        "programs": len(progs),
        "matched_v_rows": matched_v,
        "base_and_list": len(recs),
        "mvprev_vs": len(mv_recs),
        "total_records": len(recs) + len(mv_recs),
        "non_default_tex": nd_tex,
        "non_default_attr": nd_attr,
        "non_default_fout": nd_fout,
    }


def _find_seed_programs(
    paths,
    *,
    stage_dir: Path,
    out_data_dir: Path,
    shader_src_dir: Path | None,
    ver_tag: str,
) -> Path | None:
    candidates = [
        stage_dir / "seed-programs.bin",
        out_data_dir / "seed-programs.bin",
        paths.project_root / "build" / f"ps5_shaders_{ver_tag}" / "seed-programs.bin",
    ]
    if shader_src_dir is not None:
        candidates.insert(0, shader_src_dir / "seed-programs.bin")
    for cand in candidates:
        if cand.is_file() and cand.stat().st_size > 16:
            return cand
    return None


def update_and_repack_ps5_shaders(
    paths,
    *,
    stage_dir: Path,
    out_data_dir: Path,
    shader_list_tsv: Path | None = None,
    shader_src_dir: Path | None = None,
    romfs_dir: Path | None = None,
    ver_tag: str = "v143",
    jobs: int = 8,
    download_list: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, object]:
    """Download/resolve shader_list.tsv, pre-translate missing PS5 RADV + mvprev variants, and repack."""
    from .pipeline import DEFAULT_PS5_XLATE_ID, prepare_thread_count

    log = log_fn or (lambda msg: print(msg, flush=True))

    tsv_path: Path | None = None
    if download_list:
        tsv_path, list_stats = download_shader_list(dest_tsv=shader_list_tsv, log_fn=log)
    else:
        tsv_path = resolve_shader_list(paths, explicit_list=shader_list_tsv)
        if not tsv_path:
            tsv_path, list_stats = download_shader_list(log_fn=log)
        else:
            list_stats = inspect_shader_list(tsv_path)

    prep_mvprev = None
    totk_xlate = None
    for d in (
        paths.project_root / "kit_bundle" / "linux-tools",
        paths.project_root / "build" / "xlate_mvprev",
    ):
        if (d / "prep_mvprev").is_file() and (d / "totk_xlate").is_file():
            prep_mvprev = d / "prep_mvprev"
            totk_xlate = d / "totk_xlate"
            break

    pack_py = paths.totk_tools_dir / "pack_shader_cache.py"
    prep_py = paths.totk_tools_dir / "prepare_shaders.py"
    if not prep_mvprev or not totk_xlate or not pack_py.is_file():
        raise FileNotFoundError(
            "Missing bundled shader translator tools (prep_mvprev, totk_xlate, or pack_shader_cache.py)"
        )

    stage_dir.mkdir(parents=True, exist_ok=True)
    stage_cache = stage_dir / "shader-cache"
    stage_cache.mkdir(parents=True, exist_ok=True)
    out_data_dir.mkdir(parents=True, exist_ok=True)
    out_cache = out_data_dir / "shader-cache"
    out_cache.mkdir(parents=True, exist_ok=True)

    # Preserve existing packed cache so incremental translation hits all already-translated shaders
    stage_pack = stage_cache / "shader-cache.pack"
    if not stage_pack.is_file():
        for existing_pack in (
            (shader_src_dir / "shader-cache" / "shader-cache.pack") if shader_src_dir else None,
            (shader_src_dir / "shader-cache.pack") if shader_src_dir else None,
            out_cache / "shader-cache.pack",
            paths.project_root / "build" / f"ps5_shaders_{ver_tag}" / "shader-cache" / "shader-cache.pack",
        ):
            if existing_pack and existing_pack.is_file():
                log(f"[shaders] Reusing existing pack ({existing_pack.stat().st_size / (1024**2):.1f} MiB) -> {stage_pack}")
                shutil.copy2(existing_pack, stage_pack)
                break

    # Preserve existing totk_xlate.id so cache keys match the PS5 install
    xlate_id = DEFAULT_PS5_XLATE_ID
    for id_cand in (
        out_data_dir / "totk_xlate.id",
        stage_dir / "totk_xlate.id",
        (shader_src_dir / "totk_xlate.id") if shader_src_dir else None,
        prep_mvprev.parent / "totk_xlate.id",
    ):
        if id_cand and id_cand.is_file():
            val = id_cand.read_text(encoding="utf-8").strip()
            if val:
                xlate_id = val
                break

    seed_programs = _find_seed_programs(
        paths,
        stage_dir=stage_dir,
        out_data_dir=out_data_dir,
        shader_src_dir=shader_src_dir,
        ver_tag=ver_tag,
    )

    if seed_programs is not None:
        if seed_programs.resolve() != (stage_dir / "seed-programs.bin").resolve():
            shutil.copy2(seed_programs, stage_dir / "seed-programs.bin")
        seed_stats = build_seed_answers_from_programs(
            stage_dir / "seed-programs.bin",
            tsv_path,
            stage_dir / "seed-answers.bin",
            add_mvprev=True,
        )
        log(
            f"[shaders] Built seed-answers.bin: {seed_stats['total_records']:,} variants "
            f"(tex={seed_stats['non_default_tex']:,}, attr={seed_stats['non_default_attr']:,}, "
            f"fout={seed_stats['non_default_fout']:,}, mvprev={seed_stats['mvprev_vs']:,})"
        )
    elif romfs_dir and romfs_dir.is_dir() and prep_py.is_file():
        log(f"[shaders] Extracting shader inventory from RomFS ({romfs_dir}) with {tsv_path.name}...")
        subprocess.run(
            [
                str(paths.python_bin),
                str(prep_py),
                str(stage_dir),
                "--version",
                ver_tag,
                "--romfs",
                str(romfs_dir),
                "--list",
                str(tsv_path),
                "--no-run",
            ],
            check=True,
        )
        seed_stats = build_seed_answers_from_programs(
            stage_dir / "seed-programs.bin",
            tsv_path,
            stage_dir / "seed-answers.bin",
            add_mvprev=True,
        )
    else:
        raise FileNotFoundError(
            "No se encontró seed-programs.bin ni carpeta --romfs. "
            "Selecciona tu RomFS extraído (o carpeta de caché previo con seed-programs.bin) para pre-traducir."
        )

    env = os.environ.copy()
    env["TOTK_ZERO_LOCALS"] = "0"
    prep_override_raw = env.get("PS5_PREPARE_THREADS") or env.get("TOTK_PREPARE_THREADS") or ""
    prep_override = int(prep_override_raw) if prep_override_raw.isdigit() else 0
    prep_threads = prepare_thread_count(os.cpu_count() or jobs, asked=prep_override)
    xlate_procs = max(1, min(jobs, prep_threads, 10))
    env["TOTK_XLATE_PROCS"] = str(xlate_procs)
    env["TOTK_PREPARE_THREADS"] = str(prep_threads)
    env["TOTK_XLATE"] = str(totk_xlate)
    env["TOTK_SHADER_CACHE"] = str(stage_cache)
    env["TOTK_XLATE_ID"] = xlate_id

    log(
        f"[shaders] Translating missing PS5 RADV + mvprev variants "
        f"(xlate_id={xlate_id[:16]}, threads={prep_threads}, procs={xlate_procs})..."
    )
    res = subprocess.run(
        [str(prep_mvprev), str(stage_dir), str(max(2, min(prep_threads, 12))), str(xlate_procs)],
        cwd=str(stage_dir),
        env=env,
    )
    if res.returncode != 0:
        raise RuntimeError(f"prep_mvprev failed with exit code {res.returncode}")

    log("[shaders] Repacking shader-cache.pack...")
    subprocess.run([str(paths.python_bin), str(pack_py), str(stage_cache)], check=True)

    dst_pack = out_cache / "shader-cache.pack"
    if stage_pack.is_file() and stage_pack.resolve() != dst_pack.resolve():
        shutil.copy2(stage_pack, dst_pack)
    stage_prep = stage_dir / "shader-prepared.bin"
    dst_prep = out_data_dir / "shader-prepared.bin"
    if stage_prep.is_file() and stage_prep.resolve() != dst_prep.resolve():
        shutil.copy2(stage_prep, dst_prep)
    (out_data_dir / "totk_xlate.id").write_text(xlate_id + "\n", encoding="utf-8")

    pack_size_mb = dst_pack.stat().st_size / (1024 * 1024) if dst_pack.is_file() else 0.0
    log(f"[ok] Repacked PS5 shader cache -> {dst_pack} ({pack_size_mb:.1f} MiB)")
    return {
        "tsv_path": tsv_path,
        "list_stats": list_stats,
        "seed_stats": seed_stats,
        "pack_path": dst_pack,
        "prepared_path": dst_prep,
        "xlate_id": xlate_id,
    }
