"""GameBanana API v11 browser & RomFS mod downloader for Tears of the Kingdom (Game ID 7617)."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass, field
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
    full_img_url: str = ""
    views: int = 0
    wip: bool = False
    summary: str = ""


@dataclass(frozen=True)
class GBFile:
    file_id: int
    filename: str
    size_bytes: int
    download_url: str
    description: str


@dataclass(frozen=True)
class GBModDetail:
    mod_id: int
    description: str
    gallery_urls: list[str] = field(default_factory=list)
    files: list[GBFile] = field(default_factory=list)
    views: int = 0
    likes: int = 0
    author: str = ""
    category: str = ""
    profile_url: str = ""


GB_CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("all", "Todos", "All"),
    ("gameplay", "Gameplay", "Gameplay"),
    ("skins", "Trajes & Modelos", "Skins & Models"),
    ("ui", "UI & HUD", "UI & HUD"),
    ("audio", "Audio", "Audio"),
    ("other", "Otros", "Other"),
)


def clean_html_text(raw_html: str) -> str:
    """Convert GameBanana HTML description text into readable plain text."""
    if not raw_html:
        return ""
    txt = re.sub(r"(?i)<br\s*/?>", "\n", raw_html)
    txt = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|blockquote)>", "\n", txt)
    txt = re.sub(r"(?i)<li[^>]*>", "• ", txt)
    txt = re.sub(r"<[^>]+>", "", txt)
    txt = html.unescape(txt)
    txt = txt.replace("\r\n", "\n").replace("\r", "\n")
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def match_category(mod: GBMod, cat_key: str) -> bool:
    """Match a GameBanana mod category against our filter key."""
    if not cat_key or cat_key == "all":
        return True
    c = (mod.category or "").lower()
    is_game = any(k in c for k in ("game", "tweaks", "quest", "overhaul", "map", "dungeon", "shrine"))
    is_model = any(k in c for k in ("skin", "model", "tex", "armor", "weapon", "character", "pack"))
    is_audio = any(k in c for k in ("sound", "audio", "music", "voice"))
    is_ui = any(k in c for k in ("gui", "ui", "hud", "menu", "icon"))
    if cat_key == "gameplay":
        return is_game
    if cat_key == "skins":
        return is_model
    if cat_key == "audio":
        return is_audio
    if cat_key == "ui":
        return is_ui
    if cat_key == "other":
        return not (is_game or is_model or is_audio or is_ui)
    return True


def fetch_image_bytes(url: str, timeout: int = 6) -> bytes | None:
    if not url:
        return None
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


def _http_json(url: str, timeout: int = 15) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _parse_images(rec: dict) -> tuple[str, str, list[str]]:
    imgs = (rec.get("_aPreviewMedia") or {}).get("_aImages") or []
    thumb = ""
    full = ""
    gallery: list[str] = []
    for idx, im in enumerate(imgs):
        if not isinstance(im, dict):
            continue
        base = str(im.get("_sBaseUrl") or "").rstrip("/")
        if not base:
            continue
        tfn = str(im.get("_sFile220") or im.get("_sFile100") or im.get("_sFile") or "").lstrip("/")
        ffn = str(im.get("_sFile530") or im.get("_sFile") or im.get("_sFile220") or "").lstrip("/")
        if idx == 0:
            if tfn:
                thumb = f"{base}/{tfn}"
            if ffn:
                full = f"{base}/{ffn}"
        if ffn and len(gallery) < 5:
            gallery.append(f"{base}/{ffn}")
    return thumb, full, gallery


def search_mods(query: str = "", page: int = 1, sort: str = "default", category: str = "all") -> list[GBMod]:
    """Search or browse Tears of the Kingdom mods on GameBanana (API v11)."""
    q_clean = query.strip()
    out: list[GBMod] = []
    seen: set[tuple[int, bool]] = set()
    pages_to_fetch = 2 if category != "all" else 1
    for p in range(max(1, page), max(1, page) + pages_to_fetch):
        if q_clean:
            params = [
                ("_sModelName", "Mod"),
                ("_idGameRow", str(TOTK_GAME_ID)),
                ("_sOrder", "best_match"),
                ("_nPage", str(p)),
                ("_sSearchString", q_clean),
            ]
            url = f"https://gamebanana.com/apiv11/Util/Search/Results?{urllib.parse.urlencode(params)}"
        else:
            params = [
                ("_nPage", str(p)),
                ("_sSort", sort),
                ("_csvModelInclusions", "Mod,Wip"),
            ]
            url = f"https://gamebanana.com/apiv11/Game/{TOTK_GAME_ID}/Subfeed?{urllib.parse.urlencode(params)}"
        data = _http_json(url)
        records = data.get("_aRecords") or []
        if not records:
            break
        for rec in records:
            g = rec.get("_aGame") or {}
            if g and g.get("_idRow") and int(g.get("_idRow")) != TOTK_GAME_ID:
                continue
            mod_id = int(rec.get("_idRow") or 0)
            if not mod_id:
                continue
            wip = rec.get("_sModelName") == "Wip"
            if (mod_id, wip) in seen:
                continue
            seen.add((mod_id, wip))
            name = str(rec.get("_sName") or f"Mod #{mod_id}")
            cat = str((rec.get("_aRootCategory") or {}).get("_sName") or "Mod")
            author = str((rec.get("_aSubmitter") or {}).get("_sName") or "Unknown")
            likes = int(rec.get("_nLikeCount") or 0)
            views = int(rec.get("_nViewCount") or 0)
            thumb, full, _ = _parse_images(rec)
            profile_url = str(rec.get("_sProfileUrl") or f"https://gamebanana.com/{'wips' if wip else 'mods'}/{mod_id}")
            summary = clean_html_text(str(rec.get("_sDescription") or rec.get("_sText") or ""))[:220]
            mod = GBMod(mod_id, name, cat, author, likes, thumb, profile_url, full, views, wip, summary)
            if match_category(mod, category):
                out.append(mod)
    return out


def fetch_mod_detail(mod_id: int, wip: bool = False) -> GBModDetail:
    """Fetch full description, preview gallery, and downloadable files for a GameBanana mod."""
    model = "Wip" if wip else "Mod"
    url = f"https://gamebanana.com/apiv11/{model}/{int(mod_id)}/ProfilePage"
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
    _, _, gallery = _parse_images(data)
    return GBModDetail(
        mod_id=int(mod_id),
        description=clean_html_text(str(data.get("_sText") or "")),
        gallery_urls=gallery,
        files=files,
        views=int(data.get("_nViewCount") or 0),
        likes=int(data.get("_nLikeCount") or 0),
        author=str((data.get("_aSubmitter") or {}).get("_sName") or ""),
        category=str((data.get("_aCategory") or data.get("_aRootCategory") or {}).get("_sName") or ""),
        profile_url=str(data.get("_sProfileUrl") or f"https://gamebanana.com/{'wips' if wip else 'mods'}/{mod_id}"),
    )


def fetch_mod_files(mod_id: int, wip: bool = False) -> list[GBFile]:
    """Fetch downloadable archive files for a specific GameBanana mod."""
    return fetch_mod_detail(mod_id, wip=wip).files


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
