"""PS5 Tears of the Kingdom Builder — Modern Obsidian & Zonai Desktop UI (PPSA99199)."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from .deploy import PS5_LAYOUT_TEXT
from .pipeline import TITLE_ID, default_kit_paths

# ---- Obsidian x Zonai Emerald & Hylian Gold Design Tokens ----
C_BG = "#0B0E14"          # Deep obsidian canvas
C_SIDEBAR = "#0F141D"     # Elevated sidebar surface
C_CARD = "#141B26"        # Card surface
C_CARD_ALT = "#182130"    # Hover / nested surface
C_BORDER = "#222E42"      # Hairline structural border
C_INPUT = "#0C1119"       # Crisp dark input well
C_TERM = "#070A0F"        # Console terminal background

C_ACCENT = "#2EE6A6"      # Zonai Emerald primary CTA
C_ACCENT_HOV = "#4BF2B8"
C_ACCENT_TXT = "#061610"
C_GOLD = "#E6C36A"        # Hylian Gold highlight
C_BLUE = "#38BDF8"        # PS5 Cyan-Blue secondary CTA
C_BLUE_HOV = "#60CCF9"
C_DANGER = "#F87171"

C_TEXT = "#F1F5F9"        # High-contrast primary text
C_MUTED = "#94A3B8"       # Secondary labels
C_DIM = "#64748B"         # Subtle captions


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


def _load_logo(icon_path: Path, size: int = 54) -> tk.PhotoImage | None:
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


class ModernButton(tk.Frame):
    """Flat, border-styled button with smooth hover transitions and hand cursor."""

    def __init__(
        self,
        parent: tk.Widget,
        text: str,
        command,
        *,
        bg: str = C_CARD_ALT,
        hover_bg: str = "#223047",
        fg: str = C_TEXT,
        border: str = C_BORDER,
        font_spec=("Sans", 10, "bold"),
        padx: int = 14,
        pady: int = 8,
    ) -> None:
        super().__init__(parent, bg=border, padx=1, pady=1, cursor="hand2")
        self._bg = bg
        self._hover_bg = hover_bg
        self._fg = fg
        self._cmd = command
        self._enabled = True

        self._inner = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            font=font_spec,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self._inner.pack(fill="both", expand=True)

        for w in (self, self._inner):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<ButtonRelease-1>", self._on_click)

    def _on_enter(self, _e=None) -> None:
        if self._enabled:
            self._inner.configure(bg=self._hover_bg)

    def _on_leave(self, _e=None) -> None:
        if self._enabled:
            self._inner.configure(bg=self._bg)

    def _on_click(self, _e=None) -> None:
        if self._enabled and self._cmd:
            self._cmd()

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
    root.title(f"PS5 TOTK Builder — Tears of the Kingdom ({TITLE_ID})")
    root.geometry("1100x760")
    root.minsize(980, 680)
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

    # ---- Shared State (100% clean — zero hardcoded personal paths or LAN IPs) ----
    vars_map: dict[str, tk.StringVar] = {
        "game": tk.StringVar(value=""),
        "update": tk.StringVar(value=""),
        "keys": tk.StringVar(value=""),
        "exefs": tk.StringVar(value=""),
        "romfs": tk.StringVar(value=""),
        "shaders": tk.StringVar(value=""),
        "out": tk.StringVar(value=str(Path.home() / "TOTK-PS5-Out")),
        "res": tk.StringVar(value="2560x1440"),
        "hz": tk.StringVar(value="120"),
        "frame_gen": tk.StringVar(value="fsr3"),
        "scale": tk.StringVar(value="game"),
        "lang": tk.StringVar(value="es-419"),
        "ftp_host": tk.StringVar(value=""),
        "ftp_port": tk.StringVar(value="2121"),
    }
    bool_map: dict[str, tk.BooleanVar] = {
        "prompts": tk.BooleanVar(value=True),
        "pretranslate_shaders": tk.BooleanVar(value=True),
        "ftp_romfs": tk.BooleanVar(value=False),
        "ftp_shaders": tk.BooleanVar(value=True),
        "ftp_ini": tk.BooleanVar(value=True),
    }

    # ---- Root Two-Column Shell: Left Sidebar + Right Main Workspace ----
    shell = tk.Frame(root, bg=C_BG)
    shell.pack(fill="both", expand=True)

    sidebar = tk.Frame(shell, bg=C_SIDEBAR, width=236)
    sidebar.pack(side="left", fill="y")
    sidebar.pack_propagate(False)
    tk.Frame(shell, bg=C_BORDER, width=1).pack(side="left", fill="y")

    main_col = tk.Frame(shell, bg=C_BG)
    main_col.pack(side="left", fill="both", expand=True)

    # ---- Sidebar Brand Header ----
    brand = tk.Frame(sidebar, bg=C_SIDEBAR, padx=18, pady=20)
    brand.pack(fill="x")

    logo_img = _load_logo(paths.assets_sce_sys / "icon0.png", size=52)
    if logo_img is not None:
        logo_lbl = tk.Label(brand, image=logo_img, bg=C_SIDEBAR)
        logo_lbl.image = logo_img  # type: ignore[attr-defined]
        logo_lbl.pack(side="left", padx=(0, 12))

    brand_txt = tk.Frame(brand, bg=C_SIDEBAR)
    brand_txt.pack(side="left", fill="x", expand=True)
    tk.Label(
        brand_txt,
        text="TOTK PS5",
        bg=C_SIDEBAR,
        fg=C_TEXT,
        font=(ui_font, 14, "bold"),
        anchor="w",
    ).pack(fill="x")
    tk.Label(
        brand_txt,
        text=f"{TITLE_ID}  ·  BUILDER",
        bg=C_SIDEBAR,
        fg=C_GOLD,
        font=(ui_font, 8, "bold"),
        anchor="w",
    ).pack(fill="x", pady=(2, 0))

    tk.Frame(sidebar, bg=C_BORDER, height=1).pack(fill="x", padx=16, pady=(0, 14))

    # ---- Sidebar Navigation ----
    nav_items = [
        ("build", "◆", "Compilar & Shaders", "ExeFS, RomFS, -O2 y RADV"),
        ("mods", "◈", "Mods (RomFS)", "Carpetas y archivos .zip"),
        ("ftp", "▲", "Enviar a PS5", "Despliegue seguro por FTP"),
        ("layout", "▤", "Layout PS5", "Rutas exactas en consola"),
    ]
    nav_widgets: dict[str, tuple[tk.Frame, tk.Frame, tk.Label, tk.Label, tk.Label]] = {}
    pages: dict[str, tk.Frame] = {}

    def select_page(key: str) -> None:
        for k, page in pages.items():
            if k == key:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        for k, (row, bar, ico, title_l, sub_l) in nav_widgets.items():
            active = k == key
            bg_c = "#172233" if active else C_SIDEBAR
            row.configure(bg=bg_c)
            bar.configure(bg=C_ACCENT if active else bg_c)
            ico.configure(bg=bg_c, fg=C_ACCENT if active else C_DIM)
            title_l.configure(bg=bg_c, fg=C_TEXT if active else C_MUTED)
            sub_l.configure(bg=bg_c, fg=C_MUTED if active else C_DIM)

    for key, icon_ch, title_txt, sub_txt in nav_items:
        row = tk.Frame(sidebar, bg=C_SIDEBAR, cursor="hand2")
        row.pack(fill="x", padx=10, pady=3)
        bar = tk.Frame(row, bg=C_SIDEBAR, width=3)
        bar.pack(side="left", fill="y", pady=4)
        inner = tk.Frame(row, bg=C_SIDEBAR, padx=10, pady=8)
        inner.pack(side="left", fill="both", expand=True)
        ico = tk.Label(inner, text=icon_ch, bg=C_SIDEBAR, fg=C_DIM, font=(ui_font, 11, "bold"), width=2)
        ico.pack(side="left", padx=(0, 6))
        txts = tk.Frame(inner, bg=C_SIDEBAR)
        txts.pack(side="left", fill="x", expand=True)
        tl = tk.Label(txts, text=title_txt, bg=C_SIDEBAR, fg=C_MUTED, font=(ui_font, 10, "bold"), anchor="w")
        tl.pack(fill="x")
        sl = tk.Label(txts, text=sub_txt, bg=C_SIDEBAR, fg=C_DIM, font=(ui_font, 8), anchor="w")
        sl.pack(fill="x")

        # Keep inner containers synced on background updates
        def _sync_bg(r=row, inn=inner, tx=txts):
            return r, inn, tx

        def _make_click(k=key):
            return lambda _e=None: select_page(k)

        for w in (row, bar, inner, ico, txts, tl, sl):
            w.bind("<ButtonRelease-1>", _make_click())

        # Override row.configure proxy via tuple storing inner/txts too by using a small helper
        nav_widgets[key] = (row, bar, ico, tl, sl)
        row._extras = (inner, txts)  # type: ignore[attr-defined]

    # Patch select_page so inner & txts also match row bg
    _orig_select = select_page

    def select_page(key: str) -> None:  # type: ignore[no-redef]
        _orig_select(key)
        for k, (row, *_rest) in nav_widgets.items():
            bg_c = "#172233" if k == key else C_SIDEBAR
            for extra in getattr(row, "_extras", ()):
                extra.configure(bg=bg_c)

    # ---- Sidebar Bottom Status Badge ----
    side_foot = tk.Frame(sidebar, bg=C_SIDEBAR, padx=14, pady=14)
    side_foot.pack(side="bottom", fill="x")
    status_card = tk.Frame(side_foot, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1, padx=12, pady=10)
    status_card.pack(fill="x")
    status_dot = tk.Label(
        status_card,
        text="●  Listo para compilar",
        bg=C_CARD,
        fg=C_ACCENT,
        font=(ui_font, 9, "bold"),
        anchor="w",
    )
    status_dot.pack(fill="x")
    tk.Label(
        status_card,
        text="PS5 RADV · Zen 2 -O2 · 120 Hz\nAMD FSR 3.1.5 FG · 38 Trofeos",
        bg=C_CARD,
        fg=C_DIM,
        font=(ui_font, 8),
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(4, 0))

    # ---- Main Area: Page Container (top) + Action & Console Dock (bottom) ----
    page_host = tk.Frame(main_col, bg=C_BG, padx=22, pady=16)
    page_host.pack(fill="both", expand=True)

    def make_card(parent: tk.Widget, title: str, subtitle: str = "") -> tk.Frame:
        wrap = tk.Frame(parent, bg=C_CARD, highlightbackground=C_BORDER, highlightthickness=1, padx=16, pady=12)
        wrap.pack(fill="x", pady=(0, 12))
        hdr = tk.Frame(wrap, bg=C_CARD)
        hdr.pack(fill="x", pady=(0, 8))
        tk.Label(hdr, text=title, bg=C_CARD, fg=C_TEXT, font=(ui_font, 10, "bold")).pack(side="left")
        if subtitle:
            tk.Label(hdr, text=f"  ·  {subtitle}", bg=C_CARD, fg=C_DIM, font=(ui_font, 9)).pack(side="left")
        body = tk.Frame(wrap, bg=C_CARD)
        body.pack(fill="x")
        return body

    def make_input_row(parent: tk.Frame, row_idx: int, label: str, key: str, is_dir: bool) -> None:
        tk.Label(parent, text=label, bg=C_CARD, fg=C_MUTED, font=(ui_font, 9), anchor="w", width=21).grid(
            row=row_idx, column=0, sticky="w", pady=4
        )
        ent_wrap = tk.Frame(parent, bg=C_BORDER, padx=1, pady=1)
        ent_wrap.grid(row=row_idx, column=1, sticky="ew", padx=(8, 8), pady=4)
        ent = tk.Entry(
            ent_wrap,
            textvariable=vars_map[key],
            bg=C_INPUT,
            fg=C_TEXT,
            insertbackground=C_ACCENT,
            relief="flat",
            font=(ui_font, 9),
        )
        ent.pack(fill="x", ipady=5, padx=6)
        ent.bind("<FocusIn>", lambda _e, w=ent_wrap: w.configure(bg=C_ACCENT))
        ent.bind("<FocusOut>", lambda _e, w=ent_wrap: w.configure(bg=C_BORDER))

        def pick() -> None:
            chosen = filedialog.askdirectory() if is_dir else filedialog.askopenfilename()
            if chosen:
                vars_map[key].set(chosen)

        ModernButton(
            parent,
            "Examinar",
            pick,
            bg=C_CARD_ALT,
            hover_bg="#243248",
            fg=C_TEXT,
            font_spec=(ui_font, 8, "bold"),
            padx=10,
            pady=5,
        ).grid(row=row_idx, column=2, pady=4)

    # ---------------- PAGE 1: COMPILAR & SHADERS ----------------
    p_build = tk.Frame(page_host, bg=C_BG)
    pages["build"] = p_build

    tk.Label(p_build, text="Compilar & Pre-traducir Shaders", bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w").pack(
        fill="x"
    )
    tk.Label(
        p_build,
        text="Genera eboot.bin (-O2 Zen 2), íconos PlayStation y caché RADV + mvprev desde tu copia legal del juego.",
        bg=C_BG,
        fg=C_MUTED,
        font=(ui_font, 9),
        anchor="w",
    ).pack(fill="x", pady=(2, 12))

    c_src = make_card(p_build, "Origen del Juego", "Usa .xci/.nsp + prod.keys o carpetas extraídas")
    c_src.columnconfigure(1, weight=1)
    make_input_row(c_src, 0, "Juego base (.xci / .nsp)", "game", False)
    make_input_row(c_src, 1, "Update (.nsp opcional)", "update", False)
    make_input_row(c_src, 2, "Switch prod.keys", "keys", False)
    make_input_row(c_src, 3, "O ExeFS extraído", "exefs", True)
    make_input_row(c_src, 4, "O RomFS extraído", "romfs", True)
    make_input_row(c_src, 5, "Caché shaders (opcional)", "shaders", True)
    make_input_row(c_src, 6, "Carpeta de salida", "out", True)

    c_opt = make_card(p_build, "Perfil PS5", "Valores recomendados para 1440p @ 120 Hz + AMD FSR 3.1.5")
    toggles = tk.Frame(c_opt, bg=C_CARD)
    toggles.pack(fill="x", pady=(0, 8))
    for txt, bkey in (
        ("Íconos PlayStation por defecto (△ ○ × □, ○=A)", "prompts"),
        ("Pre-traducir Shaders PS5 RADV + mvprev", "pretranslate_shaders"),
    ):
        tk.Checkbutton(
            toggles,
            text=txt,
            variable=bool_map[bkey],
            bg=C_CARD,
            fg=C_TEXT,
            selectcolor=C_INPUT,
            activebackground=C_CARD,
            activeforeground=C_ACCENT,
            highlightthickness=0,
            font=(ui_font, 9),
            cursor="hand2",
        ).pack(side="left", padx=(0, 22))

    presets = tk.Frame(c_opt, bg=C_CARD)
    presets.pack(fill="x")
    for lbl, vkey, vals, w in (
        ("Resolución", "res", ("2560x1440", "1920x1080"), 11),
        ("Refresco (Hz)", "hz", ("120", "60"), 5),
        ("Frame Gen", "frame_gen", ("fsr3", "off"), 6),
        ("Escala 3D", "scale", ("game", "100", "75"), 6),
        ("Idioma", "lang", ("es-419", "es-ES", "en-US", "fr-FR", "de-DE", "ja-JP"), 7),
    ):
        cell = tk.Frame(presets, bg=C_CARD)
        cell.pack(side="left", padx=(0, 14))
        tk.Label(cell, text=lbl, bg=C_CARD, fg=C_DIM, font=(ui_font, 8, "bold"), anchor="w").pack(fill="x", pady=(0, 3))
        ttk.Combobox(cell, textvariable=vars_map[vkey], values=vals, width=w, state="readonly", style="Dark.TCombobox").pack()

    # ---------------- PAGE 2: MODS ----------------
    p_mods = tk.Frame(page_host, bg=C_BG)
    pages["mods"] = p_mods

    tk.Label(p_mods, text="Gestor de MODS (RomFS)", bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w").pack(fill="x")
    tk.Label(
        p_mods,
        text="Se empaquetan en /data/totk-ps5/mods/ y se activan/desactivan desde Touchpad + Options en tu PS5.",
        bg=C_BG,
        fg=C_MUTED,
        font=(ui_font, 9),
        anchor="w",
    ).pack(fill="x", pady=(2, 12))

    c_mods = make_card(p_mods, "Cola de Mods a Instalar", "Carpetas o archivos .zip")
    lb_wrap = tk.Frame(c_mods, bg=C_BORDER, padx=1, pady=1)
    lb_wrap.pack(fill="x", pady=(0, 10))
    mods_list = tk.Listbox(
        lb_wrap,
        height=10,
        bg=C_INPUT,
        fg=C_TEXT,
        selectbackground=C_ACCENT,
        selectforeground=C_ACCENT_TXT,
        relief="flat",
        font=(ui_font, 9),
        highlightthickness=0,
    )
    mods_list.pack(fill="both", expand=True, padx=4, pady=4)

    mod_btns = tk.Frame(c_mods, bg=C_CARD)
    mod_btns.pack(fill="x")

    def add_mod_folder() -> None:
        d = filedialog.askdirectory(title="Seleccionar carpeta de Mod RomFS")
        if d:
            mods_list.insert("end", d)

    def add_mod_zip() -> None:
        f = filedialog.askopenfilename(title="Seleccionar archivo .zip de Mod", filetypes=[("ZIP archives", "*.zip")])
        if f:
            mods_list.insert("end", f)

    def remove_mod() -> None:
        for idx in reversed(mods_list.curselection()):
            mods_list.delete(idx)

    ModernButton(mod_btns, "+ Carpeta de Mod", add_mod_folder, font_spec=(ui_font, 9, "bold")).pack(side="left", padx=(0, 8))
    ModernButton(mod_btns, "+ Mod (.zip)", add_mod_zip, font_spec=(ui_font, 9, "bold")).pack(side="left", padx=(0, 8))
    ModernButton(mod_btns, "Quitar seleccionado", remove_mod, fg=C_DANGER, font_spec=(ui_font, 9, "bold")).pack(side="left")

    # ---------------- PAGE 3: ENVIAR A PS5 (FTP) ----------------
    p_ftp = tk.Frame(page_host, bg=C_BG)
    pages["ftp"] = p_ftp

    tk.Label(p_ftp, text="Despliegue Directo a PS5 (FTP)", bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w").pack(
        fill="x"
    )
    tk.Label(
        p_ftp,
        text="Solo escribe en /data/homebrew/PPSA99199 y /data/totk-ps5. Nunca toca otros juegos ni partidas existentes.",
        bg=C_BG,
        fg=C_MUTED,
        font=(ui_font, 9),
        anchor="w",
    ).pack(fill="x", pady=(2, 12))

    c_ftp = make_card(p_ftp, "Conexión ftpsrv", "Abre ftpsrv en tu PS5 e ingresa su IP local")
    ftp_row = tk.Frame(c_ftp, bg=C_CARD)
    ftp_row.pack(fill="x", pady=(0, 10))
    tk.Label(ftp_row, text="IP de la PS5", bg=C_CARD, fg=C_MUTED, font=(ui_font, 9)).pack(side="left", padx=(0, 8))
    ip_wrap = tk.Frame(ftp_row, bg=C_BORDER, padx=1, pady=1)
    ip_wrap.pack(side="left", padx=(0, 18))
    ip_ent = tk.Entry(
        ip_wrap,
        textvariable=vars_map["ftp_host"],
        width=20,
        bg=C_INPUT,
        fg=C_TEXT,
        insertbackground=C_ACCENT,
        relief="flat",
        font=(ui_font, 10),
    )
    ip_ent.pack(ipady=5, padx=8)
    ip_ent.bind("<FocusIn>", lambda _e: ip_wrap.configure(bg=C_ACCENT))
    ip_ent.bind("<FocusOut>", lambda _e: ip_wrap.configure(bg=C_BORDER))

    tk.Label(ftp_row, text="Puerto", bg=C_CARD, fg=C_MUTED, font=(ui_font, 9)).pack(side="left", padx=(0, 8))
    pt_wrap = tk.Frame(ftp_row, bg=C_BORDER, padx=1, pady=1)
    pt_wrap.pack(side="left")
    tk.Entry(
        pt_wrap,
        textvariable=vars_map["ftp_port"],
        width=8,
        bg=C_INPUT,
        fg=C_TEXT,
        insertbackground=C_ACCENT,
        relief="flat",
        font=(ui_font, 10),
    ).pack(ipady=5, padx=8)

    for txt, bkey in (
        ("Subir shader-cache.pack (caché RADV + mvprev pre-traducido)", "ftp_shaders"),
        ("Subir / actualizar /data/totk-ps5/totk.ini", "ftp_ini"),
        ("Subir también romfs.bin (~15.86 GiB; necesario solo en la primera instalación)", "ftp_romfs"),
    ):
        tk.Checkbutton(
            c_ftp,
            text=txt,
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
        ).pack(fill="x", pady=3)

    # ---------------- PAGE 4: LAYOUT PS5 ----------------
    p_layout = tk.Frame(page_host, bg=C_BG)
    pages["layout"] = p_layout

    tk.Label(p_layout, text="Estructura Exacta en PS5", bg=C_BG, fg=C_TEXT, font=(ui_font, 15, "bold"), anchor="w").pack(
        fill="x"
    )
    tk.Label(
        p_layout,
        text="Referencia de carpetas para copiar por USB o FTP manual (ShadowMountPlus / Itemzflow).",
        bg=C_BG,
        fg=C_MUTED,
        font=(ui_font, 9),
        anchor="w",
    ).pack(fill="x", pady=(2, 12))

    lay_card = tk.Frame(p_layout, bg=C_TERM, highlightbackground=C_BORDER, highlightthickness=1, padx=8, pady=8)
    lay_card.pack(fill="both", expand=True)
    layout_box = scrolledtext.ScrolledText(
        lay_card,
        height=16,
        bg=C_TERM,
        fg="#CBD5E1",
        relief="flat",
        borderwidth=0,
        font=(mono_font, 9),
    )
    layout_box.insert("1.0", PS5_LAYOUT_TEXT)
    layout_box.config(state="disabled")
    layout_box.pack(fill="both", expand=True)

    # ---- Bottom Persistent Console & Action Bar ----
    dock = tk.Frame(main_col, bg=C_BG, padx=22, pady=12)
    dock.pack(side="bottom", fill="x")

    pbar = ttk.Progressbar(dock, mode="indeterminate", style="Zonai.Horizontal.TProgressbar")
    pbar.pack(fill="x", pady=(0, 8))

    term_card = tk.Frame(dock, bg=C_TERM, highlightbackground=C_BORDER, highlightthickness=1, padx=8, pady=6)
    term_card.pack(fill="x", pady=(0, 10))
    log_box = scrolledtext.ScrolledText(
        term_card,
        height=8,
        bg=C_TERM,
        fg="#CBD5E1",
        insertbackground=C_ACCENT,
        relief="flat",
        borderwidth=0,
        font=(mono_font, 9),
    )
    log_box.tag_config("ok", foreground=C_ACCENT)
    log_box.tag_config("info", foreground=C_BLUE)
    log_box.tag_config("gold", foreground=C_GOLD)
    log_box.tag_config("err", foreground=C_DANGER)
    log_box.pack(fill="x")

    q: queue.Queue[str | None] = queue.Queue()
    action_buttons: list[ModernButton] = []

    def set_busy(busy: bool, msg: str = "") -> None:
        for b in action_buttons:
            b.set_enabled(not busy)
        if busy:
            status_dot.configure(text=f"●  {msg or 'Trabajando...'}", fg=C_GOLD)
            pbar.start(14)
        else:
            status_dot.configure(text="●  Listo para compilar", fg=C_ACCENT)
            pbar.stop()

    def _insert_colored(line: str) -> None:
        tag = None
        low = line.lower()
        if line.startswith("[ok]") or "passed" in low or "finalizado correctamente" in low:
            tag = "ok"
        elif line.startswith("[err]") or "error" in low or "failed" in low or "fail" in low:
            tag = "err"
        elif line.startswith("[ftp]") or line.startswith(">>>"):
            tag = "gold"
        elif line.startswith("[ps5-totk]") or line.startswith("[check]"):
            tag = "info"
        if tag:
            log_box.insert("end", line, tag)
        else:
            log_box.insert("end", line)
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
                q.put(f"\n{'[ok] Proceso finalizado correctamente.' if rc == 0 else f'[err] Error (código {rc}).'}\n")
            except Exception as exc:
                q.put(f"\n[err] {exc}\n")
            finally:
                q.put(None)

        threading.Thread(target=worker, daemon=True).start()

    def _validate_inputs(*, need_ftp: bool, deploy_only: bool) -> bool:
        if not deploy_only:
            if not vars_map["game"].get().strip() and not vars_map["exefs"].get().strip():
                messagebox.showerror("Faltan archivos", "Selecciona un juego base (.xci/.nsp) o una carpeta ExeFS extraída.")
                select_page("build")
                return False
            if vars_map["game"].get().strip() and not vars_map["keys"].get().strip():
                messagebox.showerror("Falta prod.keys", "Para extraer archivos .xci/.nsp necesitas seleccionar tu Switch prod.keys.")
                select_page("build")
                return False
        if need_ftp and not vars_map["ftp_host"].get().strip():
            messagebox.showerror("Falta IP de PS5", "Ingresa la IP local de tu PS5 en la pestaña 'Enviar a PS5'.")
            select_page("ftp")
            return False
        return True

    def on_check() -> None:
        run_cmd_async([str(paths.python_bin), "-P", "-u", "-m", "builder.cli", "--check"], "Verificando Toolchain PS5...")

    def on_build() -> None:
        if not _validate_inputs(need_ftp=False, deploy_only=False):
            return
        run_cmd_async(build_cli_cmd(deploy_ftp=False), "Compilando TOTK PS5 (-O2)...")

    def on_build_and_ftp() -> None:
        if not _validate_inputs(need_ftp=True, deploy_only=False):
            return
        run_cmd_async(build_cli_cmd(deploy_ftp=True), "Compilando + Enviando a PS5...")

    def on_deploy_only() -> None:
        if not _validate_inputs(need_ftp=True, deploy_only=True):
            return
        run_cmd_async(build_cli_cmd(deploy_ftp=True, deploy_only=True), "Subiendo salida a PS5 (FTP)...")

    bar_btns = tk.Frame(dock, bg=C_BG)
    bar_btns.pack(fill="x")

    b_check = ModernButton(bar_btns, "Verificar Kit", on_check, font_spec=(ui_font, 9, "bold"), padx=14, pady=9)
    b_check.pack(side="left", padx=(0, 8))
    b_ftp = ModernButton(bar_btns, "Solo Subir FTP", on_deploy_only, font_spec=(ui_font, 9, "bold"), padx=14, pady=9)
    b_ftp.pack(side="left")

    b_both = ModernButton(
        bar_btns,
        "⚡  Compilar + Enviar a PS5",
        on_build_and_ftp,
        bg=C_BLUE,
        hover_bg=C_BLUE_HOV,
        fg="#05131C",
        border=C_BLUE,
        font_spec=(ui_font, 10, "bold"),
        padx=18,
        pady=9,
    )
    b_both.pack(side="right")
    b_build = ModernButton(
        bar_btns,
        "▶  Compilar TOTK PS5",
        on_build,
        bg=C_ACCENT,
        hover_bg=C_ACCENT_HOV,
        fg=C_ACCENT_TXT,
        border=C_ACCENT,
        font_spec=(ui_font, 10, "bold"),
        padx=18,
        pady=9,
    )
    b_build.pack(side="right", padx=(0, 10))
    action_buttons.extend([b_check, b_ftp, b_build, b_both])

    select_page("build")
    _insert_colored(f"[ps5-totk] PS5 TOTK Builder listo ({TITLE_ID}). Selecciona tu juego y presiona Compilar.\n")
    root.after(100, pump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(run_gui())
