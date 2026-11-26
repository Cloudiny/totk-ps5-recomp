"""GameBanana API v11 browser & RomFS mod downloader for Tears of the Kingdom (Game ID 7617)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

TOTK_GAME_ID = 7617
USER_AGENT = "PS5TotkBuilder/0.1 (+https://github.com/)"

# Standard TOTK RomFS top-level folders to auto-detect inside mod archives
ROMFS_ROOT_MARKERS = {
    "actor",
    "ai",
    "banc",
    "bsa",
    "component",
    "effect",
    "event",
    "font",
    "gamedata",
    "layout",
    "mals",
    "model",
    "movie",
    "pack",
    "physics",
    "rsdb",
    "scene",
    "shader",
    "sound",
    "system",
    "textogo",
    "ui",
    "worldmgr",
}


@dataclass(frozen=True)
class GBMod:
    mod_id: int
    name: str
    category: str
    author: str
    likes: int
    thumb_url: str
    profile_url: str


@dataclass(frozen=True)
class GBFile:
    file_id: int
    filename: str
    size_bytes: int
    download_url: str
    description: str


def _http_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def search_mods(query: str = "", page: int = 1, sort: str = "default") -> list[GBMod]:
    """Search or browse Tears of the Kingdom mods on GameBanana (API v11)."""
    params: list[tuple[str, str]] = [
        ("_nPage", str(max(1, page))),
        ("_sSort", sort),
        ("_aModelNames[]", "Mod"),
    ]
    if query.strip():
        params.append(("_sName", query.strip()))
    url = f"https://gamebanana.com/apiv11/Game/{TOTK_GAME_ID}/Subfeed?{urllib.parse.urlencode(params)}"
    data = _http_json(url)
    out: list[GBMod] = []
    for rec in data.get("_aRecords") or []:
        mod_id = int(rec.get("_idRow") or 0)
        if not mod_id:
            continue
        name = str(rec.get("_sName") or f"Mod #{mod_id}")
        cat = str((rec.get("_aRootCategory") or {}).get("_sName") or "Mod")
        author = str((rec.get("_aSubmitter") or {}).get("_sName") or "Unknown")
        likes = int(rec.get("_nLikeCount") or 0)
        thumb = ""
        imgs = (rec.get("_aPreviewMedia") or {}).get("_aImages") or []
        if imgs and isinstance(imgs[0], dict):
            base = str(imgs[0].get("_sBaseUrl") or "")
            f220 = str(imgs[0].get("_sFile220") or imgs[0].get("_sFile") or "")
            if base and f220:
                thumb = f"{base}/{f220}"
        profile_url = str(rec.get("_sProfileUrl") or f"https://gamebanana.com/mods/{mod_id}")
        out.append(GBMod(mod_id, name, cat, author, likes, thumb, profile_url))
    return out


def fetch_mod_files(mod_id: int) -> list[GBFile]:
    """Fetch downloadable archive files for a specific GameBanana mod."""
    url = f"https://gamebanana.com/apiv11/Mod/{int(mod_id)}/ProfilePage"
    data = _http_json(url)
    files: list[GBFile] = []
    for f in data.get("_aFiles") or []:
        dl = str(f.get("_sDownloadUrl") or "")
        if not dl:
            continue
        files.append(
            GBFile(
                file_id=int(f.get("_idRow") or 0),
                filename=str(f.get("_sFile") or f"mod_{mod_id}.zip"),
                size_bytes=int(f.get("_nFilesize") or 0),
                download_url=dl,
                description=str(f.get("_sDescription") or ""),
            )
        )
    return files


def _slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("_")
    return (slug[:48] or "totk_mod").lower()


def _find_romfs_root(extracted: Path) -> Path | None:
    """Locate the romfs/ directory (or direct TOTK RomFS subfolder root) inside an extracted mod."""
    # Direct romfs/ folder anywhere in top 3 levels
    candidates = sorted(
        (p for p in extracted.rglob("*") if p.is_dir() and p.name.lower() == "romfs"),
        key=lambda p: len(p.parts),
    )
    if candidates:
        return candidates[0]
    # Otherwise check if extracted root or a single child folder directly contains RomFS markers
    search_dirs = [extracted] + [p for p in extracted.iterdir() if p.is_dir()]
    for d in search_dirs:
        child_names = {c.name.lower() for c in d.iterdir() if c.is_dir()}
        if child_names & ROMFS_ROOT_MARKERS:
            return d
    return None


def _extract_archive(archive: Path, dst: Path) -> None:
    low = archive.name.lower()
    if low.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(dst)
        return
    # Optional fallback for .7z / .rar if system 7z or bsdtar is available
    for tool, args in (
        ("7z", ["x", "-y", f"-o{dst}", str(archive)]),
        ("bsdtar", ["-xf", str(archive), "-C", str(dst)]),
    ):
        exe = shutil.which(tool)
        if exe:
            subprocess.run([exe, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            return
    raise RuntimeError(
        f"Unsupported archive '{archive.name}'. Only .zip is built-in (install 7z or bsdtar for .7z/.rar)."
    )


def download_and_stage_mod(
    gb_file: GBFile,
    mod_name: str,
    mods_root: Path,
    log_fn: Callable[[str], None] | None = None,
) -> tuple[Path, list[str]]:
    """Download a GameBanana mod archive, validate its RomFS payload, and stage into mods_root/<slug>/romfs/.

    Returns (staged_mod_dir, warnings).
    """
    log = log_fn or (lambda _m: None)
    mods_root.mkdir(parents=True, exist_ok=True)
    slug = _slugify(mod_name)
    warnings: list[str] = []

    with tempfile.TemporaryDirectory(prefix="totk_gb_") as td:
        tmp = Path(td)
        archive = tmp / gb_file.filename
        log(f"[gb] Downloading {gb_file.filename} ({gb_file.size_bytes / (1024 * 1024):.2f} MiB)...")
        req = urllib.request.Request(gb_file.download_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp, archive.open("wb") as out_f:
            shutil.copyfileobj(resp, out_f, length=262144)

        extracted = tmp / "extracted"
        extracted.mkdir()
        log(f"[gb] Extracting {gb_file.filename}...")
        _extract_archive(archive, extracted)

        # Compatibility scan
        all_files = [p for p in extracted.rglob("*") if p.is_file()]
        has_reshade = any(p.suffix.lower() in (".fx", ".fxh") or "reshade" in p.name.lower() for p in all_files)
        has_shader_bin = any(p.suffix.lower() in (".bfsha", ".bnsh") or p.name.endswith(".bfsha.zs") for p in all_files)
        has_pchtxt = any(p.suffix.lower() == ".pchtxt" for p in all_files)
        if has_reshade:
            warnings.append("Contains PC ReShade files (.fx/.ini) which do not run on PS5.")
        if has_shader_bin:
            warnings.append(
                "Mod includes Switch shader archives (.bfsha/.bnsh): PS5 has no runtime shader translator, so new shaders must be pre-translated on PC."
            )
        if has_pchtxt:
            warnings.append("Contains Switch ExeFS .pchtxt patches (RomFS overlay only applies RomFS assets).")

        romfs_src = _find_romfs_root(extracted)
        if romfs_src is None:
            raise RuntimeError(
                "No valid TOTK RomFS folder found inside archive (e.g. romfs/, UI/, Actor/, Pack/, Model/). "
                "PC-only ReShade presets or ExeFS-only mods cannot be injected as RomFS mods."
            )

        dst_mod = mods_root / slug
        dst_romfs = dst_mod / "romfs"
        if dst_mod.exists():
            shutil.rmtree(dst_mod)
        shutil.copytree(romfs_src, dst_romfs)
        nfiles = sum(1 for p in dst_romfs.rglob("*") if p.is_file())
        log(f"[ok] Staged GameBanana mod '{mod_name}' ({nfiles} RomFS files) -> {dst_mod}")
        return dst_mod, warnings


def download_ps5_icon_from_url(url: str, dest_png: Path) -> Path:
    """Download an image URL and convert it to a clean 512x512 RGBA PS5 icon0.png."""
    req = urllib.request.Request(url.strip(), headers={"User-Agent": USER_AGENT})
    with tempfile.NamedTemporaryFile(suffix=".img", delete=False) as tf:
        tmp_path = Path(tf.name)
        with urllib.request.urlopen(req, timeout=20) as resp:
            shutil.copyfileobj(resp, tf)
    try:
        from PIL import Image  # type: ignore

        im = Image.open(tmp_path).convert("RGBA").resize((512, 512), Image.Resampling.LANCZOS)
        dest_png.parent.mkdir(parents=True, exist_ok=True)
        im.save(dest_png, format="PNG")
    finally:
        tmp_path.unlink(missing_ok=True)
    return dest_png
