"""PS5 Tears of the Kingdom Builder — Premium Bilingual (ES/EN) Obsidian & Zonai UI (PPSA99199)."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .deploy import PS5_LAYOUT_TEXT, PS5Deployer
from .gamebanana import GBFile, GBMod, download_and_stage_mod, download_ps5_icon_from_url, fetch_mod_files, search_mods
from .pipeline import TITLE_ID, default_kit_paths

# ---- Obsidian x PlayStation x Zonai Emerald & Hylian Gold Design Tokens ----
C_BG = "#090C12"          # Deep PS5 obsidian canvas
C_SIDEBAR = "#0E131D"     # Elevated sidebar
C_CARD = "#131A26"        # Card surface
C_CARD_ALT = "#192334"    # Button / interactive surface
C_BORDER = "#223047"      # Crisp hairline border
C_INPUT = "#0B1018"       # Dark input well
C_TERM = "#06090F"        # Console terminal

C_ACCENT = "#2EE6A6"      # Zonai Emerald (Triangle / primary CTA)
C_ACCENT_HOV = "#4BF2B8"
C_ACCENT_TXT = "#061610"
C_GOLD = "#E6C36A"        # Hylian Gold
C_BLUE = "#38BDF8"        # PS5 Blue (Cross / secondary CTA)
C_BLUE_HOV = "#60CCF9"
C_CORAL = "#FB7185"       # PS Circle coral-red
C_VIOLET = "#C084FC"      # PS Square violet
C_DANGER = "#F87171"

C_TEXT = "#F1F5F9"
C_MUTED = "#94A3B8"
C_DIM = "#64748B"


# ---- Full ES / EN Localization Dictionary ----
I18N: dict[str, dict[str, str]] = {
    "es": {
        "win_title": f"PS5 TOTK Builder — Tears of the Kingdom ({TITLE_ID})",
        "nav_build_t": "Compilar & Shaders",
        "nav_build_s": "ExeFS, RomFS, -O3 Zen 2 y RADV",
        "nav_mods_t": "Mods & GameBanana",
        "nav_mods_s": "Buscador e inyección RomFS",
        "nav_ftp_t": "Enviar a PS5",
        "nav_ftp_s": "Despliegue seguro por FTP",
        "nav_layout_t": "Layout & Arte PS5",
        "nav_layout_s": "Rutas y portada personalizada",
        "status_ready": "●  Listo para compilar",
        "status_sub": "PS5 RADV · -O3 Zen 2 · 120 Hz\n1080p/1440p · 38 Trofeos",
        "p_build_h": "Compilar & Pre-traducir Shaders",
        "p_build_s": "Genera eboot.bin (-O3 Zen 2), íconos PlayStation y caché RADV + mvprev desde tu copia legal del juego.",
        "c_src_t": "Origen del Juego",
        "c_src_s": "Usa .xci/.nsp + prod.keys o carpetas extraídas",
        "lbl_game": "Juego base (.xci / .nsp)",
        "lbl_update": "Update (.nsp opcional)",
        "lbl_keys": "Switch prod.keys",
        "lbl_exefs": "O ExeFS extraído",
        "lbl_romfs": "O RomFS extraído",
        "lbl_shaders": "Caché shaders (opcional)",
        "lbl_out": "Carpeta de salida",
        "btn_browse": "Examinar",
        "c_opt_t": "Perfil PS5",
        "c_opt_s": "Valores verificados para 1080p/1440p @ 120 Hz (FSR 3.1.5 opcional)",
        "chk_prompts": "Íconos PlayStation por defecto (△ ○ × □, ○=A)",
        "chk_shaders": "Pre-traducir Shaders PS5 RADV + mvprev",
        "lbl_res": "Resolución",
        "lbl_hz": "Refresco (Hz)",
        "lbl_fg": "Frame Gen",
        "lbl_scale": "Escala 3D",
        "lbl_lang": "Idioma Juego",
        "p_mods_h": "Mods RomFS & Buscador GameBanana",
        "p_mods_s": "Busca mods en GameBanana (ID 7617), descárgalos en 1 clic o añade carpetas/.zip locales para /data/totk-ps5/mods/.",
        "c_gb_t": "Buscador GameBanana (Tears of the Kingdom)",
        "c_gb_s": "Modelos, trajes, HUD, gameplay y texturas RomFS",
        "btn_search": "Buscar",
        "btn_gb_dl": "⬇  Descargar e Inyectar",
        "btn_gb_ftp": "▲  Subir Mods a PS5",
        "gb_note": "Nota PS5: mods RomFS (trajes, UI, mapas, gameplay) funcionan directo. Presets ReShade de PC no corren en PS5 y mods con nuevos shaders .bfsha requieren pre-traducción en PC.",
        "c_queue_t": "Mods Locales / Descargados en Cola",
        "c_queue_s": "Se copian a /data/totk-ps5/mods/ y se gestionan en Touchpad + Options",
        "btn_add_dir": "+ Carpeta",
        "btn_add_zip": "+ Archivo .zip",
        "btn_rm_mod": "Quitar",
        "p_ftp_h": "Despliegue Directo a PS5 (FTP)",
        "p_ftp_s": "Solo escribe en /data/homebrew/PPSA99199 y /data/totk-ps5. Nunca toca otros juegos ni tus partidas.",
        "c_ftp_t": "Conexión ftpsrv",
        "c_ftp_s": "Abre ftpsrv en tu PS5 e ingresa su IP local",
        "lbl_ip": "IP de la PS5",
        "lbl_port": "Puerto",
        "chk_ftp_sh": "Subir shader-cache.pack (caché RADV + mvprev pre-traducido)",
        "chk_ftp_ini": "Subir / actualizar /data/totk-ps5/totk.ini",
        "chk_ftp_romfs": "Subir también romfs.bin (~15.86 GiB; solo en primera instalación)",
        "p_lay_h": "Layout PS5 & Arte de Portada",
        "p_lay_s": "El AppImage ya incluye portada oficial personalizada (icon0.png + 4K pic0/pic1.dds). Opcionalmente descarga otra portada desde URL.",
        "c_art_t": "Portada PS5 Personalizada (Opcional)",
        "c_art_s": "icon0.png, pic0.dds y pic1.dds ya vienen embebidos en el AppImage",
        "lbl_art_url": "URL de imagen (PNG/JPG)",
        "btn_art_dl": "Descargar icon0.png",
        "btn_check": "Verificar Kit",
        "btn_ftp_only": "Solo Subir FTP",
        "btn_build": "▶  Compilar TOTK PS5",
        "btn_both": "⚡  Compilar + Enviar a PS5",
        "err_no_game_t": "Faltan archivos",
        "err_no_game_m": "Selecciona un juego base (.xci/.nsp) o una carpeta ExeFS extraída.",
        "err_no_keys_t": "Falta prod.keys",
        "err_no_keys_m": "Para extraer archivos .xci/.nsp necesitas seleccionar tu Switch prod.keys.",
        "err_no_ip_t": "Falta IP de PS5",
        "err_no_ip_m": "Ingresa la IP local de tu PS5 en 'Enviar a PS5'.",
        "welcome": f"[ps5-totk] PS5 TOTK Builder listo ({TITLE_ID}). Selecciona tu juego y presiona Compilar.\n",
        "pick_file_t": "Seleccionar archivo del mod",
        "pick_file_h": "Elige qué archivo descargar de GameBanana:",
        "btn_cancel": "Cancelar",
        "btn_download": "Descargar",
    },
    "en": {
        "win_title": f"PS5 TOTK Builder — Tears of the Kingdom ({TITLE_ID})",
        "nav_build_t": "Build & Shaders",
        "nav_build_s": "ExeFS, RomFS, -O3 Zen 2 & RADV",
        "nav_mods_t": "Mods & GameBanana",
        "nav_mods_s": "Browser & RomFS injector",
        "nav_ftp_t": "Deploy to PS5",
        "nav_ftp_s": "Safe FTP transfer",
        "nav_layout_t": "PS5 Layout & Art",
        "nav_layout_s": "Paths & custom cover art",
        "status_ready": "●  Ready to build",
        "status_sub": "PS5 RADV · -O3 Zen 2 · 120 Hz\n1080p/1440p · 38 Trophies",
        "p_build_h": "Build & Pre-Translate Shaders",
        "p_build_s": "Builds eboot.bin (-O3 Zen 2), PlayStation prompts & RADV + mvprev shader pack from your legal game dump.",
        "c_src_t": "Game Source",
        "c_src_s": "Use .xci/.nsp + prod.keys or extracted folders",
        "lbl_game": "Base game (.xci / .nsp)",
        "lbl_update": "Update (.nsp optional)",
        "lbl_keys": "Switch prod.keys",
        "lbl_exefs": "Or extracted ExeFS",
        "lbl_romfs": "Or extracted RomFS",
        "lbl_shaders": "Shader cache (optional)",
        "lbl_out": "Output folder",
        "btn_browse": "Browse",
        "c_opt_t": "PS5 Profile",
        "c_opt_s": "Verified defaults for 1080p/1440p @ 120 Hz (optional FSR 3.1.5)",
        "chk_prompts": "Default PlayStation prompts (△ ○ × □, ○=A)",
        "chk_shaders": "Pre-translate PS5 RADV + mvprev shaders",
        "lbl_res": "Resolution",
        "lbl_hz": "Refresh (Hz)",
        "lbl_fg": "Frame Gen",
        "lbl_scale": "3D Scale",
        "lbl_lang": "Game Lang",
        "p_mods_h": "RomFS Mods & GameBanana Browser",
        "p_mods_s": "Browse GameBanana (Game ID 7617), 1-click download & inject, or add local folders/.zip to /data/totk-ps5/mods/.",
        "c_gb_t": "GameBanana Browser (Tears of the Kingdom)",
        "c_gb_s": "Models, outfits, HUD, gameplay & RomFS textures",
        "btn_search": "Search",
        "btn_gb_dl": "⬇  Download & Inject",
        "btn_gb_ftp": "▲  Push Mods to PS5",
        "gb_note": "PS5 note: RomFS mods (outfits, UI, models, gameplay) work out of the box. PC ReShade presets do not run on PS5, and mods adding new .bfsha shaders require PC pre-translation.",
        "c_queue_t": "Staged Local / Downloaded Mods",
        "c_queue_s": "Installed to /data/totk-ps5/mods/ and toggleable in Touchpad + Options",
        "btn_add_dir": "+ Folder",
        "btn_add_zip": "+ .zip File",
        "btn_rm_mod": "Remove",
        "p_ftp_h": "Direct PS5 Deployment (FTP)",
        "p_ftp_s": "Only writes inside /data/homebrew/PPSA99199 and /data/totk-ps5. Never touches other titles or existing saves.",
        "c_ftp_t": "ftpsrv Connection",
        "c_ftp_s": "Start ftpsrv on your PS5 and enter its local IP",
        "lbl_ip": "PS5 IP Address",
        "lbl_port": "Port",
        "chk_ftp_sh": "Upload shader-cache.pack (pre-translated RADV + mvprev)",
        "chk_ftp_ini": "Upload / overwrite /data/totk-ps5/totk.ini",
        "chk_ftp_romfs": "Also upload romfs.bin (~15.86 GiB; first-time install only)",
        "p_lay_h": "PS5 Layout & Cover Artwork",
        "p_lay_s": "Custom TOTK PS5 artwork (icon0.png + 4K pic0/pic1.dds) is already embedded in the AppImage. Optionally fetch custom art from a URL.",
        "c_art_t": "Custom PS5 Cover Art (Optional)",
        "c_art_s": "icon0.png, pic0.dds & pic1.dds are already embedded by default",
        "lbl_art_url": "Image URL (PNG/JPG)",
        "btn_art_dl": "Fetch icon0.png",
        "btn_check": "Verify Kit",
        "btn_ftp_only": "FTP Upload Only",
        "btn_build": "▶  Build TOTK PS5",
        "btn_both": "⚡  Build + Deploy to PS5",
        "err_no_game_t": "Missing game files",
        "err_no_game_m": "Select a base game (.xci/.nsp) or an extracted ExeFS folder.",
        "err_no_keys_t": "Missing prod.keys",
        "err_no_keys_m": "Switch prod.keys is required to extract .xci/.nsp game files.",
        "err_no_ip_t": "Missing PS5 IP",
        "err_no_ip_m": "Enter your PS5 local IP in 'Deploy to PS5'.",
        "welcome": f"[ps5-totk] PS5 TOTK Builder ready ({TITLE_ID}). Pick your game dump and click Build.\n",
        "pick_file_t": "Select mod archive",
        "pick_file_h": "Choose which GameBanana file to download:",
        "btn_cancel": "Cancel",
        "btn_download": "Download",
    },
}


def _pick_font(root: tk.Tk) -> str:
    try:
        from tkinter import font as tkfont

        fams = set(tkfont.families(root))
        for cand in ("Inter", "Segoe UI", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans"):
            if cand in fams:
                return cand
    except Exception:
        pass
    return "Sans"


def _load_logo(icon_path: Path, size: int = 52) -> tk.PhotoImage | None:
    if not icon_path.is_file():
        return None
    try:
        from PIL import Image, ImageDraw, ImageTk  # type: ignore

        im = Image.open(icon_path).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=12, fill=255)
        im.putalpha(mask)
        return ImageTk.PhotoImage(im)  # type: ignore[return-value]
    except Exception:
        try:
            img = tk.PhotoImage(file=str(icon_path))
            factor = max(1, img.width() // size)
            return img.subsample(factor, factor) if factor > 1 else img
        except Exception:
            return None


def _draw_ps_symbol(canvas: tk.Canvas, shape: str, color: str, bg: str) -> None:
    """Crisp vector PlayStation symbol (triangle / circle / cross / square) on a 24x24 canvas."""
    canvas.configure(bg=bg)
    canvas.delete("all")
    w = 2.2
    if shape == "triangle":
        canvas.create_polygon(12, 4, 20, 19, 4, 19, outline=color, fill="", width=w, joinstyle="round")
    elif shape == "circle":
        canvas.create_oval(4.5, 4.5, 19.5, 19.5, outline=color, width=w)
    elif shape == "cross":
        canvas.create_line(5.5, 5.5, 18.5, 18.5, fill=color, width=w, capstyle="round")
        canvas.create_line(18.5, 5.5, 5.5, 18.5, fill=color, width=w, capstyle="round")
    elif shape == "square":
        canvas.create_rectangle(5, 5, 19, 19, outline=color, width=w)


class ModernButton(tk.Frame):
    """Flat, sleek button with hover highlight, focus feel, and dynamic label update."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        bg: str = C_CARD_ALT,
        hover_bg: str = "#24324A",
        fg: str = C_TEXT,
        border: str = C_BORDER,
        font_spec=("Sans", 9, "bold"),
        padx: int = 14,
        pady: int = 7,
    ) -> None:
        super().__init__(parent, bg=border, padx=1, pady=1, cursor="hand2")
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._cmd = command
        self._enabled = True

        self._inner = tk.Label(
            self, text=text, bg=bg, fg=fg, font=font_spec, padx=padx, pady=pady, cursor="hand2"
        )
        self._inner.pack(fill="both", expand=True)
        for w in (self, self._inner):
            w.bind("<Enter>", lambda _e: self._enabled and self._inner.configure(bg=self._hover_bg))
            w.bind("<Leave>", lambda _e: self._enabled and self._inner.configure(bg=self._bg))
            w.bind("<ButtonRelease-1>", lambda _e: self._enabled and self._cmd and self._cmd())

    def set_text(self, text: str) -> None:
        self._inner.configure(text=text)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self._inner.configure(
            bg=self._bg if enabled else "#111722",
            fg=self._fg if enabled else C_DIM,
            cursor="hand2" if enabled else "arrow",
        )
        self.configure(cursor="hand2" if enabled else "arrow")


