"""PS5 Tears of the Kingdom Builder — Editorial PyQt6 UI (Obsidian × PlayStation × Zonai TOTK)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Callable

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, QSize, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QTextCharFormat, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .deploy import PS5_LAYOUT_TEXT, PS5Deployer
from .gamebanana import (
    GB_CATEGORIES,
    GBFile,
    GBMod,
    GBModDetail,
    download_and_stage_mod,
    download_ps5_icon_from_url,
    fetch_image_bytes,
    fetch_mod_detail,
    fetch_mod_files,
    match_category,
    search_mods,
)
from .pipeline import TITLE_ID, default_kit_paths

# ---- Local-only UI preferences (never stored inside the repo) ----
CONFIG_PATH = Path.home() / ".config" / "ps5-totk-builder" / "ui_prefs.json"

# ---- Pure Tears of the Kingdom (Zonai Emerald × Sky Cyan × Deep Obsidian) Palette ----
C_BG = "#080D14"
C_SIDEBAR = "#0C131E"
C_CARD = "#101926"
C_CARD_ALT = "#162234"
C_INPUT = "#0A1019"
C_BORDER = "#1F3047"
C_ZONAI_BORDER = "rgba(46, 230, 166, 0.42)"

C_ACCENT = "#2EE6A6"      # Zonai Emerald (Primary TOTK Signature)
C_GOLD = "#5CE1E6"        # Purah Pad / Sky Cyan (Secondary TOTK Accent — zero OOT sand/brown)
C_BLUE = "#38BDF8"        # PS5 Sky Blue
C_CORAL = "#FB7185"       # PS Circle
C_VIOLET = "#C084FC"      # PS Square
C_DANGER = "#F87171"

C_TEXT = "#F8FAFC"        # Crisp pure alabaster white
C_TEXT_BODY = "#E2E8F0"
C_MUTED = "#94A3B8"
C_DIM = "#64748B"

SERIF_STACK = "'Noto Serif', 'Georgia', 'Liberation Serif', 'DejaVu Serif', serif"
SANS_STACK = "'Noto Sans', 'Inter', 'Ubuntu', 'Cantarell', 'Segoe UI', sans-serif"
MONO_STACK = "'JetBrains Mono', 'DejaVu Sans Mono', 'Ubuntu Mono', monospace"

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
        "status_sub": "PS5 RADV · -O3 Zen 2 · 120 Hz\n1080p / 1440p · 38 Trofeos",
        "p_build_eyebrow": "Compilación Nativa · PlayStation 5",
        "p_build_h": "Compilar & Pre-traducir Shaders",
        "p_build_s": "Genera eboot.bin (-O3 Zen 2), íconos PlayStation y caché RADV + mvprev desde tu copia legal del juego.",
        "c_src_t": "Origen del Juego",
        "c_src_s": "Selecciona tu .xci/.nsp + prod.keys, o usa carpetas ya extraídas",
        "c_adv_t": "Opcional · Carpetas ya extraídas y caché previo",
        "lbl_game": "Juego base (.xci / .nsp)",
        "lbl_update": "Update (.nsp opcional)",
        "lbl_keys": "Switch prod.keys",
        "lbl_exefs": "ExeFS extraído",
        "lbl_romfs": "RomFS extraído",
        "lbl_shaders": "Caché de shaders previo",
        "lbl_out": "Carpeta de salida",
        "btn_browse": "Examinar",
        "c_opt_t": "Perfil PS5",
        "c_opt_s": "Ajustes verificados para 1080p / 1440p a 120 Hz (FSR 3.1.5 opcional)",
        "chk_prompts": "Íconos PlayStation por defecto (△ ○ × □, ○=Confirmar)",
        "chk_shaders": "Pre-traducir Shaders PS5 RADV + mvprev",
        "lbl_res": "Resolución",
        "lbl_hz": "Refresco (Hz)",
        "lbl_fg": "Frame Gen",
        "lbl_scale": "Escala 3D",
        "lbl_lang": "Idioma del Juego",
        "p_mods_eyebrow": "Desde GameBanana (ID 7617) y tu consola PS5",
        "p_mods_h": "Mods · Tears of the Kingdom",
        "tab_gb_browse": "Explorar",
        "tab_gb_installed": "Tus Mods",
        "search_ph": "Buscar mods en GameBanana...",
        "btn_search": "Buscar",
        "btn_install": "Instalar",
        "btn_install_ps5": "Instalar en PS5",
        "btn_zoom": "Ampliar vista previa",
        "btn_close": "Cerrar",
        "btn_open_web": "Ver página",
        "gb_loading_detail": "Cargando descripción y galería desde GameBanana...",
        "gb_no_desc": "Sin descripción disponible para este mod.",
        "btn_add_zip": "📥  Instalar .zip",
        "btn_add_dir": "📁  Instalar carpeta",
        "btn_ps5_refresh": "🔄  Actualizar PS5",
        "btn_push_mods": "▲  Subir Cola a PS5",
        "btn_delete": "Eliminar",
        "btn_remove": "Quitar",
        "ps5_mods_hdr": "Instalados en PS5 (/data/totk-ps5/mods/)",
        "local_mods_hdr": "Cola local lista para subir",
        "ps5_mods_empty": "No hay mods instalados en PS5 o aún no te has conectado.",
        "local_mods_empty": "Aún no hay mods locales en cola. Descarga desde Explorar o añade un .zip / carpeta.",
        "p_ftp_eyebrow": "Despliegue Seguro · ftpsrv",
        "p_ftp_h": "Enviar a PS5 (FTP)",
        "p_ftp_s": "Solo escribe en /data/homebrew/PPSA99199 y /data/totk-ps5. Nunca toca otros juegos ni tus partidas.",
        "c_ftp_t": "Conexión a la consola",
        "c_ftp_s": "Inicia ftpsrv en tu PS5, ingresa su IP local y conéctate",
        "lbl_ip": "IP local de la PS5",
        "lbl_port": "Puerto FTP",
        "btn_connect_ps5": "Conectar a PS5",
        "chk_ftp_sh": "Subir shader-cache.pack (caché RADV + mvprev pre-traducido)",
        "chk_ftp_ini": "Subir / actualizar /data/totk-ps5/totk.ini",
        "chk_ftp_romfs": "Subir también romfs.bin (~15.86 GiB · solo primera instalación)",
        "p_lay_eyebrow": "Identidad Visual & Estructura",
        "p_lay_h": "Layout & Arte PS5",
        "p_lay_s": "La portada personalizada (icon0.png + 4K pic0/pic1.dds) ya viene integrada. Puedes reemplazar icon0.png desde una URL.",
        "c_art_t": "Portada PS5 Personalizada",
        "c_art_s": "Descarga y convierte cualquier PNG/JPG a 512×512 para la PS5",
        "lbl_art_url": "URL de imagen (PNG / JPG)",
        "btn_art_dl": "Descargar icon0.png",
        "btn_check": "Verificar Kit",
        "btn_ftp_only": "Solo Subir FTP",
        "btn_build": "▶  Compilar TOTK PS5",
        "btn_both": "⚡  Compilar + Enviar a PS5",
        "err_no_game_t": "Faltan archivos del juego",
        "err_no_game_m": "Selecciona un juego base (.xci/.nsp) o una carpeta ExeFS extraída.",
        "err_no_keys_t": "Falta prod.keys",
        "err_no_keys_m": "Para extraer archivos .xci/.nsp necesitas seleccionar tu Switch prod.keys.",
        "welcome": f"[ps5-totk] PS5 TOTK Builder listo ({TITLE_ID}). Selecciona tu juego o conecta tu PS5.\n",
        "conn_title": "Conectar a tu PS5",
        "conn_sub": "Inicia ftpsrv en tu PS5 para ver tus mods instalados, subir archivos y desplegar directamente.",
        "conn_skip": "Continuar sin PS5",
        "conn_cancel": "Cancelar",
        "conn_btn": "Conectar ahora",
        "conn_testing": "Conectando con la PS5...",
        "conn_need_ip": "Ingresa la IP local de tu PS5 (ej. 192.168.1.50).",
        "del_confirm_t": "Eliminar mod de PS5",
        "del_confirm_m": "¿Seguro que deseas eliminar '{name}' de /data/totk-ps5/mods/ en tu PS5?",
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
        "status_sub": "PS5 RADV · -O3 Zen 2 · 120 Hz\n1080p / 1440p · 38 Trophies",
        "p_build_eyebrow": "Native Recompilation · PlayStation 5",
        "p_build_h": "Build & Pre-Translate Shaders",
        "p_build_s": "Builds eboot.bin (-O3 Zen 2), PlayStation prompts & RADV + mvprev shader cache from your legal game copy.",
        "c_src_t": "Game Source",
        "c_src_s": "Pick your .xci/.nsp + prod.keys, or point to already-extracted folders",
        "c_adv_t": "Optional · Extracted Folders & Existing Shader Cache",
        "lbl_game": "Base game (.xci / .nsp)",
        "lbl_update": "Update (.nsp optional)",
        "lbl_keys": "Switch prod.keys",
        "lbl_exefs": "Extracted ExeFS",
        "lbl_romfs": "Extracted RomFS",
        "lbl_shaders": "Existing shader cache",
        "lbl_out": "Output folder",
        "btn_browse": "Browse",
        "c_opt_t": "PS5 Profile",
        "c_opt_s": "Verified defaults for 1080p / 1440p at 120 Hz (optional FSR 3.1.5)",
        "chk_prompts": "Default PlayStation prompts (△ ○ × □, ○=Confirm)",
        "chk_shaders": "Pre-translate PS5 RADV + mvprev shaders",
        "lbl_res": "Resolution",
        "lbl_hz": "Refresh (Hz)",
        "lbl_fg": "Frame Gen",
        "lbl_scale": "3D Scale",
        "lbl_lang": "Game Language",
        "p_mods_eyebrow": "From GameBanana (ID 7617) and your PS5 console",
        "p_mods_h": "Mods · Tears of the Kingdom",
        "tab_gb_browse": "Browse",
        "tab_gb_installed": "Your Mods",
        "search_ph": "Search mods on GameBanana...",
        "btn_search": "Search",
        "btn_install": "Install",
        "btn_install_ps5": "Install to PS5",
        "btn_zoom": "Expand preview",
        "btn_close": "Close",
        "btn_open_web": "Open page",
        "gb_loading_detail": "Loading description & preview gallery from GameBanana...",
        "gb_no_desc": "No description available for this mod.",
        "btn_add_zip": "📥  Install .zip",
        "btn_add_dir": "📁  Install folder",
        "btn_ps5_refresh": "🔄  Refresh PS5",
        "btn_push_mods": "▲  Push Queue to PS5",
        "btn_delete": "Delete",
        "btn_remove": "Remove",
        "ps5_mods_hdr": "Installed on PS5 (/data/totk-ps5/mods/)",
        "local_mods_hdr": "Local Queue Ready to Push",
        "ps5_mods_empty": "No mods installed on PS5 yet, or PS5 not connected.",
        "local_mods_empty": "No local mods queued yet. Download from Browse or add a .zip / folder.",
        "p_ftp_eyebrow": "Safe Deployment · ftpsrv",
        "p_ftp_h": "Deploy to PS5 (FTP)",
        "p_ftp_s": "Only writes inside /data/homebrew/PPSA99199 and /data/totk-ps5. Never touches other titles or saves.",
        "c_ftp_t": "Console Connection",
        "c_ftp_s": "Start ftpsrv on your PS5, enter its local IP and connect",
        "lbl_ip": "PS5 Local IP",
        "lbl_port": "FTP Port",
        "btn_connect_ps5": "Connect to PS5",
        "chk_ftp_sh": "Upload shader-cache.pack (pre-translated RADV + mvprev)",
        "chk_ftp_ini": "Upload / overwrite /data/totk-ps5/totk.ini",
        "chk_ftp_romfs": "Also upload romfs.bin (~15.86 GiB · first install only)",
        "p_lay_eyebrow": "Visual Identity & Folder Layout",
        "p_lay_h": "PS5 Layout & Cover Art",
        "p_lay_s": "Custom TOTK PS5 cover art (icon0.png + 4K pic0/pic1.dds) is already embedded. Optionally replace icon0.png from a URL.",
        "c_art_t": "Custom PS5 Cover Art",
        "c_art_s": "Download and convert any PNG/JPG to 512×512 for PS5",
        "lbl_art_url": "Image URL (PNG / JPG)",
        "btn_art_dl": "Fetch icon0.png",
        "btn_check": "Verify Kit",
        "btn_ftp_only": "FTP Upload Only",
        "btn_build": "▶  Build TOTK PS5",
        "btn_both": "⚡  Build + Deploy to PS5",
        "err_no_game_t": "Missing game files",
        "err_no_game_m": "Select a base game (.xci/.nsp) or an extracted ExeFS folder.",
        "err_no_keys_t": "Missing prod.keys",
        "err_no_keys_m": "Switch prod.keys is required to extract .xci/.nsp game files.",
        "welcome": f"[ps5-totk] PS5 TOTK Builder ready ({TITLE_ID}). Pick your game dump or connect your PS5.\n",
        "conn_title": "Connect to your PS5",
        "conn_sub": "Start ftpsrv on your PS5 to view installed mods, push updates, and deploy directly.",
        "conn_skip": "Continue Offline",
        "conn_cancel": "Cancel",
        "conn_btn": "Connect Now",
        "conn_testing": "Connecting to PS5...",
        "conn_need_ip": "Enter your PS5 local IP address (e.g. 192.168.1.50).",
        "del_confirm_t": "Delete mod from PS5",
        "del_confirm_m": "Remove '{name}' from /data/totk-ps5/mods/ on your PS5?",
    },
}


def _load_prefs() -> dict:
    try:
        if CONFIG_PATH.is_file():
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_prefs(data: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def _rounded_pixmap(src: QPixmap, width: int, height: int, radius: int = 8) -> QPixmap:
    if src.isNull():
        return QPixmap()
    scaled = src.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
    x = max(0, (scaled.width() - width) // 2)
    y = max(0, (scaled.height() - height) // 2)
    cropped = scaled.copy(x, y, min(width, scaled.width()), min(height, scaled.height()))
    out = QPixmap(width, height)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, cropped)
    p.end()
    return out


# ---- Global Editorial QSS Stylesheet ----
APP_QSS = f"""
QMainWindow, QDialog, QStackedWidget, QScrollArea, QScrollArea QWidget#ScrollCanvas {{
    background-color: {C_BG};
    color: {C_TEXT_BODY};
    font-family: {SANS_STACK};
    font-size: 13px;
}}
QWidget {{
    font-family: {SANS_STACK};
    color: {C_TEXT_BODY};
}}
QLabel {{
    background: transparent;
}}
QScrollArea {{
    background-color: {C_BG};
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 4px 0px 4px 0px;
}}
QScrollBar::handle:vertical {{
    background: rgba(46, 230, 166, 0.38);
    min-height: 36px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(46, 230, 166, 0.68);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
QFrame#Sidebar {{
    background-color: {C_SIDEBAR};
    border-right: 1px solid #1C2638;
}}
QFrame#EditorialCard {{
    background-color: {C_CARD};
    border: 1px solid #1E2B40;
    border-radius: 12px;
}}
QFrame#StatusCard {{
    background-color: #0B1019;
    border: 1px solid #1E2B40;
    border-radius: 10px;
}}
QFrame#ModalFrame {{
    background-color: #0C131D;
    border: 1px solid rgba(46, 230, 166, 0.55);
    border-radius: 14px;
}}
QLabel#Eyebrow {{
    font-family: {SERIF_STACK};
    font-style: italic;
    font-size: 13px;
    color: {C_ACCENT};
}}
QLabel#PageTitle {{
    font-family: {SERIF_STACK};
    font-size: 25px;
    font-weight: 600;
    color: {C_TEXT};
}}
QLabel#PageSub {{
    font-size: 13px;
    color: {C_MUTED};
}}
QLabel#CardTitle {{
    font-family: {SERIF_STACK};
    font-size: 16px;
    font-weight: 600;
    color: {C_TEXT};
}}
QLabel#CardSub {{
    font-size: 12px;
    color: {C_MUTED};
}}
QLabel#FieldLabel {{
    font-size: 12px;
    font-weight: 600;
    color: #CBD5E1;
}}
QLineEdit {{
    background-color: {C_INPUT};
    color: #F8FAFC;
    border: 1px solid #24364F;
    border-radius: 8px;
    padding: 6px 12px;
    min-height: 24px;
    font-size: 13px;
    selection-background-color: {C_ACCENT};
    selection-color: #061610;
}}
QLineEdit:focus {{
    border: 1px solid {C_ACCENT};
    background-color: #0D1623;
}}
QComboBox {{
    background-color: {C_INPUT};
    color: #F8FAFC;
    border: 1px solid #24364F;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 24px;
}}
QComboBox:hover {{
    border: 1px solid {C_ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    width: 0px;
    height: 0px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 5px solid {C_ACCENT};
    margin-right: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: #0E1724;
    color: #F8FAFC;
    border: 1px solid {C_ACCENT};
    selection-background-color: rgba(46, 230, 166, 0.22);
    selection-color: {C_ACCENT};
    padding: 4px;
    outline: none;
}}
QCheckBox {{
    color: #E2E8F0;
    font-size: 13px;
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid #334663;
    background-color: {C_INPUT};
}}
QCheckBox::indicator:checked {{
    background-color: {C_ACCENT};
    border-color: {C_ACCENT};
}}
QPushButton {{
    background-color: {C_CARD_ALT};
    color: #E2E8F0;
    border: 1px solid #26364F;
    border-radius: 8px;
    padding: 8px 15px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: #1F2D42;
    border-color: #384E70;
}}
QPushButton:disabled {{
    background-color: #101622;
    color: #475569;
    border-color: #1A2333;
}}
QPushButton#PrimaryEmerald {{
    background-color: #2EE6A6;
    color: #051811;
    border: 1px solid #5BF2BE;
    font-weight: 700;
}}
QPushButton#PrimaryEmerald:hover {{
    background-color: #4EF0B8;
}}
QPushButton#PrimaryGold {{
    background-color: #2EE6A6;
    color: #051811;
    border: 1px solid #5BF2BE;
    font-weight: 700;
}}
QPushButton#PrimaryGold:hover {{
    background-color: #4EF0B8;
}}
QPushButton#PrimaryBlue {{
    background-color: #38BDF8;
    color: #04131D;
    border: 1px solid #75D6FC;
    font-weight: 700;
}}
QPushButton#PrimaryBlue:hover {{
    background-color: #60CCF9;
}}
QPushButton#DangerBtn {{
    background-color: rgba(248, 113, 113, 0.12);
    color: #FCA5A5;
    border: 1px solid rgba(248, 113, 113, 0.35);
}}
QPushButton#DangerBtn:hover {{
    background-color: rgba(248, 113, 113, 0.24);
}}
QPushButton#GhostBtn {{
    background: transparent;
    color: {C_MUTED};
    border: 1px solid transparent;
    padding: 7px 12px;
}}
QPushButton#GhostBtn:hover {{
    color: {C_TEXT};
    background-color: rgba(255, 255, 255, 0.05);
}}
QPushButton#SubTab {{
    background: transparent;
    color: {C_MUTED};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 14px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#SubTab:hover {{
    color: {C_TEXT};
}}
QPushButton#SubTab[active="true"] {{
    background-color: rgba(46, 230, 166, 0.14);
    color: {C_TEXT};
    border: 1px solid {C_ACCENT};
}}
QPushButton#CatTab {{
    background: transparent;
    color: {C_MUTED};
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 11px;
    font-size: 12.5px;
    font-weight: 600;
}}
QPushButton#CatTab:hover {{
    color: {C_TEXT};
}}
QPushButton#CatTab[active="true"] {{
    background-color: rgba(46, 230, 166, 0.14);
    color: {C_ACCENT};
    border: 1px solid rgba(46, 230, 166, 0.72);
}}
QPushButton#InlineInstall {{
    background: transparent;
    color: {C_ACCENT};
    border: none;
    font-size: 13px;
    font-weight: 700;
    padding: 6px 10px;
}}
QPushButton#InlineInstall:hover {{
    color: #7DF7CB;
    background-color: rgba(46, 230, 166, 0.14);
    border-radius: 6px;
}}
QPlainTextEdit#Terminal {{
    background-color: #06090F;
    color: #CBD5E1;
    border: 1px solid #1C273A;
    border-radius: 10px;
    font-family: {MONO_STACK};
    font-size: 12px;
    padding: 8px 10px;
}}
QProgressBar {{
    background-color: #131B29;
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C_ACCENT}, stop:1 {C_GOLD});
    border-radius: 2px;
}}
"""


# ---- Crisp Vector PlayStation Symbol Widget ----
class PSSymbolWidget(QWidget):
    def __init__(self, shape: str, color: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._shape = shape
        self._color = QColor(color)
        self.setFixedSize(24, 24)

    def set_color(self, color: str) -> None:
        self._color = QColor(color)
        self.update()

    def paintEvent(self, _ev) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self._shape == "triangle":
            path = QPainterPath()
            path.moveTo(12, 4.2)
            path.lineTo(20, 19.2)
            path.lineTo(4, 19.2)
            path.closeSubpath()
            p.drawPath(path)
        elif self._shape == "circle":
            p.drawEllipse(QRectF(4.5, 4.5, 15, 15))
        elif self._shape == "cross":
            p.drawLine(QPointF(5.5, 5.5), QPointF(18.5, 18.5))
            p.drawLine(QPointF(18.5, 5.5), QPointF(5.5, 18.5))
        elif self._shape == "square":
            p.drawRect(QRectF(5, 5, 14, 14))
        p.end()


# ---- Preserved PlayStation Sidebar Nav Row ----
class SidebarNavItem(QFrame):
    clicked = pyqtSignal()

    def __init__(self, shape: str, accent: str, title: str, sub: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._accent = accent
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("NavItem")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(10)

        self._bar = QFrame()
        self._bar.setFixedWidth(3)
        lay.addWidget(self._bar)

        inner = QHBoxLayout()
        inner.setContentsMargins(10, 10, 4, 10)
        inner.setSpacing(12)
        self._sym = PSSymbolWidget(shape, C_DIM)
        inner.addWidget(self._sym)

        col = QVBoxLayout()
        col.setSpacing(2)
        self._title = QLabel(title)
        self._title.setStyleSheet("font-size: 13.5px; font-weight: 700;")
        self._sub = QLabel(sub)
        self._sub.setStyleSheet("font-size: 11px;")
        col.addWidget(self._title)
        col.addWidget(self._sub)
        inner.addLayout(col, 1)
        lay.addLayout(inner, 1)
        self.set_active(False)

    def set_texts(self, title: str, sub: str) -> None:
        self._title.setText(title)
        self._sub.setText(sub)

    def set_active(self, active: bool) -> None:
        self._active = active
        bg = "#162134" if active else "transparent"
        self.setStyleSheet(f"QFrame#NavItem {{ background-color: {bg}; border-radius: 8px; }}")
        self._bar.setStyleSheet(f"background-color: {self._accent if active else 'transparent'}; border-radius: 2px;")
        self._sym.set_color(self._accent if active else C_DIM)
        self._title.setStyleSheet(f"font-size: 13.5px; font-weight: 700; color: {C_TEXT if active else C_MUTED};")
        self._sub.setStyleSheet(f"font-size: 11px; color: {C_MUTED if active else C_DIM};")

    def enterEvent(self, ev) -> None:  # noqa: N802
        if not self._active:
            self.setStyleSheet("QFrame#NavItem { background-color: #121B2B; border-radius: 8px; }")
        super().enterEvent(ev)

    def leaveEvent(self, ev) -> None:  # noqa: N802
        if not self._active:
            self.setStyleSheet("QFrame#NavItem { background-color: transparent; border-radius: 8px; }")
        super().leaveEvent(ev)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(ev)


# ---- Background Worker Threads ----
class FnWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn: Callable[[], object], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class CommandWorker(QThread):
    line = pyqtSignal(str)
    finished_rc = pyqtSignal(int)

    def __init__(self, cmd: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._cmd = cmd

    def run(self) -> None:
        try:
            proc = subprocess.Popen(self._cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            assert proc.stdout is not None
            for ln in proc.stdout:
                self.line.emit(ln)
            self.finished_rc.emit(proc.wait())
        except Exception as exc:
            self.line.emit(f"[err] {exc}\n")
            self.finished_rc.emit(1)


class ThumbBatchWorker(QThread):
    thumb_ready = pyqtSignal(str, bytes)

    def __init__(self, urls: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._urls = urls
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        def _fetch(u: str) -> tuple[str, bytes | None]:
            if self._cancelled:
                return u, None
            return u, fetch_image_bytes(u, timeout=5)

        try:
            with ThreadPoolExecutor(max_workers=6) as pool:
                for url, raw in pool.map(_fetch, self._urls):
                    if self._cancelled:
                        break
                    if raw:
                        self.thumb_ready.emit(url, raw)
        except RuntimeError:
            pass


# ---- PS5 Connection Modal (Startup + On-Demand) ----
class PS5ConnectDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        tr: Callable[[str], str],
        initial_host: str,
        initial_port: str,
        *,
        startup: bool = False,
    ) -> None:
        super().__init__(parent)
        self._tr = tr
        self.connected_host = ""
        self.connected_port = 2121
        self.ps5_mods: list[str] = []
        self._worker: FnWorker | None = None

        self.setWindowTitle(tr("conn_title"))
        self.setModal(True)
        self.setFixedWidth(480)

        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(14, 14, 14, 14)

        frame = QFrame()
        frame.setObjectName("ModalFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)

        eyebrow = QLabel("PLAYSTATION 5 · FTPSRV")
        eyebrow.setStyleSheet(f"font-size: 11px; font-weight: 700; letter-spacing: 1.5px; color: {C_ACCENT};")
        lay.addWidget(eyebrow)

        title = QLabel(tr("conn_title"))
        title.setStyleSheet(f"font-family: {SERIF_STACK}; font-size: 22px; font-weight: 600; color: {C_TEXT};")
        lay.addWidget(title)

        sub = QLabel(tr("conn_sub"))
        sub.setWordWrap(True)
        sub.setStyleSheet(f"font-size: 13px; color: {C_MUTED};")
        lay.addWidget(sub)

        row = QHBoxLayout()
        row.setSpacing(10)
        col_ip = QVBoxLayout()
        col_ip.setSpacing(5)
        lbl_ip = QLabel(tr("lbl_ip"))
        lbl_ip.setObjectName("FieldLabel")
        self.ed_ip = QLineEdit(initial_host)
        self.ed_ip.setMinimumHeight(40)
        self.ed_ip.setPlaceholderText("192.168.1.50")
        self.ed_ip.returnPressed.connect(self._do_connect)
        col_ip.addWidget(lbl_ip)
        col_ip.addWidget(self.ed_ip)

        col_pt = QVBoxLayout()
        col_pt.setSpacing(5)
        lbl_pt = QLabel(tr("lbl_port"))
        lbl_pt.setObjectName("FieldLabel")
        self.ed_port = QLineEdit(initial_port or "2121")
        self.ed_port.setFixedWidth(96)
        self.ed_port.setMinimumHeight(40)
        self.ed_port.returnPressed.connect(self._do_connect)
        col_pt.addWidget(lbl_pt)
        col_pt.addWidget(self.ed_port)

        row.addLayout(col_ip, 1)
        row.addLayout(col_pt)
        lay.addLayout(row)

        self.lbl_msg = QLabel("")
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet(f"font-size: 12.5px; color: {C_GOLD}; min-height: 20px;")
        lay.addWidget(self.lbl_msg)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)
        self.btn_skip = QPushButton(tr("conn_skip") if startup else tr("conn_cancel"))
        self.btn_skip.setObjectName("GhostBtn")
        self.btn_skip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_skip.clicked.connect(self.reject)
        btns.addWidget(self.btn_skip)

        self.btn_go = QPushButton(f"🔌  {tr('conn_btn')}")
        self.btn_go.setObjectName("PrimaryEmerald")
        self.btn_go.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_go.clicked.connect(self._do_connect)
        btns.addWidget(self.btn_go)
        lay.addLayout(btns)

        root_lay.addWidget(frame)
        self.ed_ip.setFocus()

    def _do_connect(self) -> None:
        host = self.ed_ip.text().strip()
        if not host:
            self.lbl_msg.setStyleSheet(f"font-size: 12.5px; color: {C_DANGER};")
            self.lbl_msg.setText(self._tr("conn_need_ip"))
            return
        port = int(self.ed_port.text().strip() or "2121")
        self.btn_go.setEnabled(False)
        self.lbl_msg.setStyleSheet(f"font-size: 12.5px; color: {C_GOLD};")
        self.lbl_msg.setText(self._tr("conn_testing"))

        def _work() -> list[str]:
            dep = PS5Deployer(host, port, timeout=6, log_fn=lambda _m: None)
            try:
                return dep.list_dirs("/data/totk-ps5/mods")
            finally:
                dep.close()

        self._worker = FnWorker(_work, self)
        self._worker.done.connect(lambda dirs: self._on_ok(host, port, dirs))
        self._worker.failed.connect(self._on_fail)
        self._worker.start()

    def _on_ok(self, host: str, port: int, dirs: list[str]) -> None:
        self.connected_host = host
        self.connected_port = port
        self.ps5_mods = list(dirs)
        self.accept()

    def _on_fail(self, err: str) -> None:
        self.btn_go.setEnabled(True)
        self.lbl_msg.setStyleSheet(f"font-size: 12.5px; color: {C_DANGER};")
        self.lbl_msg.setText(f"Error FTP: {err}")


# ---- Full-Screen Gallery Zoom Dialog ----
class GalleryLightboxDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, urls: list[str], start_idx: int = 0) -> None:
        super().__init__(parent)
        self._urls = urls
        self._idx = start_idx
        self._workers: list[FnWorker] = []

        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(960, 620)
        self.setStyleSheet("QDialog { background-color: #05080D; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)

        self.lbl_img = QLabel("Cargando vista previa...")
        self.lbl_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_img.setStyleSheet(f"color: {C_MUTED}; font-size: 14px; background-color: #0A0F17; border-radius: 10px;")
        self.lbl_img.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay.addWidget(self.lbl_img, 1)

        bar = QHBoxLayout()
        if len(urls) > 1:
            b_prev = QPushButton("◀  Anterior")
            b_prev.setCursor(Qt.CursorShape.PointingHandCursor)
            b_prev.clicked.connect(lambda: self._load(self._idx - 1))
            b_next = QPushButton("Siguiente  ▶")
            b_next.setCursor(Qt.CursorShape.PointingHandCursor)
            b_next.clicked.connect(lambda: self._load(self._idx + 1))
            bar.addWidget(b_prev)
            bar.addWidget(b_next)
        self.lbl_pos = QLabel("")
        self.lbl_pos.setStyleSheet(f"color: {C_GOLD}; font-size: 13px; font-weight: 600;")
        bar.addWidget(self.lbl_pos)
        bar.addStretch(1)
        b_close = QPushButton("Cerrar")
        b_close.setCursor(Qt.CursorShape.PointingHandCursor)
        b_close.clicked.connect(self.accept)
        bar.addWidget(b_close)
        lay.addLayout(bar)

        self._load(start_idx)

    def _load(self, idx: int) -> None:
        if not self._urls:
            return
        self._idx = idx % len(self._urls)
        self.lbl_pos.setText(f"{self._idx + 1} / {len(self._urls)}")
        url = self._urls[self._idx]
        self.lbl_img.setPixmap(QPixmap())
        self.lbl_img.setText("Cargando...")

        w = FnWorker(lambda: fetch_image_bytes(url, timeout=8), self)
        w.done.connect(self._on_img)
        self._workers.append(w)
        w.start()

    def _on_img(self, raw: object) -> None:
        if isinstance(raw, bytes) and raw:
            pm = QPixmap()
            if pm.loadFromData(raw):
                self.lbl_img.setText("")
                self.lbl_img.setPixmap(
                    pm.scaled(
                        max(400, self.lbl_img.width() - 20),
                        max(300, self.lbl_img.height() - 20),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )


# ---- Editorial Mod Detail Modal (Directly modeled on oot-din Image 2) ----
class ModDetailDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        mod: GBMod,
        tr: Callable[[str], str],
        is_es: bool,
        cached_detail: GBModDetail | None,
        on_detail_loaded: Callable[[GBModDetail], None],
        on_install: Callable[[GBMod, GBFile | None], None],
    ) -> None:
        super().__init__(parent)
        self._mod = mod
        self._tr = tr
        self._is_es = is_es
        self._on_detail_loaded = on_detail_loaded
        self._on_install = on_install
        self._files: list[GBFile] = []
        self._gallery_urls: list[str] = []
        self._workers: list[FnWorker] = []

        self.setWindowTitle(f"{mod.name} — Tears of the Kingdom")
        self.setModal(True)
        self.resize(780, 620)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(14, 14, 14, 14)

        frame = QFrame()
        frame.setObjectName("ModalFrame")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(12)

        lbl_title = QLabel(mod.name)
        lbl_title.setWordWrap(True)
        lbl_title.setStyleSheet(f"font-family: {SERIF_STACK}; font-size: 25px; font-weight: 600; color: {C_TEXT};")
        lay.addWidget(lbl_title)

        views_lbl = "vistas" if is_es else "views"
        self.lbl_meta = QLabel(f"{mod.author} · {mod.category}  ·  ♥ {mod.likes:,} · {mod.views:,} {views_lbl}")
        self.lbl_meta.setStyleSheet(f"font-size: 13.5px; color: {C_MUTED};")
        lay.addWidget(self.lbl_meta)

        self.cb_files = QComboBox()
        self.cb_files.addItem("Cargando archivos..." if is_es else "Loading files...")
        self.cb_files.setMinimumHeight(38)
        lay.addWidget(self.cb_files)

        prev_row = QHBoxLayout()
        prev_row.setSpacing(16)
        self.lbl_thumb = QLabel("...")
        self.lbl_thumb.setFixedSize(210, 118)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lbl_thumb.setStyleSheet(f"background-color: {C_INPUT}; border: 1px solid {C_GOLD}; border-radius: 8px; color: {C_DIM};")
        self.lbl_thumb.mouseReleaseEvent = lambda _e: self._open_zoom()  # type: ignore[method-assign]
        prev_row.addWidget(self.lbl_thumb)

        prev_row.addStretch(1)
        self.btn_zoom = QPushButton(tr("btn_zoom"))
        self.btn_zoom.setObjectName("GhostBtn")
        self.btn_zoom.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_zoom.setStyleSheet(f"QPushButton {{ background: transparent; color: {C_TEXT_BODY}; font-size: 13.5px; border: none; padding: 8px 14px; }} QPushButton:hover {{ color: {C_GOLD}; }}")
        self.btn_zoom.clicked.connect(self._open_zoom)
        prev_row.addWidget(self.btn_zoom)
        lay.addLayout(prev_row)

        self.desc = QPlainTextEdit()
        self.desc.setReadOnly(True)
        self.desc.setPlainText(tr("gb_loading_detail"))
        self.desc.setStyleSheet(
            f"QPlainTextEdit {{ background: transparent; color: #ECE7DA; border: none; font-family: {SANS_STACK}; font-size: 14px; line-height: 1.5; padding: 4px 2px; }}"
        )
        lay.addWidget(self.desc, 1)

        foot = QHBoxLayout()
        foot.setSpacing(12)
        foot.addStretch(1)

        btn_close = QPushButton(tr("btn_close"))
        btn_close.setObjectName("GhostBtn")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.reject)
        foot.addWidget(btn_close)

        btn_web = QPushButton(tr("btn_open_web"))
        btn_web.setObjectName("GhostBtn")
        btn_web.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_web.clicked.connect(lambda: webbrowser.open(mod.profile_url))
        foot.addWidget(btn_web)

        self.btn_inst = QPushButton(tr("btn_install_ps5"))
        self.btn_inst.setObjectName("PrimaryGold")
        self.btn_inst.setMinimumHeight(40)
        self.btn_inst.setMinimumWidth(148)
        self.btn_inst.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_inst.clicked.connect(self._install_clicked)
        foot.addWidget(self.btn_inst)
        lay.addLayout(foot)

        outer.addWidget(frame)

        if cached_detail is not None:
            self._apply_detail(cached_detail)
        else:
            w = FnWorker(lambda: fetch_mod_detail(mod.mod_id, wip=mod.wip), self)
            w.done.connect(self._on_fetched)
            w.failed.connect(lambda _e: self.desc.setPlainText(mod.summary or tr("gb_no_desc")))
            self._workers.append(w)
            w.start()

    def _on_fetched(self, detail: object) -> None:
        if isinstance(detail, GBModDetail):
            self._on_detail_loaded(detail)
            self._apply_detail(detail)

    def _apply_detail(self, detail: GBModDetail) -> None:
        views_lbl = "vistas" if self._is_es else "views"
        author = detail.author or self._mod.author
        cat = detail.category or self._mod.category
        likes = detail.likes or self._mod.likes
        views = detail.views or self._mod.views
        self.lbl_meta.setText(f"{author} · {cat}  ·  ♥ {likes:,} · {views:,} {views_lbl}")

        self._files = list(detail.files)
        self.cb_files.clear()
        if self._files:
            for f in self._files:
                mb = f.size_bytes / (1024 * 1024)
                self.cb_files.addItem(f"{f.filename} ({mb:.1f} MB)")
        else:
            self.cb_files.addItem("Sin archivos descargables" if self._is_es else "No downloadable files")

        self.desc.setPlainText(detail.description or self._mod.summary or self._tr("gb_no_desc"))

        urls = list(detail.gallery_urls)
        if not urls and self._mod.full_img_url:
            urls.append(self._mod.full_img_url)
        elif not urls and self._mod.thumb_url:
            urls.append(self._mod.thumb_url)
        self._gallery_urls = urls
        if urls:
            w = FnWorker(lambda u=urls[0]: fetch_image_bytes(u, timeout=6), self)
            w.done.connect(self._on_thumb)
            self._workers.append(w)
            w.start()

    def _on_thumb(self, raw: object) -> None:
        if isinstance(raw, bytes) and raw:
            pm = QPixmap()
            if pm.loadFromData(raw):
                self.lbl_thumb.setText("")
                self.lbl_thumb.setPixmap(_rounded_pixmap(pm, 208, 116, radius=7))

    def _open_zoom(self) -> None:
        urls = self._gallery_urls or ([self._mod.full_img_url] if self._mod.full_img_url else [])
        if urls:
            GalleryLightboxDialog(self, self._mod.name, urls, 0).exec()

    def _install_clicked(self) -> None:
        chosen = None
        idx = self.cb_files.currentIndex()
        if self._files and 0 <= idx < len(self._files):
            chosen = self._files[idx]
        self.accept()
        self._on_install(self._mod, chosen)


# ---- Clean 2-Column Editorial Mod Row (Modeled on oot-din Image 1) ----
class EditorialModRow(QFrame):
    open_detail = pyqtSignal(object)
    install_clicked = pyqtSignal(object)

    def __init__(self, mod: GBMod, install_label: str, cached_pm: QPixmap | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.mod = mod
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setObjectName("ModRow")
        self.setStyleSheet(
            "QFrame#ModRow { background: transparent; border: none; border-bottom: 1px solid #1A2333; }"
            "QFrame#ModRow:hover { background-color: rgba(255, 255, 255, 0.035); }"
        )

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 10)
        lay.setSpacing(14)

        self.lbl_thumb = QLabel()
        self.lbl_thumb.setFixedSize(96, 54)
        self.lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_thumb.setStyleSheet(f"background-color: {C_INPUT}; border: 1px solid #1E293B; border-radius: 6px; color: {C_DIM}; font-size: 10px;")
        if cached_pm is not None:
            self.lbl_thumb.setPixmap(cached_pm)
        else:
            self.lbl_thumb.setText("TOTK")
        lay.addWidget(self.lbl_thumb)

        col = QVBoxLayout()
        col.setSpacing(3)
        short_name = mod.name if len(mod.name) <= 34 else mod.name[:33].rstrip() + "…"
        lbl_name = QLabel(short_name)
        lbl_name.setToolTip(mod.name)
        lbl_name.setWordWrap(False)
        lbl_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lbl_name.setStyleSheet(f"font-family: {SERIF_STACK}; font-size: 14px; font-weight: 600; color: {C_TEXT};")
        meta_txt = f"{mod.author} · {mod.category} · ★ {mod.likes}"
        short_meta = meta_txt if len(meta_txt) <= 38 else meta_txt[:37].rstrip() + "…"
        lbl_meta = QLabel(short_meta)
        lbl_meta.setToolTip(meta_txt)
        lbl_meta.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        lbl_meta.setStyleSheet(f"font-size: 12px; color: {C_MUTED};")
        col.addWidget(lbl_name)
        col.addWidget(lbl_meta)
        lay.addLayout(col, 1)

        btn_inst = QPushButton(install_label)
        btn_inst.setObjectName("InlineInstall")
        btn_inst.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_inst.clicked.connect(lambda: self.install_clicked.emit(self.mod))
        lay.addWidget(btn_inst)

    def set_thumb(self, pm: QPixmap) -> None:
        self.lbl_thumb.setText("")
        self.lbl_thumb.setPixmap(pm)

    def mouseReleaseEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self.open_detail.emit(self.mod)
        super().mouseReleaseEvent(ev)

    def mouseDoubleClickEvent(self, ev) -> None:  # noqa: N802
        if ev.button() == Qt.MouseButton.LeftButton:
            self.open_detail.emit(self.mod)
        super().mouseDoubleClickEvent(ev)


# ---- Main Application Window ----
class PS5TotkWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.paths = default_kit_paths()
        self.prefs = _load_prefs()
        self.lang = self.prefs.get("lang", "es")
        if self.lang not in ("es", "en"):
            self.lang = "es"

        self.ps5_connected = False
        self.ps5_mods: list[str] = []
        self.local_mods: list[str] = []
        self.gb_all_results: list[GBMod] = []
        self.gb_detail_cache: dict[tuple[int, bool], GBModDetail] = {}
        self.gb_thumb_cache: dict[str, QPixmap] = {}
        self.gb_rows_by_url: dict[str, list[EditorialModRow]] = {}
        self.gb_cat = "all"
        self.active_workers: list[QThread] = []
        self._thumb_worker: ThumbBatchWorker | None = None
        self._cmd_worker: CommandWorker | None = None
        self._tr_bindings: list[tuple[QObject, str]] = []

        self.setMinimumSize(1160, 820)
        self.resize(1380, 940)

        icon_path = self.paths.assets_sce_sys / "icon0.png"
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Root layout: top 2px Zonai stripe + (Sidebar | Main Column)
        central = QWidget()
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        accent_bar = QFrame()
        accent_bar.setFixedHeight(2)
        accent_bar.setStyleSheet(f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C_ACCENT}, stop:0.5 {C_GOLD}, stop:1 {C_BLUE});")
        root_v.addWidget(accent_bar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root_v.addLayout(body, 1)

        # ---- LEFT PLAYSTATION SIDEBAR (Preserved Layout, Crisp PyQt6) ----
        self.sidebar = QFrame()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(274)
        sb_lay = QVBoxLayout(self.sidebar)
        sb_lay.setContentsMargins(14, 18, 14, 16)
        sb_lay.setSpacing(12)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        self.lbl_logo = QLabel()
        self.lbl_logo.setFixedSize(50, 50)
        if icon_path.is_file():
            self.lbl_logo.setPixmap(_rounded_pixmap(QPixmap(str(icon_path)), 50, 50, radius=11))
        brand_row.addWidget(self.lbl_logo)

        b_col = QVBoxLayout()
        b_col.setSpacing(2)
        b_t = QLabel("TOTK PS5")
        b_t.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {C_TEXT};")
        b_s = QLabel(f"{TITLE_ID} · PS5")
        b_s.setStyleSheet(f"font-size: 11px; font-weight: 700; color: {C_ACCENT}; letter-spacing: 0.8px;")
        b_col.addWidget(b_t)
        b_col.addWidget(b_s)
        brand_row.addLayout(b_col, 1)
        sb_lay.addLayout(brand_row)

        # ES | EN Pill Toggle
        lang_pill = QFrame()
        lang_pill.setStyleSheet(f"background-color: {C_INPUT}; border: 1px solid {C_BORDER}; border-radius: 7px;")
        lp_lay = QHBoxLayout(lang_pill)
        lp_lay.setContentsMargins(2, 2, 2, 2)
        lp_lay.setSpacing(2)
        self.btn_es = QPushButton("Español (ES)")
        self.btn_en = QPushButton("English (EN)")
        for b_l, code in ((self.btn_es, "es"), (self.btn_en, "en")):
            b_l.setCursor(Qt.CursorShape.PointingHandCursor)
            b_l.setFixedHeight(30)
            b_l.clicked.connect(lambda _checked=False, c=code: self.apply_language(c))
            lp_lay.addWidget(b_l)
        sb_lay.addWidget(lang_pill)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #1D283A;")
        sb_lay.addWidget(sep)

        # Navigation (△ ○ × □)
        self.nav_items: dict[str, SidebarNavItem] = {}
        nav_specs = [
            ("build", "triangle", C_ACCENT, "nav_build_t", "nav_build_s"),
            ("mods", "circle", C_CORAL, "nav_mods_t", "nav_mods_s"),
            ("ftp", "cross", C_BLUE, "nav_ftp_t", "nav_ftp_s"),
            ("layout", "square", C_VIOLET, "nav_layout_t", "nav_layout_s"),
        ]
        for key, shape, color, tk_k, sk_k in nav_specs:
            item = SidebarNavItem(shape, color, self.tr_key(tk_k), self.tr_key(sk_k))
            item.clicked.connect(lambda k=key: self.select_page(k))
            sb_lay.addWidget(item)
            self.nav_items[key] = item

        sb_lay.addStretch(1)

        # Bottom Status Card
        st_card = QFrame()
        st_card.setObjectName("StatusCard")
        st_lay = QVBoxLayout(st_card)
        st_lay.setContentsMargins(14, 12, 14, 12)
        st_lay.setSpacing(6)
        self.lbl_status_dot = QLabel(self.tr_key("status_ready"))
        self.lbl_status_dot.setStyleSheet(f"font-size: 12.5px; font-weight: 700; color: {C_ACCENT};")
        self.lbl_status_sub = QLabel(self.tr_key("status_sub"))
        self.lbl_status_sub.setStyleSheet(f"font-size: 11px; color: {C_DIM};")
        self.btn_sb_conn = QPushButton(f"🔌  {self.tr_key('btn_connect_ps5')}")
        self.btn_sb_conn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sb_conn.setStyleSheet(
            f"QPushButton {{ background-color: rgba(56, 189, 248, 0.12); color: {C_BLUE}; border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 6px; padding: 5px 10px; font-size: 11.5px; font-weight: 700; }}"
            "QPushButton:hover { background-color: rgba(56, 189, 248, 0.22); }"
        )
        self.btn_sb_conn.clicked.connect(lambda: self.open_ps5_connect_modal(startup=False))
        st_lay.addWidget(self.lbl_status_dot)
        st_lay.addWidget(self.lbl_status_sub)
        st_lay.addWidget(self.btn_sb_conn)
        sb_lay.addWidget(st_card)

        body.addWidget(self.sidebar)

        # ---- MAIN WORKSPACE COLUMN ----
        main_w = QWidget()
        main_lay = QVBoxLayout(main_w)
        main_lay.setContentsMargins(0, 0, 0, 0)
        main_lay.setSpacing(0)
        body.addWidget(main_w, 1)

        self.stack = QStackedWidget()
        main_lay.addWidget(self.stack, 1)

        self._page_indices: dict[str, int] = {}
        self._build_page_build()
        self._build_page_mods()
        self._build_page_ftp()
        self._build_page_layout()

        # ---- BOTTOM CONSOLE & ACTION DOCK (hidden on Mods page for full browser height) ----
        self.dock = QFrame()
        self.dock.setStyleSheet("QFrame { background-color: #090D14; border-top: 1px solid #1A2436; }")
        dock_lay = QVBoxLayout(self.dock)
        dock_lay.setContentsMargins(28, 12, 28, 14)
        dock_lay.setSpacing(10)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 1)
        self.pbar.setValue(0)
        self.pbar.setTextVisible(False)
        dock_lay.addWidget(self.pbar)

        self.log_box = QPlainTextEdit()
        self.log_box.setObjectName("Terminal")
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(84)
        dock_lay.addWidget(self.log_box)

        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)
        self.btn_check = self._bind_tr(QPushButton(), "btn_check")
        self.btn_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check.clicked.connect(
            lambda: self.run_cmd_async([str(self.paths.python_bin), "-P", "-u", "-m", "builder.cli", "--check"], self.tr_key("btn_check"))
        )
        self.btn_ftp_only = self._bind_tr(QPushButton(), "btn_ftp_only")
        self.btn_ftp_only.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ftp_only.clicked.connect(self._run_ftp_only)

        self.btn_build = self._bind_tr(QPushButton(), "btn_build")
        self.btn_build.setObjectName("PrimaryEmerald")
        self.btn_build.setMinimumHeight(40)
        self.btn_build.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_build.clicked.connect(self._run_build_only)

        self.btn_both = self._bind_tr(QPushButton(), "btn_both")
        self.btn_both.setObjectName("PrimaryBlue")
        self.btn_both.setMinimumHeight(40)
        self.btn_both.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_both.clicked.connect(self._run_build_and_ftp)

        btn_bar.addWidget(self.btn_check)
        btn_bar.addWidget(self.btn_ftp_only)
        btn_bar.addStretch(1)
        btn_bar.addWidget(self.btn_build)
        btn_bar.addWidget(self.btn_both)
        dock_lay.addLayout(btn_bar)
        main_lay.addWidget(self.dock)

        self.action_buttons = [self.btn_check, self.btn_ftp_only, self.btn_build, self.btn_both]

        self.apply_language(self.lang)
        self.select_page("build")
        self.append_log(self.tr_key("welcome"))

        # Prompt to connect to PS5 right after window opens
        QTimer.singleShot(280, lambda: self.open_ps5_connect_modal(startup=True))

    # ---- Helpers ----
    def tr_key(self, key: str) -> str:
        return I18N[self.lang].get(key, key)

    def _bind_tr(self, widget: QObject, key: str):
        self._tr_bindings.append((widget, key))
        if hasattr(widget, "setText"):
            widget.setText(self.tr_key(key))  # type: ignore[attr-defined]
        return widget

    def _wrap_scroll_page(self, max_width: int = 1040) -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer = QWidget()
        outer.setObjectName("ScrollCanvas")
        outer_lay = QHBoxLayout(outer)
        outer_lay.setContentsMargins(28, 16, 28, 16)
        outer_lay.setSpacing(0)

        content = QWidget()
        if max_width > 0:
            content.setMaximumWidth(max_width)
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        outer_lay.addWidget(content, 1)
        if max_width > 0:
            outer_lay.addStretch(0)
        scroll.setWidget(outer)
        return scroll, lay

    def _make_card(self, title_key: str, sub_key: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("EditorialCard")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(10)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        t = self._bind_tr(QLabel(), title_key)
        t.setObjectName("CardTitle")
        s = self._bind_tr(QLabel(), sub_key)
        s.setObjectName("CardSub")
        hdr.addWidget(t)
        hdr.addWidget(s, 1)
        lay.addLayout(hdr)
        return card, lay

    def _make_path_field(self, label_key: str, *, default: str = "", pick_dir: bool = False, filt: str = "") -> tuple[QWidget, QLineEdit]:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        lbl = self._bind_tr(QLabel(), label_key)
        lbl.setObjectName("FieldLabel")
        lay.addWidget(lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        ed = QLineEdit(default)
        ed.setMinimumHeight(38)
        btn = self._bind_tr(QPushButton(), "btn_browse")
        btn.setMinimumHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        def _pick() -> None:
            if pick_dir:
                p = QFileDialog.getExistingDirectory(self, self.tr_key(label_key), ed.text() or str(Path.home()))
            else:
                p, _ = QFileDialog.getOpenFileName(self, self.tr_key(label_key), ed.text() or str(Path.home()), filt or "All Files (*)")
            if p:
                ed.setText(p)

        btn.clicked.connect(_pick)
        row.addWidget(ed, 1)
        row.addWidget(btn)
        lay.addLayout(row)
        return box, ed

    # ================ PAGE 1: BUILD & SHADERS ================
    def _build_page_build(self) -> None:
        scroll, lay = self._wrap_scroll_page(max_width=1060)

        ey = self._bind_tr(QLabel(), "p_build_eyebrow")
        ey.setObjectName("Eyebrow")
        h = self._bind_tr(QLabel(), "p_build_h")
        h.setObjectName("PageTitle")
        sub = self._bind_tr(QLabel(), "p_build_s")
        sub.setObjectName("PageSub")
        sub.setWordWrap(True)
        lay.addWidget(ey)
        lay.addWidget(h)
        lay.addWidget(sub)

        # Card 1: Game Source (clean 2-column grid instead of stretched 1600px rows!)
        c_src, src_lay = self._make_card("c_src_t", "c_src_s")
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(12)

        w_game, self.ed_game = self._make_path_field("lbl_game", filt="Switch Images (*.xci *.nsp);;All Files (*)")
        w_upd, self.ed_update = self._make_path_field("lbl_update", filt="Switch Updates (*.nsp);;All Files (*)")
        w_keys, self.ed_keys = self._make_path_field("lbl_keys", filt="Key Files (*.keys);;All Files (*)")
        w_out, self.ed_out = self._make_path_field("lbl_out", default=self.prefs.get("out", str(Path.home() / "TOTK-PS5-Out")), pick_dir=True)

        grid.addWidget(w_game, 0, 0)
        grid.addWidget(w_upd, 0, 1)
        grid.addWidget(w_keys, 1, 0)
        grid.addWidget(w_out, 1, 1)
        src_lay.addLayout(grid)

        # Divider + optional extracted folders
        div = QFrame()
        div.setFixedHeight(1)
        div.setStyleSheet("background-color: #1D293D;")
        src_lay.addWidget(div)

        adv_lbl = self._bind_tr(QLabel(), "c_adv_t")
        adv_lbl.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {C_GOLD};")
        src_lay.addWidget(adv_lbl)

        grid2 = QGridLayout()
        grid2.setHorizontalSpacing(18)
        grid2.setVerticalSpacing(10)
        w_exefs, self.ed_exefs = self._make_path_field("lbl_exefs", pick_dir=True)
        w_romfs, self.ed_romfs = self._make_path_field("lbl_romfs", pick_dir=True)
        w_sh, self.ed_shaders = self._make_path_field("lbl_shaders", pick_dir=True)
        grid2.addWidget(w_exefs, 0, 0)
        grid2.addWidget(w_romfs, 0, 1)
        grid2.addWidget(w_sh, 1, 0, 1, 2)
        src_lay.addLayout(grid2)
        lay.addWidget(c_src)

        # Card 2: PS5 Profile
        c_opt, opt_lay = self._make_card("c_opt_t", "c_opt_s")
        chk_row = QHBoxLayout()
        chk_row.setSpacing(24)
        self.chk_prompts = self._bind_tr(QCheckBox(), "chk_prompts")
        self.chk_prompts.setChecked(True)
        self.chk_shaders = self._bind_tr(QCheckBox(), "chk_shaders")
        self.chk_shaders.setChecked(True)
        chk_row.addWidget(self.chk_prompts)
        chk_row.addWidget(self.chk_shaders)
        chk_row.addStretch(1)
        opt_lay.addLayout(chk_row)

        p_grid = QGridLayout()
        p_grid.setHorizontalSpacing(14)
        self.cb_res = QComboBox()
        self.cb_res.addItems(["2560x1440", "1920x1080", "3840x2160"])
        self.cb_hz = QComboBox()
        self.cb_hz.addItems(["120", "60"])
        self.cb_fg = QComboBox()
        self.cb_fg.addItems(["fsr3", "off"])
        self.cb_scale = QComboBox()
        self.cb_scale.addItems(["75", "67", "game", "100"])
        self.cb_lang = QComboBox()
        self.cb_lang.addItems(["es-419", "es-ES", "en-US", "fr-FR", "de-DE", "ja-JP"])

        for col_idx, (lk, cb) in enumerate(
            [
                ("lbl_res", self.cb_res),
                ("lbl_hz", self.cb_hz),
                ("lbl_fg", self.cb_fg),
                ("lbl_scale", self.cb_scale),
                ("lbl_lang", self.cb_lang),
            ]
        ):
            lbl = self._bind_tr(QLabel(), lk)
            lbl.setObjectName("FieldLabel")
            p_grid.addWidget(lbl, 0, col_idx)
            p_grid.addWidget(cb, 1, col_idx)
        opt_lay.addLayout(p_grid)
        lay.addWidget(c_opt)
        lay.addStretch(1)

        self._page_indices["build"] = self.stack.addWidget(scroll)

    # ================ PAGE 2: EDITORIAL MODS & GAMEBANANA ================
    def _build_page_mods(self) -> None:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(32, 22, 32, 16)
        lay.setSpacing(12)

        # Header + Search on right
        hdr = QHBoxLayout()
        hdr.setSpacing(16)
        hdr_l = QVBoxLayout()
        hdr_l.setSpacing(2)
        ey = self._bind_tr(QLabel(), "p_mods_eyebrow")
        ey.setObjectName("Eyebrow")
        ht = self._bind_tr(QLabel(), "p_mods_h")
        ht.setObjectName("PageTitle")
        hdr_l.addWidget(ey)
        hdr_l.addWidget(ht)
        hdr.addLayout(hdr_l, 1)

        search_row = QHBoxLayout()
        search_row.setSpacing(8)
        self.ed_gb_query = QLineEdit()
        self.ed_gb_query.setMinimumWidth(250)
        self.ed_gb_query.setMinimumHeight(38)
        self.ed_gb_query.setPlaceholderText(self.tr_key("search_ph"))
        self.ed_gb_query.returnPressed.connect(self.run_gb_search)
        self.cb_gb_sort = QComboBox()
        self.cb_gb_sort.addItems(["default", "new", "updated"])
        self.cb_gb_sort.setFixedWidth(112)
        self.btn_gb_search = self._bind_tr(QPushButton(), "btn_search")
        self.btn_gb_search.setObjectName("PrimaryEmerald")
        self.btn_gb_search.setMinimumHeight(38)
        self.btn_gb_search.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_gb_search.clicked.connect(self.run_gb_search)
        search_row.addWidget(self.ed_gb_query)
        search_row.addWidget(self.cb_gb_sort)
        search_row.addWidget(self.btn_gb_search)
        hdr.addLayout(search_row)
        lay.addLayout(hdr)

        # Sub-tabs: Explorar | Tus Mods (PS5/Local)
        sub_row = QHBoxLayout()
        sub_row.setSpacing(10)
        self.btn_sub_browse = QPushButton(self.tr_key("tab_gb_browse"))
        self.btn_sub_browse.setObjectName("SubTab")
        self.btn_sub_browse.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sub_browse.clicked.connect(lambda: self._select_mods_sub(0))

        self.btn_sub_inst = QPushButton(f"{self.tr_key('tab_gb_installed')} (0/0)")
        self.btn_sub_inst.setObjectName("SubTab")
        self.btn_sub_inst.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_sub_inst.clicked.connect(lambda: self._select_mods_sub(1))

        self.lbl_mods_count = QLabel("")
        self.lbl_mods_count.setStyleSheet(f"font-size: 12.5px; color: {C_GOLD}; font-weight: 600;")

        sub_row.addWidget(self.btn_sub_browse)
        sub_row.addWidget(self.btn_sub_inst)
        sub_row.addSpacing(12)
        sub_row.addWidget(self.lbl_mods_count)
        sub_row.addStretch(1)
        lay.addLayout(sub_row)

        self.mods_stack = QStackedWidget()
        lay.addWidget(self.mods_stack, 1)

        # ---- Sub-page 0: GameBanana 2-Column Editorial Grid ----
        browse_w = QWidget()
        b_lay = QVBoxLayout(browse_w)
        b_lay.setContentsMargins(0, 0, 0, 0)
        b_lay.setSpacing(10)

        cat_row = QHBoxLayout()
        cat_row.setSpacing(6)
        self.cat_buttons: dict[str, QPushButton] = {}
        for key_c, es_l, _en_l in GB_CATEGORIES:
            b = QPushButton(es_l)
            b.setObjectName("CatTab")
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _c=False, ck=key_c: self._select_gb_cat(ck))
            cat_row.addWidget(b)
            self.cat_buttons[key_c] = b
        cat_row.addStretch(1)
        b_lay.addLayout(cat_row)

        self.gb_scroll = QScrollArea()
        self.gb_scroll.setWidgetResizable(True)
        self.gb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gb_grid_host = QWidget()
        self.gb_grid_host.setObjectName("ScrollCanvas")
        self.gb_grid_lay = QGridLayout(self.gb_grid_host)
        self.gb_grid_lay.setContentsMargins(0, 4, 10, 12)
        self.gb_grid_lay.setHorizontalSpacing(24)
        self.gb_grid_lay.setVerticalSpacing(0)
        self.gb_grid_lay.setColumnStretch(0, 1)
        self.gb_grid_lay.setColumnStretch(1, 1)
        self.gb_scroll.setWidget(self.gb_grid_host)
        b_lay.addWidget(self.gb_scroll, 1)

        self.lbl_mods_foot = QLabel("●  GameBanana · Tears of the Kingdom (ID 7617)")
        self.lbl_mods_foot.setStyleSheet(f"font-size: 12px; color: {C_MUTED};")
        b_lay.addWidget(self.lbl_mods_foot)
        self.mods_stack.addWidget(browse_w)

        # ---- Sub-page 1: Tus Mods (PS5 Installed + Local Queue, Image 3 style) ----
        inst_scroll = QScrollArea()
        inst_scroll.setWidgetResizable(True)
        inst_w = QWidget()
        inst_w.setObjectName("ScrollCanvas")
        inst_lay = QVBoxLayout(inst_w)
        inst_lay.setContentsMargins(0, 6, 12, 12)
        inst_lay.setSpacing(16)

        act_row = QHBoxLayout()
        act_row.setSpacing(10)
        b_zip = self._bind_tr(QPushButton(), "btn_add_zip")
        b_zip.setCursor(Qt.CursorShape.PointingHandCursor)
        b_zip.clicked.connect(self._add_local_zip)
        b_dir = self._bind_tr(QPushButton(), "btn_add_dir")
        b_dir.setCursor(Qt.CursorShape.PointingHandCursor)
        b_dir.clicked.connect(self._add_local_dir)
        b_ref = self._bind_tr(QPushButton(), "btn_ps5_refresh")
        b_ref.setObjectName("PrimaryBlue")
        b_ref.setCursor(Qt.CursorShape.PointingHandCursor)
        b_ref.clicked.connect(self.refresh_ps5_mods)
        b_push = self._bind_tr(QPushButton(), "btn_push_mods")
        b_push.setObjectName("PrimaryGold")
        b_push.setCursor(Qt.CursorShape.PointingHandCursor)
        b_push.clicked.connect(self.push_staged_mods_to_ps5)
        act_row.addWidget(b_zip)
        act_row.addWidget(b_dir)
        act_row.addWidget(b_ref)
        act_row.addStretch(1)
        act_row.addWidget(b_push)
        inst_lay.addLayout(act_row)

        # PS5 installed section
        c_ps5 = QFrame()
        c_ps5.setObjectName("EditorialCard")
        c_ps5_l = QVBoxLayout(c_ps5)
        c_ps5_l.setContentsMargins(20, 16, 20, 16)
        c_ps5_l.setSpacing(8)
        ps5_h = self._bind_tr(QLabel(), "ps5_mods_hdr")
        ps5_h.setObjectName("CardTitle")
        c_ps5_l.addWidget(ps5_h)
        self.ps5_mods_host = QVBoxLayout()
        self.ps5_mods_host.setSpacing(0)
        c_ps5_l.addLayout(self.ps5_mods_host)
        inst_lay.addWidget(c_ps5)

        # Local queue section
        c_loc = QFrame()
        c_loc.setObjectName("EditorialCard")
        c_loc_l = QVBoxLayout(c_loc)
        c_loc_l.setContentsMargins(20, 16, 20, 16)
        c_loc_l.setSpacing(8)
        loc_h = self._bind_tr(QLabel(), "local_mods_hdr")
        loc_h.setObjectName("CardTitle")
        c_loc_l.addWidget(loc_h)
        self.local_mods_host = QVBoxLayout()
        self.local_mods_host.setSpacing(0)
        c_loc_l.addLayout(self.local_mods_host)
        inst_lay.addWidget(c_loc)
        inst_lay.addStretch(1)

        inst_scroll.setWidget(inst_w)
        self.mods_stack.addWidget(inst_scroll)

        self._select_mods_sub(0)
        self._rebuild_installed_lists()
        self._page_indices["mods"] = self.stack.addWidget(page)

    # ================ PAGE 3: DEPLOY TO PS5 (FTP) ================
    def _build_page_ftp(self) -> None:
        scroll, lay = self._wrap_scroll_page(max_width=920)
        ey = self._bind_tr(QLabel(), "p_ftp_eyebrow")
        ey.setObjectName("Eyebrow")
        h = self._bind_tr(QLabel(), "p_ftp_h")
        h.setObjectName("PageTitle")
        sub = self._bind_tr(QLabel(), "p_ftp_s")
        sub.setObjectName("PageSub")
        sub.setWordWrap(True)
        lay.addWidget(ey)
        lay.addWidget(h)
        lay.addWidget(sub)

        c_ftp, f_lay = self._make_card("c_ftp_t", "c_ftp_s")
        row = QHBoxLayout()
        row.setSpacing(14)

        col_ip = QVBoxLayout()
        col_ip.setSpacing(5)
        l_ip = self._bind_tr(QLabel(), "lbl_ip")
        l_ip.setObjectName("FieldLabel")
        self.ed_ftp_host = QLineEdit(self.prefs.get("ftp_host", ""))
        self.ed_ftp_host.setPlaceholderText("192.168.1.50")
        self.ed_ftp_host.setMinimumHeight(40)
        col_ip.addWidget(l_ip)
        col_ip.addWidget(self.ed_ftp_host)

        col_pt = QVBoxLayout()
        col_pt.setSpacing(5)
        l_pt = self._bind_tr(QLabel(), "lbl_port")
        l_pt.setObjectName("FieldLabel")
        self.ed_ftp_port = QLineEdit(self.prefs.get("ftp_port", "2121"))
        self.ed_ftp_port.setFixedWidth(110)
        self.ed_ftp_port.setMinimumHeight(40)
        col_pt.addWidget(l_pt)
        col_pt.addWidget(self.ed_ftp_port)

        col_btn = QVBoxLayout()
        col_btn.setSpacing(5)
        col_btn.addWidget(QLabel(""))
        btn_conn = self._bind_tr(QPushButton(), "btn_connect_ps5")
        btn_conn.setObjectName("PrimaryEmerald")
        btn_conn.setMinimumHeight(40)
        btn_conn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_conn.clicked.connect(lambda: self.open_ps5_connect_modal(startup=False))
        col_btn.addWidget(btn_conn)

        row.addLayout(col_ip, 1)
        row.addLayout(col_pt)
        row.addLayout(col_btn)
        f_lay.addLayout(row)

        self.chk_ftp_sh = self._bind_tr(QCheckBox(), "chk_ftp_sh")
        self.chk_ftp_sh.setChecked(True)
        self.chk_ftp_ini = self._bind_tr(QCheckBox(), "chk_ftp_ini")
        self.chk_ftp_ini.setChecked(True)
        self.chk_ftp_romfs = self._bind_tr(QCheckBox(), "chk_ftp_romfs")
        self.chk_ftp_romfs.setChecked(False)
        for c in (self.chk_ftp_sh, self.chk_ftp_ini, self.chk_ftp_romfs):
            f_lay.addWidget(c)

        lay.addWidget(c_ftp)
        lay.addStretch(1)
        self._page_indices["ftp"] = self.stack.addWidget(scroll)

    # ================ PAGE 4: LAYOUT & ARTWORK ================
    def _build_page_layout(self) -> None:
        scroll, lay = self._wrap_scroll_page(max_width=1020)
        ey = self._bind_tr(QLabel(), "p_lay_eyebrow")
        ey.setObjectName("Eyebrow")
        h = self._bind_tr(QLabel(), "p_lay_h")
        h.setObjectName("PageTitle")
        sub = self._bind_tr(QLabel(), "p_lay_s")
        sub.setObjectName("PageSub")
        sub.setWordWrap(True)
        lay.addWidget(ey)
        lay.addWidget(h)
        lay.addWidget(sub)

        c_art, a_lay = self._make_card("c_art_t", "c_art_s")
        row = QHBoxLayout()
        row.setSpacing(12)
        self.ed_art_url = QLineEdit()
        self.ed_art_url.setMinimumHeight(38)
        self.ed_art_url.setPlaceholderText("https://.../icon0.png")
        b_art = self._bind_tr(QPushButton(), "btn_art_dl")
        b_art.setObjectName("PrimaryGold")
        b_art.setMinimumHeight(38)
        b_art.setCursor(Qt.CursorShape.PointingHandCursor)
        b_art.clicked.connect(self._fetch_art_url)
        row.addWidget(self.ed_art_url, 1)
        row.addWidget(b_art)
        a_lay.addLayout(row)
        lay.addWidget(c_art)

        layout_txt = QPlainTextEdit(PS5_LAYOUT_TEXT)
        layout_txt.setObjectName("Terminal")
        layout_txt.setReadOnly(True)
        layout_txt.setMinimumHeight(340)
        lay.addWidget(layout_txt, 1)
        self._page_indices["layout"] = self.stack.addWidget(scroll)

    # ---- Navigation & Localization ----
    def select_page(self, key: str) -> None:
        self.stack.setCurrentIndex(self._page_indices[key])
        for k, item in self.nav_items.items():
            item.set_active(k == key)
        if key == "mods":
            self.dock.hide()
            if not self.gb_all_results:
                self.run_gb_search()
        else:
            self.dock.show()

    def apply_language(self, code: str) -> None:
        self.lang = code
        self.prefs["lang"] = code
        _save_prefs(self.prefs)
        self.setWindowTitle(self.tr_key("win_title"))

        act_style = f"background-color: {C_ACCENT}; color: #051710; border: none; border-radius: 5px; font-weight: 700; font-size: 12px;"
        off_style = f"background-color: transparent; color: {C_MUTED}; border: none; border-radius: 5px; font-weight: 600; font-size: 12px;"
        self.btn_es.setStyleSheet(act_style if code == "es" else off_style)
        self.btn_en.setStyleSheet(act_style if code == "en" else off_style)

        for w, key in self._tr_bindings:
            if hasattr(w, "setText"):
                w.setText(self.tr_key(key))  # type: ignore[attr-defined]

        for key, _, _, tk_k, sk_k in [
            ("build", "", "", "nav_build_t", "nav_build_s"),
            ("mods", "", "", "nav_mods_t", "nav_mods_s"),
            ("ftp", "", "", "nav_ftp_t", "nav_ftp_s"),
            ("layout", "", "", "nav_layout_t", "nav_layout_s"),
        ]:
            self.nav_items[key].set_texts(self.tr_key(tk_k), self.tr_key(sk_k))

        self.ed_gb_query.setPlaceholderText(self.tr_key("search_ph"))
        self.btn_sub_browse.setText(self.tr_key("tab_gb_browse"))
        self.lbl_status_sub.setText(self.tr_key("status_sub"))
        self.btn_sb_conn.setText(f"🔌  {self.tr_key('btn_connect_ps5')}")
        if not self.ps5_connected:
            self.lbl_status_dot.setText(self.tr_key("status_ready"))
        if self.gb_all_results:
            self.lbl_mods_count.setText(
                f"{len(self.gb_all_results)} mods encontrados en GameBanana (Tears of the Kingdom)"
                if code == "es"
                else f"{len(self.gb_all_results)} mods found on GameBanana (Tears of the Kingdom)"
            )
        self._refresh_cat_tabs()
        self._update_installed_tab_label()
        self._rebuild_installed_lists()

    # ---- PS5 Connection Handling ----
    def open_ps5_connect_modal(self, *, startup: bool = False, on_connected: Callable[[], None] | None = None) -> None:
        dlg = PS5ConnectDialog(
            self,
            self.tr_key,
            self.ed_ftp_host.text().strip(),
            self.ed_ftp_port.text().strip() or "2121",
            startup=startup,
        )
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.ed_ftp_host.setText(dlg.connected_host)
            self.ed_ftp_port.setText(str(dlg.connected_port))
            self.prefs["ftp_host"] = dlg.connected_host
            self.prefs["ftp_port"] = str(dlg.connected_port)
            _save_prefs(self.prefs)
            self.ps5_connected = True
            self.ps5_mods = dlg.ps5_mods
            self.lbl_status_dot.setText(f"●  PS5 ({dlg.connected_host})")
            self.lbl_status_dot.setStyleSheet(f"font-size: 12.5px; font-weight: 700; color: {C_ACCENT};")
            self._update_installed_tab_label()
            self._rebuild_installed_lists()
            self.append_log(f"[ok] PS5 connected at {dlg.connected_host}:{dlg.connected_port} ({len(self.ps5_mods)} mods installed).\n")
            if on_connected:
                on_connected()

    # ---- GameBanana Browser & Mod Actions ----
    def _select_mods_sub(self, idx: int) -> None:
        self.mods_stack.setCurrentIndex(idx)
        self.btn_sub_browse.setProperty("active", "true" if idx == 0 else "false")
        self.btn_sub_inst.setProperty("active", "true" if idx == 1 else "false")
        for b in (self.btn_sub_browse, self.btn_sub_inst):
            b.style().unpolish(b)
            b.style().polish(b)

    def _update_installed_tab_label(self) -> None:
        self.btn_sub_inst.setText(f"{self.tr_key('tab_gb_installed')} ({len(self.ps5_mods)}/{len(self.local_mods)})")

    def _refresh_cat_tabs(self) -> None:
        is_es = self.lang == "es"
        for key_c, es_l, en_l in GB_CATEGORIES:
            btn = self.cat_buttons[key_c]
            cnt = sum(1 for m in self.gb_all_results if match_category(m, key_c)) if self.gb_all_results else 0
            label = f"{es_l if is_es else en_l} ({cnt})" if self.gb_all_results else (es_l if is_es else en_l)
            btn.setText(label.replace("&", "&&"))
            btn.setProperty("active", "true" if key_c == self.gb_cat else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _select_gb_cat(self, cat_key: str) -> None:
        self.gb_cat = cat_key
        self._refresh_cat_tabs()
        if self.gb_all_results:
            self._render_gb_grid([m for m in self.gb_all_results if match_category(m, cat_key)])
        else:
            self.run_gb_search()

    def run_gb_search(self) -> None:
        query = self.ed_gb_query.text().strip()
        sort = self.cb_gb_sort.currentText() or "default"
        self.lbl_mods_foot.setText("⏳  Cargando mods de Tears of the Kingdom desde GameBanana..." if self.lang == "es" else "⏳  Loading Tears of the Kingdom mods from GameBanana...")

        w = FnWorker(lambda: search_mods(query=query, page=1, sort=sort, category="all", max_pages=3), self)
        w.done.connect(self._on_gb_results)
        w.failed.connect(lambda err: self.lbl_mods_foot.setText(f"✖  Error GameBanana: {err}"))
        self.active_workers.append(w)
        w.start()

    def _on_gb_results(self, mods: object) -> None:
        if not isinstance(mods, list):
            return
        self.gb_all_results = mods
        is_es = self.lang == "es"
        self.lbl_mods_count.setText(
            f"{len(mods)} mods encontrados en GameBanana (Tears of the Kingdom)"
            if is_es
            else f"{len(mods)} mods found on GameBanana (Tears of the Kingdom)"
        )
        self._refresh_cat_tabs()
        self._render_gb_grid([m for m in mods if match_category(m, self.gb_cat)])

    def _render_gb_grid(self, mods: list[GBMod]) -> None:
        if self._thumb_worker is not None:
            self._thumb_worker.cancel()
        while self.gb_grid_lay.count():
            it = self.gb_grid_lay.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self.gb_rows_by_url.clear()

        missing_urls: list[str] = []
        inst_lbl = self.tr_key("btn_install")
        for idx, m in enumerate(mods):
            r, c = divmod(idx, 2)
            cached = self.gb_thumb_cache.get(m.thumb_url) if m.thumb_url else None
            row = EditorialModRow(m, inst_lbl, cached_pm=cached)
            row.open_detail.connect(self._open_mod_detail)
            row.install_clicked.connect(lambda mod_obj: self._install_gb_mod(mod_obj, None))
            self.gb_grid_lay.addWidget(row, r, c)
            if m.thumb_url and cached is None:
                self.gb_rows_by_url.setdefault(m.thumb_url, []).append(row)
                if m.thumb_url not in missing_urls:
                    missing_urls.append(m.thumb_url)

        self.gb_grid_lay.setRowStretch((len(mods) + 1) // 2, 1)
        is_es = self.lang == "es"
        self.lbl_mods_foot.setText(
            f"●  {len(mods)} mods mostrados · Haz clic en cualquier mod para ver su galería y descripción completa."
            if is_es
            else f"●  {len(mods)} mods shown · Click any mod to view its gallery and full description."
        )

        if missing_urls:
            tw = ThumbBatchWorker(missing_urls, self)
            tw.thumb_ready.connect(self._on_thumb_loaded)
            self._thumb_worker = tw
            tw.start()

    def _on_thumb_loaded(self, url: str, raw: bytes) -> None:
        pm = QPixmap()
        if not pm.loadFromData(raw):
            return
        rounded = _rounded_pixmap(pm, 96, 54, radius=6)
        self.gb_thumb_cache[url] = rounded
        for row in self.gb_rows_by_url.get(url, []):
            try:
                row.set_thumb(rounded)
            except RuntimeError:
                pass

    def _open_mod_detail(self, mod: GBMod) -> None:
        cached = self.gb_detail_cache.get((mod.mod_id, mod.wip))
        dlg = ModDetailDialog(
            self,
            mod,
            self.tr_key,
            self.lang == "es",
            cached,
            on_detail_loaded=lambda d: self.gb_detail_cache.__setitem__((mod.mod_id, mod.wip), d),
            on_install=self._install_gb_mod,
        )
        dlg.exec()

    def _install_gb_mod(self, mod: GBMod, chosen_file: GBFile | None) -> None:
        if not self.ps5_connected:
            self.open_ps5_connect_modal(startup=False, on_connected=lambda: self._install_gb_mod(mod, chosen_file))
            return

        host = self.ed_ftp_host.text().strip()
        port = int(self.ed_ftp_port.text().strip() or "2121")
        out_root = Path(self.ed_out.text().strip() or str(Path.home() / "TOTK-PS5-Out")) / "data_totk_ps5" / "mods"
        self.lbl_mods_foot.setText(f"⬇  Descargando e instalando {mod.name} en PS5...")

        def _work() -> tuple[str, list[str]]:
            target_file = chosen_file
            if target_file is None:
                detail = self.gb_detail_cache.get((mod.mod_id, mod.wip))
                files = detail.files if (detail and detail.files) else fetch_mod_files(mod.mod_id, wip=mod.wip)
                if not files:
                    raise RuntimeError("Este mod no tiene archivos descargables.")
                target_file = files[0]
            staged_dir, _warns = download_and_stage_mod(target_file, mod.name, out_root, log_fn=lambda _m: None)
            dep = PS5Deployer(host, port, log_fn=lambda _m: None)
            try:
                dep.mkdir_p(f"/data/totk-ps5/mods/{staged_dir.name}")
                dep.chmod_777(f"/data/totk-ps5/mods/{staged_dir.name}")
                dep.upload_dir(staged_dir, f"/data/totk-ps5/mods/{staged_dir.name}")
                dirs = dep.list_dirs("/data/totk-ps5/mods")
            finally:
                dep.close()
            return str(staged_dir), dirs

        w = FnWorker(_work, self)
        w.done.connect(lambda res: self._on_mod_installed(mod.name, res))
        w.failed.connect(lambda err: self.lbl_mods_foot.setText(f"✖  Error instalando {mod.name}: {err}"))
        self.active_workers.append(w)
        w.start()

    def _on_mod_installed(self, mod_name: str, res: object) -> None:
        if isinstance(res, tuple):
            staged_str, dirs = res
            if staged_str not in self.local_mods:
                self.local_mods.append(staged_str)
            self.ps5_mods = list(dirs)
            self._update_installed_tab_label()
            self._rebuild_installed_lists()
            self.lbl_mods_foot.setText(f"✔  {mod_name} instalado en tu PS5 (/data/totk-ps5/mods/).")

    def _rebuild_installed_lists(self) -> None:
        for host_lay in (self.ps5_mods_host, self.local_mods_host):
            while host_lay.count():
                it = host_lay.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.deleteLater()

        if not self.ps5_mods:
            emp = QLabel(self.tr_key("ps5_mods_empty"))
            emp.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; padding: 10px 0;")
            self.ps5_mods_host.addWidget(emp)
        else:
            for name in self.ps5_mods:
                row = QFrame()
                row.setStyleSheet("QFrame { border-bottom: 1px solid #1C273A; }")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 10, 4, 10)
                lbl = QLabel(f"📦  {name}")
                lbl.setStyleSheet(f"font-size: 13.5px; font-weight: 600; color: {C_TEXT};")
                btn = QPushButton(self.tr_key("btn_delete"))
                btn.setObjectName("DangerBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c=False, n=name: self._delete_ps5_mod(n))
                rl.addWidget(lbl, 1)
                rl.addWidget(btn)
                self.ps5_mods_host.addWidget(row)

        if not self.local_mods:
            emp2 = QLabel(self.tr_key("local_mods_empty"))
            emp2.setStyleSheet(f"color: {C_MUTED}; font-size: 13px; padding: 10px 0;")
            self.local_mods_host.addWidget(emp2)
        else:
            for p_str in self.local_mods:
                row = QFrame()
                row.setStyleSheet("QFrame { border-bottom: 1px solid #1C273A; }")
                rl = QHBoxLayout(row)
                rl.setContentsMargins(4, 10, 4, 10)
                lbl = QLabel(p_str)
                lbl.setStyleSheet(f"font-size: 13px; color: {C_TEXT_BODY};")
                btn = QPushButton(self.tr_key("btn_remove"))
                btn.setObjectName("DangerBtn")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _c=False, p=p_str: self._remove_local_mod(p))
                rl.addWidget(lbl, 1)
                rl.addWidget(btn)
                self.local_mods_host.addWidget(row)

    def _add_local_zip(self) -> None:
        p, _ = QFileDialog.getOpenFileName(self, self.tr_key("btn_add_zip"), str(Path.home()), "ZIP Archives (*.zip)")
        if p and p not in self.local_mods:
            self.local_mods.append(p)
            self._update_installed_tab_label()
            self._rebuild_installed_lists()

    def _add_local_dir(self) -> None:
        p = QFileDialog.getExistingDirectory(self, self.tr_key("btn_add_dir"), str(Path.home()))
        if p and p not in self.local_mods:
            self.local_mods.append(p)
            self._update_installed_tab_label()
            self._rebuild_installed_lists()

    def _remove_local_mod(self, p: str) -> None:
        if p in self.local_mods:
            self.local_mods.remove(p)
            self._update_installed_tab_label()
            self._rebuild_installed_lists()

    def refresh_ps5_mods(self) -> None:
        if not self.ps5_connected:
            self.open_ps5_connect_modal(startup=False, on_connected=self.refresh_ps5_mods)
            return
        host = self.ed_ftp_host.text().strip()
        port = int(self.ed_ftp_port.text().strip() or "2121")

        def _work() -> list[str]:
            dep = PS5Deployer(host, port, timeout=10, log_fn=lambda _m: None)
            try:
                return dep.list_dirs("/data/totk-ps5/mods")
            finally:
                dep.close()

        w = FnWorker(_work, self)
        w.done.connect(self._on_ps5_mods_refreshed)
        self.active_workers.append(w)
        w.start()

    def _on_ps5_mods_refreshed(self, dirs: object) -> None:
        if isinstance(dirs, list):
            self.ps5_mods = dirs
            self._update_installed_tab_label()
            self._rebuild_installed_lists()

    def _delete_ps5_mod(self, mod_name: str) -> None:
        if not self.ps5_connected:
            self.open_ps5_connect_modal(startup=False)
            return
        ans = QMessageBox.question(self, self.tr_key("del_confirm_t"), self.tr_key("del_confirm_m").format(name=mod_name))
        if ans != QMessageBox.StandardButton.Yes:
            return
        host = self.ed_ftp_host.text().strip()
        port = int(self.ed_ftp_port.text().strip() or "2121")

        def _work() -> list[str]:
            dep = PS5Deployer(host, port, log_fn=lambda _m: None)
            try:
                dep.rm_rf(f"/data/totk-ps5/mods/{mod_name}")
                return dep.list_dirs("/data/totk-ps5/mods")
            finally:
                dep.close()

        w = FnWorker(_work, self)
        w.done.connect(self._on_ps5_mods_refreshed)
        self.active_workers.append(w)
        w.start()

    def push_staged_mods_to_ps5(self) -> None:
        if not self.ps5_connected:
            self.open_ps5_connect_modal(startup=False, on_connected=self.push_staged_mods_to_ps5)
            return
        host = self.ed_ftp_host.text().strip()
        port = int(self.ed_ftp_port.text().strip() or "2121")
        out_mods = Path(self.ed_out.text().strip() or str(Path.home() / "TOTK-PS5-Out")) / "data_totk_ps5" / "mods"
        if not out_mods.is_dir():
            QMessageBox.information(self, "Mods", "No hay mods en la carpeta de salida todavía." if self.lang == "es" else "No staged mods directory found yet.")
            return

        def _work() -> list[str]:
            dep = PS5Deployer(host, port, log_fn=lambda _m: None)
            try:
                dep.mkdir_p("/data/totk-ps5/mods")
                dep.chmod_777("/data/totk-ps5/mods")
                dep.upload_dir(out_mods, "/data/totk-ps5/mods")
                return dep.list_dirs("/data/totk-ps5/mods")
            finally:
                dep.close()

        w = FnWorker(_work, self)
        w.done.connect(self._on_ps5_mods_refreshed)
        self.active_workers.append(w)
        w.start()

    def _fetch_art_url(self) -> None:
        url = self.ed_art_url.text().strip()
        if not url:
            return
        dest = Path(self.ed_out.text().strip() or str(Path.home() / "TOTK-PS5-Out")) / TITLE_ID / "sce_sys" / "icon0.png"
        self.append_log(f">>> Downloading custom PS5 icon0.png from {url}...\n")

        w = FnWorker(lambda: (download_ps5_icon_from_url(url, dest), str(dest))[1], self)
        w.done.connect(self._on_art_done)
        w.failed.connect(lambda err: self.append_log(f"[err] Icon download failed: {err}\n"))
        self.active_workers.append(w)
        w.start()

    def _on_art_done(self, dest_str: object) -> None:
        if isinstance(dest_str, str) and Path(dest_str).is_file():
            self.lbl_logo.setPixmap(_rounded_pixmap(QPixmap(dest_str), 50, 50, radius=11))
            self.append_log(f"[ok] Saved 512x512 PS5 icon0.png -> {dest_str}\n")

    # ---- Build & Deploy CLI Orchestration (100% Preserved Logic) ----
    def append_log(self, text: str) -> None:
        cur = self.log_box.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        low = text.lower()
        if text.startswith("[ok]") or "passed" in low:
            fmt.setForeground(QColor(C_ACCENT))
        elif text.startswith("[err]") or "error" in low or "failed" in low:
            fmt.setForeground(QColor(C_DANGER))
        elif text.startswith("[ftp]") or text.startswith("[warn]") or text.startswith(">>>"):
            fmt.setForeground(QColor(C_GOLD))
        elif text.startswith("[ps5-totk]") or text.startswith("[check]"):
            fmt.setForeground(QColor(C_BLUE))
        else:
            fmt.setForeground(QColor("#CBD5E1"))
        cur.insertText(text, fmt)
        self.log_box.setTextCursor(cur)
        self.log_box.ensureCursorVisible()

    def _set_busy(self, busy: bool, label: str = "") -> None:
        for b in self.action_buttons:
            b.setEnabled(not busy)
        if busy:
            self.pbar.setRange(0, 0)
            self.lbl_status_dot.setText(f"●  {label}")
            self.lbl_status_dot.setStyleSheet(f"font-size: 12.5px; font-weight: 700; color: {C_GOLD};")
        else:
            self.pbar.setRange(0, 1)
            self.pbar.setValue(0)
            if self.ps5_connected:
                self.lbl_status_dot.setText(f"●  PS5 ({self.ed_ftp_host.text().strip()})")
            else:
                self.lbl_status_dot.setText(self.tr_key("status_ready"))
            self.lbl_status_dot.setStyleSheet(f"font-size: 12.5px; font-weight: 700; color: {C_ACCENT};")

    def build_cli_cmd(self, *, deploy_ftp: bool, deploy_only: bool = False) -> list[str]:
        out_dir = self.ed_out.text().strip() or str(Path.home() / "TOTK-PS5-Out")
        self.prefs["out"] = out_dir
        _save_prefs(self.prefs)
        cmd = [str(self.paths.python_bin), "-P", "-u", "-m", "builder.cli", "--out", out_dir]
        if deploy_only:
            cmd.append("--deploy-only")
        else:
            if self.ed_game.text().strip():
                cmd += ["--game", self.ed_game.text().strip()]
                if self.ed_update.text().strip():
                    cmd += ["--update", self.ed_update.text().strip()]
                if self.ed_keys.text().strip():
                    cmd += ["--keys", self.ed_keys.text().strip()]
            else:
                cmd += ["--exefs", self.ed_exefs.text().strip()]
                if self.ed_romfs.text().strip():
                    cmd += ["--romfs", self.ed_romfs.text().strip()]
            if self.ed_shaders.text().strip():
                cmd += ["--shaders", self.ed_shaders.text().strip()]
            if not self.chk_prompts.isChecked():
                cmd.append("--no-prompts")
            if self.chk_shaders.isChecked():
                cmd.append("--pretranslate-shaders")
            cmd += [
                "--res",
                self.cb_res.currentText(),
                "--hz",
                self.cb_hz.currentText(),
                "--frame-gen",
                self.cb_fg.currentText(),
                "--scale",
                self.cb_scale.currentText(),
                "--lang",
                self.cb_lang.currentText(),
            ]
            for m in self.local_mods:
                cmd += ["--mod", m]
        if deploy_ftp:
            cmd += ["--deploy-ftp", self.ed_ftp_host.text().strip(), "--ftp-port", self.ed_ftp_port.text().strip() or "2121"]
            if self.chk_ftp_romfs.isChecked():
                cmd.append("--deploy-romfs")
            if not self.chk_ftp_sh.isChecked():
                cmd.append("--skip-ftp-shaders")
            if not self.chk_ftp_ini.isChecked():
                cmd.append("--skip-ftp-ini")
        return cmd

    def _validate(self, *, need_ftp: bool, deploy_only: bool) -> bool:
        if not deploy_only:
            if not self.ed_game.text().strip() and not self.ed_exefs.text().strip():
                QMessageBox.warning(self, self.tr_key("err_no_game_t"), self.tr_key("err_no_game_m"))
                self.select_page("build")
                return False
            if self.ed_game.text().strip() and not self.ed_keys.text().strip():
                QMessageBox.warning(self, self.tr_key("err_no_keys_t"), self.tr_key("err_no_keys_m"))
                self.select_page("build")
                return False
        if need_ftp and not self.ed_ftp_host.text().strip():
            self.open_ps5_connect_modal(startup=False)
            return bool(self.ed_ftp_host.text().strip())
        return True

    def _run_ftp_only(self) -> None:
        if self._validate(need_ftp=True, deploy_only=True):
            self.run_cmd_async(self.build_cli_cmd(deploy_ftp=True, deploy_only=True), self.tr_key("btn_ftp_only"))

    def _run_build_only(self) -> None:
        if self._validate(need_ftp=False, deploy_only=False):
            self.run_cmd_async(self.build_cli_cmd(deploy_ftp=False), self.tr_key("btn_build"))

    def _run_build_and_ftp(self) -> None:
        if self._validate(need_ftp=True, deploy_only=False):
            self.run_cmd_async(self.build_cli_cmd(deploy_ftp=True), self.tr_key("btn_both"))

    def run_cmd_async(self, cmd: list[str], label: str) -> None:
        self._set_busy(True, label)
        self.log_box.clear()
        self.append_log(f">>> {label}\n")
        w = CommandWorker(cmd, self)
        w.line.connect(self.append_log)
        w.finished_rc.connect(lambda rc: (self.append_log(f"\n{'[ok] Done.' if rc == 0 else f'[err] Failed (exit {rc}).'}\n"), self._set_busy(False)))
        self._cmd_worker = w
        w.start()


    def closeEvent(self, ev) -> None:  # noqa: N802
        if self._thumb_worker is not None:
            self._thumb_worker.cancel()
            self._thumb_worker.wait(1500)
        for w in list(self.active_workers):
            if w.isRunning():
                w.quit()
                w.wait(1000)
        super().closeEvent(ev)


def run_gui() -> int:
    from PyQt6.QtGui import QPalette

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(C_BG))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(C_TEXT_BODY))
    pal.setColor(QPalette.ColorRole.Base, QColor(C_INPUT))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(C_CARD))
    pal.setColor(QPalette.ColorRole.Text, QColor(C_TEXT_BODY))
    pal.setColor(QPalette.ColorRole.Button, QColor(C_CARD_ALT))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(C_TEXT_BODY))
    app.setPalette(pal)
    app.setStyleSheet(APP_QSS)
    win = PS5TotkWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_gui())