def run_gui() -> int:
    paths = default_kit_paths()

    root = tk.Tk()
    root.geometry("1160x790")
    root.minsize(1020, 700)
    root.configure(bg=C_BG)

    ui_font = _pick_font(root)
    mono_font = "JetBrains Mono" if ui_font == "Inter" else "Monospace"

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(
        "Dark.TCombobox",
        fieldbackground=C_INPUT,
        background=C_CARD_ALT,
        foreground=C_TEXT,
        arrowcolor=C_ACCENT,
        bordercolor=C_BORDER,
        lightcolor=C_BORDER,
        darkcolor=C_BORDER,
        padding=(8, 5),
    )
    style.map(
        "Dark.TCombobox",
        fieldbackground=[("readonly", C_INPUT), ("focus", "#101826")],
        foreground=[("readonly", C_TEXT)],
        bordercolor=[("focus", C_ACCENT)],
    )
    style.configure(
        "Zonai.Horizontal.TProgressbar",
        troughcolor=C_INPUT,
        background=C_ACCENT,
        bordercolor=C_BG,
        lightcolor=C_ACCENT,
        darkcolor=C_ACCENT,
        thickness=4,
    )
    root.option_add("*TCombobox*Listbox.background", C_CARD)
    root.option_add("*TCombobox*Listbox.foreground", C_TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", C_ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", C_ACCENT_TXT)

    # ---- Localization Registry ----
    lang_code = ["es"]
    i18n_bindings: list[tuple[object, str, str]] = []  # (widget, key, mode)

    def tr(key: str) -> str:
        return I18N[lang_code[0]].get(key, key)

    def bind_tr(widget, key: str, mode: str = "text"):
        i18n_bindings.append((widget, key, mode))
        val = tr(key)
        if mode == "modern":
            widget.set_text(val)
        elif mode == "sub":
            widget.configure(text=f"  ·  {val}")
        else:
            widget.configure(text=val)
        return widget

    # ---- Shared State (ZERO hardcoded personal paths or IPs) ----
    vars_map: dict[str, tk.StringVar] = {
        "game": tk.StringVar(value=""),
        "update": tk.StringVar(value=""),
        "keys": tk.StringVar(value=""),
        "exefs": tk.StringVar(value=""),
        "romfs": tk.StringVar(value=""),
        "shaders": tk.StringVar(value=""),
        "out": tk.StringVar(value=str(Path.home() / "TOTK-PS5-Out")),
        "res": tk.StringVar(value="1920x1080"),
        "hz": tk.StringVar(value="120"),
        "frame_gen": tk.StringVar(value="off"),
        "scale": tk.StringVar(value="game"),
        "lang": tk.StringVar(value="es-419"),
        "ftp_host": tk.StringVar(value=""),
        "ftp_port": tk.StringVar(value="2121"),
        "gb_query": tk.StringVar(value=""),
        "gb_sort": tk.StringVar(value="default"),
        "art_url": tk.StringVar(value=""),
    }
    bool_map: dict[str, tk.BooleanVar] = {
        "prompts": tk.BooleanVar(value=True),
        "pretranslate_shaders": tk.BooleanVar(value=True),
        "ftp_romfs": tk.BooleanVar(value=False),
        "ftp_shaders": tk.BooleanVar(value=True),
        "ftp_ini": tk.BooleanVar(value=True),
    }

    # ---- Shell: Sidebar + Hairline + Main Workspace ----
    # Top 2px Zonai emerald-gold accent stripe
    top_bar = tk.Frame(root, bg=C_ACCENT, height=2)
    top_bar.pack(fill="x")

    shell = tk.Frame(root, bg=C_BG)
    shell.pack(fill="both", expand=True)

    sidebar = tk.Frame(shell, bg=C_SIDEBAR, width=254)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    tk.Frame(shell, bg=C_BORDER, width=1).pack(side="left", fill="y")

    main_col = tk.Frame(shell, bg=C_BG)
    main_col.pack(side="left", fill="both", expand=True)

    # ---- Sidebar Brand + ES/EN Pill Switcher ----
    brand = tk.Frame(sidebar, bg=C_SIDEBAR, padx=18, pady=18)
    brand.pack(fill="x")

    logo_img = _load_logo(paths.assets_sce_sys / "icon0.png", size=50)
    logo_lbl = tk.Label(brand, bg=C_SIDEBAR)
    if logo_img is not None:
        logo_lbl.configure(image=logo_img)
        logo_lbl.image = logo_img  # type: ignore[attr-defined]
        logo_lbl.pack(side="left", padx=(0, 12))

    brand_txt = tk.Frame(brand, bg=C_SIDEBAR)
    brand_txt.pack(side="left", fill="x", expand=True)
    tk.Label(brand_txt, text="TOTK PS5", bg=C_SIDEBAR, fg=C_TEXT, font=(ui_font, 14, "bold"), anchor="w").pack(fill="x")
    tk.Label(
        brand_txt, text=f"{TITLE_ID}  ·  PRO", bg=C_SIDEBAR, fg=C_GOLD, font=(ui_font, 8, "bold"), anchor="w"
    ).pack(fill="x", pady=(2, 0))

    # Sleek ES | EN language switcher pill
    lang_bar = tk.Frame(sidebar, bg=C_SIDEBAR, padx=16, pady=4)
    lang_bar.pack(fill="x")
    pill = tk.Frame(lang_bar, bg=C_BORDER, padx=1, pady=1)
    pill.pack(fill="x")
    pill_in = tk.Frame(pill, bg=C_INPUT)
    pill_in.pack(fill="x")
    btn_es = tk.Label(pill_in, text="Español (ES)", font=(ui_font, 8, "bold"), pady=5, cursor="hand2")
    btn_en = tk.Label(pill_in, text="English (EN)", font=(ui_font, 8, "bold"), pady=5, cursor="hand2")
    btn_es.pack(side="left", fill="x", expand=True)
    btn_en.pack(side="left", fill="x", expand=True)

    def apply_language(code: str) -> None:
        lang_code[0] = code
        root.title(tr("win_title"))
        btn_es.configure(
            bg=C_ACCENT if code == "es" else C_INPUT,
            fg=C_ACCENT_TXT if code == "es" else C_MUTED,
        )
        btn_en.configure(
            bg=C_ACCENT if code == "en" else C_INPUT,
            fg=C_ACCENT_TXT if code == "en" else C_MUTED,
        )
        for w, key, mode in i18n_bindings:
            val = tr(key)
            if mode == "modern":
                w.set_text(val)  # type: ignore[attr-defined]
            elif mode == "sub":
                w.configure(text=f"  ·  {val}")  # type: ignore[attr-defined]
            else:
                w.configure(text=val)  # type: ignore[attr-defined]

    btn_es.bind("<ButtonRelease-1>", lambda _e: apply_language("es"))
    btn_en.bind("<ButtonRelease-1>", lambda _e: apply_language("en"))

    tk.Frame(sidebar, bg=C_BORDER, height=1).pack(fill="x", padx=16, pady=(12, 12))

    # ---- Sidebar PlayStation Navigation (△ ○ × □) ----
    nav_specs = [
        ("build", "triangle", C_ACCENT, "nav_build_t", "nav_build_s"),
        ("mods", "circle", C_CORAL, "nav_mods_t", "nav_mods_s"),
        ("ftp", "cross", C_BLUE, "nav_ftp_t", "nav_ftp_s"),
        ("layout", "square", C_VIOLET, "nav_layout_t", "nav_layout_s"),
    ]
    nav_nodes: dict[str, dict] = {}
    pages: dict[str, tk.Frame] = {}

    def select_page(key: str) -> None:
        for k, p in pages.items():
            if k == key:
                p.pack(fill="both", expand=True)
            else:
                p.pack_forget()
        for k, n in nav_nodes.items():
            active = k == key
            bg_c = "#172235" if active else C_SIDEBAR
            n["row"].configure(bg=bg_c)
            n["bar"].configure(bg=n["color"] if active else bg_c)
            n["inner"].configure(bg=bg_c)
            n["txts"].configure(bg=bg_c)
            n["tl"].configure(bg=bg_c, fg=C_TEXT if active else C_MUTED)
            n["sl"].configure(bg=bg_c, fg=C_MUTED if active else C_DIM)
            _draw_ps_symbol(n["cv"], n["shape"], n["color"] if active else C_DIM, bg_c)

    for key, shape, color, tk_key, sk_key in nav_specs:
        row = tk.Frame(sidebar, bg=C_SIDEBAR, cursor="hand2")
        row.pack(fill="x", padx=10, pady=3)
        bar = tk.Frame(row, bg=C_SIDEBAR, width=3)
        bar.pack(side="left", fill="y", pady=5)
        inner = tk.Frame(row, bg=C_SIDEBAR, padx=10, pady=9)
        inner.pack(side="left", fill="both", expand=True)
        cv = tk.Canvas(inner, width=24, height=24, bg=C_SIDEBAR, highlightthickness=0, cursor="hand2")
        cv.pack(side="left", padx=(0, 10))
        txts = tk.Frame(inner, bg=C_SIDEBAR)
        txts.pack(side="left", fill="x", expand=True)
        tl = bind_tr(tk.Label(txts, bg=C_SIDEBAR, fg=C_MUTED, font=(ui_font, 10, "bold"), anchor="w"), tk_key)
        tl.pack(fill="x")
        sl = bind_tr(tk.Label(txts, bg=C_SIDEBAR, fg=C_DIM, font=(ui_font, 8), anchor="w"), sk_key)
        sl.pack(fill="x")

        nav_nodes[key] = {
            "row": row,
            "bar": bar,
            "inner": inner,
            "cv": cv,
            "txts": txts,
            "tl": tl,
            "sl": sl,
            "shape": shape,
            "color": color,
        }
        for w in (row, bar, inner, cv, txts, tl, sl):
            w.bind("<ButtonRelease-1>", lambda _e, k=key: select_page(k))

    # ---- Sidebar Bottom Status Card ----
    side_foot = tk.Frame(sidebar, bg=C_SIDEBAR, padx=14, pady=14)
    side_foot.pack(side="bottom", fill="x")
    status_card = tk.Frame(side_foot, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1, padx=12, pady=10)
    status_card.pack(fill="x")
    status_dot = bind_tr(
        tk.Label(status_card, bg=C_CARD, fg=C_ACCENT, font=(ui_font, 9, "bold"), anchor="w"),
        "status_ready",
    )
    status_dot.pack(fill="x")
    bind_tr(
        tk.Label(status_card, bg=C_CARD, fg=C_DIM, font=(ui_font, 8), justify="left", anchor="w"),
        "status_sub",
    ).pack(fill="x", pady=(4, 0))

    # ---- Page Host ----
    page_host = tk.Frame(main_col, bg=C_BG, padx=22, pady=14)
    page_host.pack(fill="both", expand=True)

    def make_card(parent: tk.Widget, title_key: str, sub_key: str = "") -> tk.Frame:
        wrap = tk.Frame(parent, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1, padx=16, pady=11)
        wrap.pack(fill="x", pady=(0, 10))
        hdr = tk.Frame(wrap, bg=C_CARD)
        hdr.pack(fill="x", pady=(0, 7))
        bind_tr(tk.Label(hdr, bg=C_CARD, fg=C_TEXT, font=(ui_font, 10, "bold")), title_key).pack(side="left")
        if sub_key:
            bind_tr(tk.Label(hdr, bg=C_CARD, fg=C_DIM, font=(ui_font, 8)), sub_key, mode="sub").pack(side="left")
        body = tk.Frame(wrap, bg=C_CARD)
        body.pack(fill="x")
        return body

    def make_input_row(parent: tk.Frame, row_idx: int, label_key: str, key: str, is_dir: bool) -> None:
        bind_tr(
            tk.Label(parent, bg=C_CARD, fg=C_MUTED, font=(ui_font, 9), anchor="w", width=22), label_key
        ).grid(row=row_idx, column=0, sticky="w", pady=3)
        ent_wrap = tk.Frame(parent, bg=C_BORDER, padx=1, pady=1)
        ent_wrap.grid(row=row_idx, column=1, sticky="ew", padx=(8, 8), pady=3)
        ent = tk.Entry(
            ent_wrap, textvariable=vars_map[key], bg=C_INPUT, fg=C_TEXT, insertbackground=C_ACCENT, relief="flat", font=(ui_font, 9)
        )
        ent.pack(fill="x", ipady=4, padx=6)
        ent.bind("<FocusIn>", lambda _e, w=ent_wrap: w.configure(bg=C_ACCENT))
        ent.bind("<FocusOut>", lambda _e, w=ent_wrap: w.configure(bg=C_BORDER))

        def pick() -> None:
            chosen = filedialog.askdirectory() if is_dir else filedialog.askopenfilename()
            if chosen:
                vars_map[key].set(chosen)

        b = ModernButton(parent, tr("btn_browse"), pick, font_spec=(ui_font, 8, "bold"), padx=10, pady=4)
        bind_tr(b, "btn_browse", mode="modern")
        b.grid(row=row_idx, column=2, pady=3)

    # ================ PAGE 1: BUILD & SHADERS ================
    p_build = tk.Frame(page_host, bg=C_BG)
    pages["build"] = p_build

    bind_tr(tk.Label(p_build, bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w"), "p_build_h").pack(fill="x")
    bind_tr(tk.Label(p_build, bg=C_BG, fg=C_MUTED, font=(ui_font, 9), anchor="w"), "p_build_s").pack(fill="x", pady=(2, 10))

    c_src = make_card(p_build, "c_src_t", "c_src_s")
    c_src.columnconfigure(1, weight=1)
    make_input_row(c_src, 0, "lbl_game", "game", False)
    make_input_row(c_src, 1, "lbl_update", "update", False)
    make_input_row(c_src, 2, "lbl_keys", "keys", False)
    make_input_row(c_src, 3, "lbl_exefs", "exefs", True)
    make_input_row(c_src, 4, "lbl_romfs", "romfs", True)
    make_input_row(c_src, 5, "lbl_shaders", "shaders", True)
    make_input_row(c_src, 6, "lbl_out", "out", True)

    c_opt = make_card(p_build, "c_opt_t", "c_opt_s")
    toggles = tk.Frame(c_opt, bg=C_CARD)
    toggles.pack(fill="x", pady=(0, 8))
    for k_txt, bkey in (("chk_prompts", "prompts"), ("chk_shaders", "pretranslate_shaders")):
        cb = tk.Checkbutton(
            toggles,
            variable=bool_map[bkey],
            bg=C_CARD,
            fg=C_TEXT,
            selectcolor=C_INPUT,
            activebackground=C_CARD,
            activeforeground=C_ACCENT,
            highlightthickness=0,
            font=(ui_font, 9),
            cursor="hand2",
        )
        bind_tr(cb, k_txt)
        cb.pack(side="left", padx=(0, 22))

    presets = tk.Frame(c_opt, bg=C_CARD)
    presets.pack(fill="x")
    for k_lbl, vkey, vals, w in (
        ("lbl_res", "res", ("1920x1080", "2560x1440", "3840x2160"), 11),
        ("lbl_hz", "hz", ("120", "60"), 5),
        ("lbl_fg", "frame_gen", ("off", "fsr3"), 6),
        ("lbl_scale", "scale", ("game", "100", "75"), 6),
        ("lbl_lang", "lang", ("es-419", "es-ES", "en-US", "fr-FR", "de-DE", "ja-JP"), 7),
    ):
        cell = tk.Frame(presets, bg=C_CARD)
        cell.pack(side="left", padx=(0, 14))
        bind_tr(tk.Label(cell, bg=C_CARD, fg=C_DIM, font=(ui_font, 8, "bold"), anchor="w"), k_lbl).pack(fill="x", pady=(0, 3))
        ttk.Combobox(cell, textvariable=vars_map[vkey], values=vals, width=w, state="readonly", style="Dark.TCombobox").pack()

    # ================ PAGE 2: MODS & GAMEBANANA ================
    p_mods = tk.Frame(page_host, bg=C_BG)
    pages["mods"] = p_mods

    bind_tr(tk.Label(p_mods, bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w"), "p_mods_h").pack(fill="x")
    bind_tr(tk.Label(p_mods, bg=C_BG, fg=C_MUTED, font=(ui_font, 9), anchor="w"), "p_mods_s").pack(fill="x", pady=(2, 10))

    # Console log queue declared early so GameBanana & Artwork actions can stream live logs
    q: queue.Queue[str | None] = queue.Queue()
    gb_results: list[GBMod] = []

    c_gb = make_card(p_mods, "c_gb_t", "c_gb_s")
    gb_bar = tk.Frame(c_gb, bg=C_CARD)
    gb_bar.pack(fill="x", pady=(0, 6))
    gb_ent_wrap = tk.Frame(gb_bar, bg=C_BORDER, padx=1, pady=1)
    gb_ent_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))
    gb_ent = tk.Entry(
        gb_ent_wrap, textvariable=vars_map["gb_query"], bg=C_INPUT, fg=C_TEXT, insertbackground=C_ACCENT, relief="flat", font=(ui_font, 9)
    )
    gb_ent.pack(fill="x", ipady=4, padx=6)
    gb_ent.bind("<FocusIn>", lambda _e: gb_ent_wrap.configure(bg=C_ACCENT))
    gb_ent.bind("<FocusOut>", lambda _e: gb_ent_wrap.configure(bg=C_BORDER))

    ttk.Combobox(
        gb_bar, textvariable=vars_map["gb_sort"], values=("default", "new", "updated"), width=9, state="readonly", style="Dark.TCombobox"
    ).pack(side="left", padx=(0, 8))

    gb_list_wrap = tk.Frame(c_gb, bg=C_BORDER, padx=1, pady=1)
    gb_list_wrap.pack(fill="x", pady=(0, 6))
    gb_list = tk.Listbox(
        gb_list_wrap,
        height=6,
        bg=C_INPUT,
        fg=C_TEXT,
        selectbackground=C_ACCENT,
        selectforeground=C_ACCENT_TXT,
        relief="flat",
        font=(ui_font, 9),
        highlightthickness=0,
    )
    gb_list.pack(fill="both", expand=True, padx=4, pady=3)

    gb_actions = tk.Frame(c_gb, bg=C_CARD)
    gb_actions.pack(fill="x")

    bind_tr(
        tk.Label(c_gb, bg=C_CARD, fg=C_GOLD, font=(ui_font, 8), wraplength=820, justify="left", anchor="w"), "gb_note"
    ).pack(fill="x", pady=(6, 0))

    c_queue = make_card(p_mods, "c_queue_t", "c_queue_s")
    lb_wrap = tk.Frame(c_queue, bg=C_BORDER, padx=1, pady=1)
    lb_wrap.pack(fill="x", pady=(0, 6))
    mods_list = tk.Listbox(
        lb_wrap,
        height=4,
        bg=C_INPUT,
        fg=C_TEXT,
        selectbackground=C_ACCENT,
        selectforeground=C_ACCENT_TXT,
        relief="flat",
        font=(ui_font, 9),
        highlightthickness=0,
    )
    mods_list.pack(fill="both", expand=True, padx=4, pady=3)
    mod_btns = tk.Frame(c_queue, bg=C_CARD)
    mod_btns.pack(fill="x")

    def _run_gb_search() -> None:
        query = vars_map["gb_query"].get().strip()
        sort = vars_map["gb_sort"].get().strip() or "default"
        q.put(f">>> GameBanana search: '{query or '(featured)'}' ({sort})\n")

        def worker() -> None:
            try:
                mods = search_mods(query=query, page=1, sort=sort)
                gb_results.clear()
                gb_results.extend(mods)

                def _fill() -> None:
                    gb_list.delete(0, "end")
                    for m in mods:
                        gb_list.insert("end", f"[{m.category}]  {m.name}   —   by {m.author}  (★ {m.likes})")

                root.after(0, _fill)
                q.put(f"[ok] GameBanana returned {len(mods)} TOTK mods.\n")
            except Exception as exc:
                q.put(f"[err] GameBanana search failed: {exc}\n")

        threading.Thread(target=worker, daemon=True).start()

    gb_ent.bind("<Return>", lambda _e: _run_gb_search())

    def _choose_file_dialog(mod: GBMod, files: list[GBFile]) -> GBFile | None:
        if len(files) == 1:
            return files[0]
        picked: list[GBFile | None] = [None]
        dlg = tk.Toplevel(root)
        dlg.title(tr("pick_file_t"))
        dlg.configure(bg=C_CARD)
        dlg.geometry("560x320")
        dlg.transient(root)
        dlg.grab_set()
        tk.Label(dlg, text=f"{tr('pick_file_h')}\n{mod.name}", bg=C_CARD, fg=C_TEXT, font=(ui_font, 10, "bold"), justify="left").pack(
            fill="x", padx=16, pady=(14, 8)
        )
        lb = tk.Listbox(dlg, bg=C_INPUT, fg=C_TEXT, selectbackground=C_ACCENT, selectforeground=C_ACCENT_TXT, relief="flat", font=(ui_font, 9))
        for f in files:
            lb.insert("end", f"{f.filename}   ({f.size_bytes / (1024 * 1024):.2f} MiB)")
        lb.selection_set(0)
        lb.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        bf = tk.Frame(dlg, bg=C_CARD)
        bf.pack(fill="x", padx=16, pady=(0, 14))

        def _ok() -> None:
            sel = lb.curselection()
            if sel:
                picked[0] = files[sel[0]]
            dlg.destroy()

        ModernButton(bf, tr("btn_cancel"), dlg.destroy, padx=12, pady=6).pack(side="right")
        ModernButton(bf, tr("btn_download"), _ok, bg=C_ACCENT, hover_bg=C_ACCENT_HOV, fg=C_ACCENT_TXT, border=C_ACCENT, padx=14, pady=6).pack(
            side="right", padx=(0, 8)
        )
        root.wait_window(dlg)
        return picked[0]

    def _run_gb_download() -> None:
        sel = gb_list.curselection()
        if not sel:
            return
        mod = gb_results[sel[0]]
        q.put(f">>> Fetching files for GameBanana mod #{mod.mod_id} ({mod.name})...\n")

        def worker() -> None:
            try:
                files = fetch_mod_files(mod.mod_id)
                if not files:
                    q.put("[err] No downloadable files found for this mod.\n")
                    return
                chosen_box: list[GBFile | None] = [None]
                ev = threading.Event()

                def _ask() -> None:
                    chosen_box[0] = _choose_file_dialog(mod, files)
                    ev.set()

                root.after(0, _ask)
                ev.wait()
                chosen = chosen_box[0]
                if not chosen:
                    return
                mods_root = Path(vars_map["out"].get().strip() or str(Path.home() / "TOTK-PS5-Out")) / "data_totk_ps5" / "mods"
                staged_dir, warns = download_and_stage_mod(chosen, mod.name, mods_root, log_fn=lambda m: q.put(m + "\n"))
                for w in warns:
                    q.put(f"[warn] {w}\n")

                def _add() -> None:
                    existing = [mods_list.get(i) for i in range(mods_list.size())]
                    if str(staged_dir) not in existing:
                        mods_list.insert("end", str(staged_dir))

                root.after(0, _add)
            except Exception as exc:
                q.put(f"[err] GameBanana download failed: {exc}\n")

        threading.Thread(target=worker, daemon=True).start()

    def _push_mods_ftp_now() -> None:
        host = vars_map["ftp_host"].get().strip()
        if not host:
            messagebox.showerror(tr("err_no_ip_t"), tr("err_no_ip_m"))
            select_page("ftp")
            return
        port = int(vars_map["ftp_port"].get().strip() or "2121")
        out_mods = Path(vars_map["out"].get().strip() or str(Path.home() / "TOTK-PS5-Out")) / "data_totk_ps5" / "mods"
        if not out_mods.is_dir():
            q.put("[err] No staged mods directory found yet.\n")
            return
        q.put(f">>> Pushing staged mods from {out_mods} -> ps5://{host}:{port}/data/totk-ps5/mods\n")

        def worker() -> None:
            try:
                dep = PS5Deployer(host, port, log_fn=lambda m: q.put(m + "\n"))
                try:
                    dep.mkdir_p("/data/totk-ps5/mods")
                    dep.chmod_777("/data/totk-ps5/mods")
                    n = dep.upload_dir(out_mods, "/data/totk-ps5/mods")
                    q.put(f"[ok] Uploaded {n} mod files to /data/totk-ps5/mods!\n")
                finally:
                    dep.close()
            except Exception as exc:
                q.put(f"[err] FTP mod upload failed: {exc}\n")

        threading.Thread(target=worker, daemon=True).start()

    b_search = ModernButton(gb_bar, tr("btn_search"), _run_gb_search, bg=C_ACCENT, hover_bg=C_ACCENT_HOV, fg=C_ACCENT_TXT, border=C_ACCENT, padx=12, pady=5)
    bind_tr(b_search, "btn_search", mode="modern")
    b_search.pack(side="left")

    b_gbdl = ModernButton(gb_actions, tr("btn_gb_dl"), _run_gb_download, bg=C_ACCENT, hover_bg=C_ACCENT_HOV, fg=C_ACCENT_TXT, border=C_ACCENT, padx=12, pady=5)
    bind_tr(b_gbdl, "btn_gb_dl", mode="modern")
    b_gbdl.pack(side="left", padx=(0, 8))

    b_gbftp = ModernButton(gb_actions, tr("btn_gb_ftp"), _push_mods_ftp_now, bg=C_BLUE, hover_bg=C_BLUE_HOV, fg="#05131C", border=C_BLUE, padx=12, pady=5)
    bind_tr(b_gbftp, "btn_gb_ftp", mode="modern")
    b_gbftp.pack(side="left")

    def add_mod_folder() -> None:
        d = filedialog.askdirectory()
        if d:
            mods_list.insert("end", d)

    def add_mod_zip() -> None:
        f = filedialog.askopenfilename(filetypes=[("ZIP archives", "*.zip")])
        if f:
            mods_list.insert("end", f)

    def remove_mod() -> None:
        for idx in reversed(mods_list.curselection()):
            mods_list.delete(idx)

    for key_b, fn, fg_c in (("btn_add_dir", add_mod_folder, C_TEXT), ("btn_add_zip", add_mod_zip, C_TEXT), ("btn_rm_mod", remove_mod, C_DANGER)):
        mb = ModernButton(mod_btns, tr(key_b), fn, fg=fg_c, font_spec=(ui_font, 8, "bold"), padx=10, pady=5)
        bind_tr(mb, key_b, mode="modern")
        mb.pack(side="left", padx=(0, 8))

    # ================ PAGE 3: DEPLOY TO PS5 (FTP) ================
    p_ftp = tk.Frame(page_host, bg=C_BG)
    pages["ftp"] = p_ftp

    bind_tr(tk.Label(p_ftp, bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w"), "p_ftp_h").pack(fill="x")
    bind_tr(tk.Label(p_ftp, bg=C_BG, fg=C_MUTED, font=(ui_font, 9), anchor="w"), "p_ftp_s").pack(fill="x", pady=(2, 12))

    c_ftp = make_card(p_ftp, "c_ftp_t", "c_ftp_s")
    ftp_row = tk.Frame(c_ftp, bg=C_CARD)
    ftp_row.pack(fill="x", pady=(0, 10))
    bind_tr(tk.Label(ftp_row, bg=C_CARD, fg=C_MUTED, font=(ui_font, 9)), "lbl_ip").pack(side="left", padx=(0, 8))
    ip_wrap = tk.Frame(ftp_row, bg=C_BORDER, padx=1, pady=1)
    ip_wrap.pack(side="left", padx=(0, 18))
    ip_ent = tk.Entry(ip_wrap, textvariable=vars_map["ftp_host"], width=20, bg=C_INPUT, fg=C_TEXT, insertbackground=C_ACCENT, relief="flat", font=(ui_font, 10))
    ip_ent.pack(ipady=5, padx=8)
    ip_ent.bind("<FocusIn>", lambda _e: ip_wrap.configure(bg=C_ACCENT))
    ip_ent.bind("<FocusOut>", lambda _e: ip_wrap.configure(bg=C_BORDER))

    bind_tr(tk.Label(ftp_row, bg=C_CARD, fg=C_MUTED, font=(ui_font, 9)), "lbl_port").pack(side="left", padx=(0, 8))
    pt_wrap = tk.Frame(ftp_row, bg=C_BORDER, padx=1, pady=1)
    pt_wrap.pack(side="left")
    tk.Entry(pt_wrap, textvariable=vars_map["ftp_port"], width=8, bg=C_INPUT, fg=C_TEXT, insertbackground=C_ACCENT, relief="flat", font=(ui_font, 10)).pack(
        ipady=5, padx=8
    )

    for k_txt, bkey in (("chk_ftp_sh", "ftp_shaders"), ("chk_ftp_ini", "ftp_ini"), ("chk_ftp_romfs", "ftp_romfs")):
        cb = tk.Checkbutton(
            c_ftp,
            variable=bool_map[bkey],
            bg=C_CARD,
            fg=C_TEXT,
            selectcolor=C_INPUT,
            activebackground=C_CARD,
            activeforeground=C_ACCENT,
            highlightthickness=0,
            font=(ui_font, 9),
            anchor="w",
            cursor="hand2",
        )
        bind_tr(cb, k_txt)
        cb.pack(fill="x", pady=3)

    # ================ PAGE 4: LAYOUT & ARTWORK ================
    p_layout = tk.Frame(page_host, bg=C_BG)
    pages["layout"] = p_layout

    bind_tr(tk.Label(p_layout, bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w"), "p_lay_h").pack(fill="x")
    bind_tr(tk.Label(p_layout, bg=C_BG, fg=C_MUTED, font=(ui_font, 9), anchor="w"), "p_lay_s").pack(fill="x", pady=(2, 10))

    c_art = make_card(p_layout, "c_art_t", "c_art_s")
    art_row = tk.Frame(c_art, bg=C_CARD)
    art_row.pack(fill="x")
    bind_tr(tk.Label(art_row, bg=C_CARD, fg=C_MUTED, font=(ui_font, 9)), "lbl_art_url").pack(side="left", padx=(0, 8))
    art_wrap = tk.Frame(art_row, bg=C_BORDER, padx=1, pady=1)
    art_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))
    tk.Entry(art_wrap, textvariable=vars_map["art_url"], bg=C_INPUT, fg=C_TEXT, insertbackground=C_ACCENT, relief="flat", font=(ui_font, 9)).pack(
        fill="x", ipady=4, padx=6
    )

    def _fetch_art_url() -> None:
        url = vars_map["art_url"].get().strip()
        if not url:
            return
        dest = Path(vars_map["out"].get().strip() or str(Path.home() / "TOTK-PS5-Out")) / TITLE_ID / "sce_sys" / "icon0.png"
        q.put(f">>> Downloading custom PS5 icon0.png from {url}...\n")

        def worker() -> None:
            try:
                download_ps5_icon_from_url(url, dest)
                q.put(f"[ok] Saved 512x512 PS5 icon0.png -> {dest}\n")
                new_logo = _load_logo(dest, size=50)
                if new_logo is not None:
                    def _upd() -> None:
                        logo_lbl.configure(image=new_logo)
                        logo_lbl.image = new_logo  # type: ignore[attr-defined]
                    root.after(0, _upd)
            except Exception as exc:
                q.put(f"[err] Icon download failed: {exc}\n")

        threading.Thread(target=worker, daemon=True).start()

    b_art = ModernButton(art_row, tr("btn_art_dl"), _fetch_art_url, font_spec=(ui_font, 8, "bold"), padx=10, pady=5)
    bind_tr(b_art, "btn_art_dl", mode="modern")
    b_art.pack(side="left")

    lay_card = tk.Frame(p_layout, bg=C_TERM, highlightbackground=C_BORDER, highlightthickness=1, padx=8, pady=8)
    lay_card.pack(fill="both", expand=True)
    layout_box = scrolledtext.ScrolledText(
        lay_card, height=12, bg=C_TERM, fg="#CBD5E1", relief="flat", borderwidth=0, font=(mono_font, 9)
    )
    layout_box.insert("1.0", PS5_LAYOUT_TEXT)
    layout_box.config(state="disabled")
    layout_box.pack(fill="both", expand=True)

    # ================ BOTTOM CONSOLE & ACTION DOCK ================
    dock = tk.Frame(main_col, bg=C_BG, padx=22, pady=10)
    dock.pack(side="bottom", fill="x")

    pbar = ttk.Progressbar(dock, mode="indeterminate", style="Zonai.Horizontal.TProgressbar")
    pbar.pack(fill="x", pady=(0, 7))

    term_card = tk.Frame(dock, bg=C_TERM, highlightbackground=C_BORDER, highlightthickness=1, padx=8, pady=6)
    term_card.pack(fill="x", pady=(0, 9))
    log_box = scrolledtext.ScrolledText(
        term_card, height=7, bg=C_TERM, fg="#CBD5E1", insertbackground=C_ACCENT, relief="flat", borderwidth=0, font=(mono_font, 9)
    )
    log_box.tag_config("ok", foreground=C_ACCENT)
    log_box.tag_config("info", foreground=C_BLUE)
    log_box.tag_config("gold", foreground=C_GOLD)
    log_box.tag_config("err", foreground=C_DANGER)
    log_box.pack(fill="x")

    action_buttons: list[ModernButton] = []

    def set_busy(busy: bool, msg: str = "") -> None:
        for b in action_buttons:
            b.set_enabled(not busy)
        if busy:
            status_dot.configure(text=f"●  {msg or 'Working...'}", fg=C_GOLD)
            pbar.start(14)
        else:
            status_dot.configure(text=tr("status_ready"), fg=C_ACCENT)
            pbar.stop()

    def _insert_colored(line: str) -> None:
        tag = None
        low = line.lower()
        if line.startswith("[ok]") or "passed" in low:
            tag = "ok"
        elif line.startswith("[err]") or "error" in low or "failed" in low:
            tag = "err"
        elif line.startswith("[ftp]") or line.startswith("[warn]") or line.startswith(">>>"):
            tag = "gold"
        elif line.startswith("[ps5-totk]") or line.startswith("[gb]") or line.startswith("[check]"):
            tag = "info"
        log_box.insert("end", line, tag) if tag else log_box.insert("end", line)
        log_box.see("end")

    def pump() -> None:
        try:
            while True:
                item = q.get_nowait()
                if item is None:
                    set_busy(False)
                    break
                _insert_colored(item)
        except queue.Empty:
            pass
        root.after(100, pump)

    def build_cli_cmd(*, deploy_ftp: bool, deploy_only: bool = False) -> list[str]:
        cmd = [str(paths.python_bin), "-P", "-u", "-m", "builder.cli", "--out", vars_map["out"].get().strip()]
        if deploy_only:
            cmd.append("--deploy-only")
        else:
            if vars_map["game"].get().strip():
                cmd += ["--game", vars_map["game"].get().strip()]
                if vars_map["update"].get().strip():
                    cmd += ["--update", vars_map["update"].get().strip()]
                if vars_map["keys"].get().strip():
                    cmd += ["--keys", vars_map["keys"].get().strip()]
            else:
                cmd += ["--exefs", vars_map["exefs"].get().strip()]
                if vars_map["romfs"].get().strip():
                    cmd += ["--romfs", vars_map["romfs"].get().strip()]
            if vars_map["shaders"].get().strip():
                cmd += ["--shaders", vars_map["shaders"].get().strip()]
            if not bool_map["prompts"].get():
                cmd.append("--no-prompts")
            if bool_map["pretranslate_shaders"].get():
                cmd.append("--pretranslate-shaders")
            cmd += [
                "--res",
                vars_map["res"].get(),
                "--hz",
                vars_map["hz"].get(),
                "--frame-gen",
                vars_map["frame_gen"].get(),
                "--scale",
                vars_map["scale"].get(),
                "--lang",
                vars_map["lang"].get(),
            ]
            for i in range(mods_list.size()):
                cmd += ["--mod", mods_list.get(i)]
        if deploy_ftp:
            cmd += ["--deploy-ftp", vars_map["ftp_host"].get().strip(), "--ftp-port", vars_map["ftp_port"].get().strip()]
            if bool_map["ftp_romfs"].get():
                cmd.append("--deploy-romfs")
            if not bool_map["ftp_shaders"].get():
                cmd.append("--skip-ftp-shaders")
            if not bool_map["ftp_ini"].get():
                cmd.append("--skip-ftp-ini")
        return cmd

    def run_cmd_async(cmd: list[str], label: str) -> None:
        set_busy(True, label)
        log_box.delete("1.0", "end")
        _insert_colored(f">>> {label}\n")

        def worker() -> None:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                assert proc.stdout is not None
                for line in proc.stdout:
                    q.put(line)
                rc = proc.wait()
                q.put(f"\n{'[ok] Done.' if rc == 0 else f'[err] Failed (exit {rc}).'}\n")
            except Exception as exc:
                q.put(f"\n[err] {exc}\n")
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _validate(*, need_ftp: bool, deploy_only: bool) -> bool:
        if not deploy_only:
            if not vars_map["game"].get().strip() and not vars_map["exefs"].get().strip():
                messagebox.showerror(tr("err_no_game_t"), tr("err_no_game_m"))
                select_page("build")
                return False
            if vars_map["game"].get().strip() and not vars_map["keys"].get().strip():
                messagebox.showerror(tr("err_no_keys_t"), tr("err_no_keys_m"))
                select_page("build")
                return False
        if need_ftp and not vars_map["ftp_host"].get().strip():
            messagebox.showerror(tr("err_no_ip_t"), tr("err_no_ip_m"))
            select_page("ftp")
            return False
        return True

    bar_btns = tk.Frame(dock, bg=C_BG)
    bar_btns.pack(fill="x")

    b_check = bind_tr(
        ModernButton(
            bar_btns,
            tr("btn_check"),
            lambda: run_cmd_async([str(paths.python_bin), "-P", "-u", "-m", "builder.cli", "--check"], tr("btn_check")),
            font_spec=(ui_font, 9, "bold"),
            padx=14,
            pady=8,
        ),
        "btn_check",
        mode="modern",
    )
    b_check.pack(side="left", padx=(0, 8))

    b_ftp = bind_tr(
        ModernButton(
            bar_btns,
            tr("btn_ftp_only"),
            lambda: _validate(need_ftp=True, deploy_only=True) and run_cmd_async(build_cli_cmd(deploy_ftp=True, deploy_only=True), tr("btn_ftp_only")),
            font_spec=(ui_font, 9, "bold"),
            padx=14,
            pady=8,
        ),
        "btn_ftp_only",
        mode="modern",
    )
    b_ftp.pack(side="left")

    b_both = bind_tr(
        ModernButton(
            bar_btns,
            tr("btn_both"),
            lambda: _validate(need_ftp=True, deploy_only=False) and run_cmd_async(build_cli_cmd(deploy_ftp=True), tr("btn_both")),
            bg=C_BLUE,
            hover_bg=C_BLUE_HOV,
            fg="#05131C",
            border=C_BLUE,
            font_spec=(ui_font, 10, "bold"),
            padx=18,
            pady=8,
        ),
        "btn_both",
        mode="modern",
    )
    b_both.pack(side="right")

    b_build = bind_tr(
        ModernButton(
            bar_btns,
            tr("btn_build"),
            lambda: _validate(need_ftp=False, deploy_only=False) and run_cmd_async(build_cli_cmd(deploy_ftp=False), tr("btn_build")),
            bg=C_ACCENT,
            hover_bg=C_ACCENT_HOV,
            fg=C_ACCENT_TXT,
            border=C_ACCENT,
            font_spec=(ui_font, 10, "bold"),
            padx=18,
            pady=8,
        ),
        "btn_build",
        mode="modern",
    )
    b_build.pack(side="right", padx=(0, 10))
    action_buttons.extend([b_check, b_ftp, b_build, b_both])

    apply_language("es")
    select_page("build")
    _insert_colored(tr("welcome"))
    root.after(100, pump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run_gui())
