#!/usr/bin/env python3
"""All-in-One Tkinter GUI for PS5TotkBuilder AppImage (PPSA99199).

Features:
  - Tab 1 (Compilar & Shaders): Build PPSA99199/eboot.bin, PlayStation button icons (△ ○ × □),
    and PS5 RADV pre-translated shaders (TOTK_ZERO_LOCALS=0).
  - Tab 2 (MODS): Add RomFS mod folders or .zip archives staged to /data/totk-ps5/mods/.
  - Tab 3 (Enviar a PS5 FTP): One-click FTP deployment with exact PS5 layout creation.
  - Tab 4 (Layout PS5): Full directory structure & DualSense controls reference.
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

from .cli import main as cli_main
from .deploy import PS5_LAYOUT_TEXT
from .pipeline import default_kit_paths


def launch_gui() -> int:
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return cli_main(["--help"])

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, ttk
    except Exception:
        return cli_main(["--help"])

    paths = default_kit_paths()

    root = tk.Tk()
    root.title("PS5 TOTK Builder — Tears of the Kingdom (PPSA99199)")
    root.geometry("860x660")
    root.configure(bg="#111917")

    bg = "#111917"
    fg = "#e6efe9"
    accent = "#4fc3a1"
    entry_bg = "#1b2724"
    btn_bg = "#22332e"

    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=btn_bg, foreground=fg, padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", "#09110f")])

    tk.Label(
        root,
        text="PS5 Tears of the Kingdom Builder — Title ID PPSA99199",
        font=("Sans", 13, "bold"),
        bg=bg,
        fg=accent,
    ).pack(pady=(10, 4))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="x", padx=12, pady=4)

    # ---------------- TAB 1: Build & Shaders ----------------
    tab_build = tk.Frame(notebook, bg=bg, padx=10, pady=8)
    notebook.add(tab_build, text="1. Compilar & Shaders")

    def _if_exists(p: str) -> str:
        return p if Path(p).exists() else ""

    vars_map: dict[str, tk.StringVar] = {
        "game": tk.StringVar(value=""),
        "update": tk.StringVar(value=""),
        "keys": tk.StringVar(value=_if_exists("/home/saul/Games/Hyrule/TOTK/keys/prod.keys")),
        "exefs": tk.StringVar(value=_if_exists("/home/saul/Games/Hyrule/TOTK/ROM/exefs")),
        "romfs": tk.StringVar(value=_if_exists("/home/saul/Games/Hyrule/TOTK/ROM/romfs")),
        "shaders": tk.StringVar(value=""),
        "out": tk.StringVar(value=str(Path.home() / "TOTK-PS5-Out")),
        "res": tk.StringVar(value="2560x1440"),
        "hz": tk.StringVar(value="120"),
        "frame_gen": tk.StringVar(value="fsr3"),
        "scale": tk.StringVar(value="game"),
        "lang": tk.StringVar(value="es-419"),
        "ftp_host": tk.StringVar(value="10.0.0.195"),
        "ftp_port": tk.StringVar(value="2121"),
    }
    bool_map: dict[str, tk.BooleanVar] = {
        "prompts": tk.BooleanVar(value=True),
        "pretranslate_shaders": tk.BooleanVar(value=True),
        "ftp_romfs": tk.BooleanVar(value=False),
        "ftp_shaders": tk.BooleanVar(value=True),
        "ftp_ini": tk.BooleanVar(value=True),
    }

    def add_row(parent: tk.Frame, row: int, label: str, key: str, is_dir: bool) -> None:
        tk.Label(parent, text=label, bg=bg, fg=fg, anchor="w", width=22).grid(row=row, column=0, sticky="w", pady=2)
        tk.Entry(parent, textvariable=vars_map[key], bg=entry_bg, fg=fg, insertbackground=fg).grid(
            row=row, column=1, sticky="ew", padx=6, pady=2
        )

        def pick() -> None:
            chosen = filedialog.askdirectory() if is_dir else filedialog.askopenfilename()
            if chosen:
                vars_map[key].set(chosen)

        tk.Button(parent, text="Examinar", command=pick, bg=btn_bg, fg=fg).grid(row=row, column=2, pady=2)

    tab_build.columnconfigure(1, weight=1)
    add_row(tab_build, 0, "Juego base (.xci/.nsp):", "game", False)
    add_row(tab_build, 1, "Update (.nsp opcional):", "update", False)
    add_row(tab_build, 2, "Switch prod.keys:", "keys", False)
    add_row(tab_build, 3, "O ExeFS extraído:", "exefs", True)
    add_row(tab_build, 4, "O RomFS extraído:", "romfs", True)
    add_row(tab_build, 5, "Carpeta caché shaders:", "shaders", True)
    add_row(tab_build, 6, "Carpeta de salida:", "out", True)

    opts = tk.Frame(tab_build, bg=bg)
    opts.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(6, 2))
    tk.Checkbutton(
        opts,
        text="Íconos PlayStation por defecto (△ ○ × □, ○=A)",
        variable=bool_map["prompts"],
        bg=bg,
        fg=fg,
        selectcolor=entry_bg,
        activebackground=bg,
        activeforeground=fg,
    ).pack(side="left", padx=(0, 12))
    tk.Checkbutton(
        opts,
        text="Pre-traducir Shaders PS5 (RADV)",
        variable=bool_map["pretranslate_shaders"],
        bg=bg,
        fg=fg,
        selectcolor=entry_bg,
        activebackground=bg,
        activeforeground=fg,
    ).pack(side="left")

    presets = tk.Frame(tab_build, bg=bg)
    presets.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(4, 2))
    tk.Label(presets, text="Resolución:", bg=bg, fg=fg).pack(side="left")
    ttk.Combobox(presets, textvariable=vars_map["res"], values=("2560x1440", "1920x1080"), width=10, state="readonly").pack(
        side="left", padx=(4, 8)
    )
    tk.Label(presets, text="Hz:", bg=bg, fg=fg).pack(side="left")
    ttk.Combobox(presets, textvariable=vars_map["hz"], values=("120", "60"), width=4, state="readonly").pack(
        side="left", padx=(4, 8)
    )
    tk.Label(presets, text="FSR3 FG:", bg=bg, fg=fg).pack(side="left")
    ttk.Combobox(presets, textvariable=vars_map["frame_gen"], values=("fsr3", "off"), width=5, state="readonly").pack(
        side="left", padx=(4, 8)
    )
    tk.Label(presets, text="Escala:", bg=bg, fg=fg).pack(side="left")
    ttk.Combobox(presets, textvariable=vars_map["scale"], values=("100", "game", "75"), width=5, state="readonly").pack(
        side="left", padx=(4, 8)
    )
    tk.Label(presets, text="Idioma:", bg=bg, fg=fg).pack(side="left")
    ttk.Combobox(
        presets,
        textvariable=vars_map["lang"],
        values=("es-419", "es-ES", "en-US", "fr-FR", "de-DE", "ja-JP"),
        width=6,
        state="readonly",
    ).pack(side="left", padx=4)

    # ---------------- TAB 2: MODS ----------------
    tab_mods = tk.Frame(notebook, bg=bg, padx=10, pady=8)
    notebook.add(tab_mods, text="2. MODS (RomFS)")

    tk.Label(
        tab_mods,
        text="Agrega carpetas o archivos .zip de mods RomFS (se instalan en /data/totk-ps5/mods/ y se gestionan desde Touchpad+Options):",
        bg=bg,
        fg=fg,
        anchor="w",
    ).pack(fill="x", pady=(0, 4))

    mods_list = tk.Listbox(tab_mods, height=7, bg=entry_bg, fg=fg, selectbackground=accent, selectforeground="#09110f")
    mods_list.pack(fill="both", expand=True, pady=4)

    mod_btns = tk.Frame(tab_mods, bg=bg)
    mod_btns.pack(fill="x", pady=4)

    def add_mod_folder() -> None:
        chosen = filedialog.askdirectory(title="Seleccionar carpeta de Mod RomFS")
        if chosen:
            mods_list.insert("end", chosen)

    def add_mod_zip() -> None:
        chosen = filedialog.askopenfilename(title="Seleccionar Mod (.zip)", filetypes=[("ZIP archives", "*.zip")])
        if chosen:
            mods_list.insert("end", chosen)

    def remove_mod() -> None:
        for idx in reversed(mods_list.curselection()):
            mods_list.delete(idx)

    tk.Button(mod_btns, text="+ Carpeta Mod", command=add_mod_folder, bg=btn_bg, fg=fg).pack(side="left", padx=(0, 6))
    tk.Button(mod_btns, text="+ Mod (.zip)", command=add_mod_zip, bg=btn_bg, fg=fg).pack(side="left", padx=(0, 6))
    tk.Button(mod_btns, text="Quitar seleccionado", command=remove_mod, bg=btn_bg, fg=fg).pack(side="left")

    # ---------------- TAB 3: PS5 FTP Deploy ----------------
    tab_ftp = tk.Frame(notebook, bg=bg, padx=10, pady=8)
    notebook.add(tab_ftp, text="3. Enviar a PS5 (FTP)")

    ftp_row = tk.Frame(tab_ftp, bg=bg)
    ftp_row.pack(fill="x", pady=4)
    tk.Label(ftp_row, text="IP PS5 (ftpsrv):", bg=bg, fg=fg).pack(side="left")
    tk.Entry(ftp_row, textvariable=vars_map["ftp_host"], width=18, bg=entry_bg, fg=fg, insertbackground=fg).pack(
        side="left", padx=(6, 14)
    )
    tk.Label(ftp_row, text="Puerto:", bg=bg, fg=fg).pack(side="left")
    tk.Entry(ftp_row, textvariable=vars_map["ftp_port"], width=7, bg=entry_bg, fg=fg, insertbackground=fg).pack(
        side="left", padx=6
    )

    ftp_opts = tk.Frame(tab_ftp, bg=bg)
    ftp_opts.pack(fill="x", pady=6)
    tk.Checkbutton(
        ftp_opts,
        text="Subir caché de shaders",
        variable=bool_map["ftp_shaders"],
        bg=bg,
        fg=fg,
        selectcolor=entry_bg,
        activebackground=bg,
        activeforeground=fg,
    ).pack(side="left", padx=(0, 14))
    tk.Checkbutton(
        ftp_opts,
        text="Sobrescribir totk.ini",
        variable=bool_map["ftp_ini"],
        bg=bg,
        fg=fg,
        selectcolor=entry_bg,
        activebackground=bg,
        activeforeground=fg,
    ).pack(side="left", padx=(0, 14))
    tk.Checkbutton(
        ftp_opts,
        text="Subir romfs.bin completo (15.86 GiB)",
        variable=bool_map["ftp_romfs"],
        bg=bg,
        fg=fg,
        selectcolor=entry_bg,
        activebackground=bg,
        activeforeground=fg,
    ).pack(side="left")

    tk.Label(
        tab_ftp,
        text="Nota: Cierra TOTK en la PS5 antes de subir eboot.bin. Nunca toca PPSA99198 (OOT) ni otros títulos.",
        bg=bg,
        fg="#9bc4b5",
        anchor="w",
    ).pack(fill="x", pady=(6, 0))

    # ---------------- TAB 4: Layout PS5 ----------------
    tab_layout = tk.Frame(notebook, bg=bg, padx=10, pady=8)
    notebook.add(tab_layout, text="4. Layout PS5")

    layout_box = scrolledtext.ScrolledText(tab_layout, height=13, bg="#0b1110", fg="#c9e4d8", font=("Monospace", 8))
    layout_box.insert("1.0", PS5_LAYOUT_TEXT)
    layout_box.config(state="disabled")
    layout_box.pack(fill="both", expand=True)

    # ---------------- Shared Log & Action Buttons ----------------
    log_box = scrolledtext.ScrolledText(root, height=13, bg="#0b1110", fg="#c9e4d8", font=("Monospace", 9))
    log_box.pack(fill="both", expand=True, padx=12, pady=(6, 8))

    q: queue.Queue[str | None] = queue.Queue()
    action_buttons: list[tk.Button] = []

    def set_busy(busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for b in action_buttons:
            b.config(state=state)

    def pump() -> None:
        try:
            while True:
                item = q.get_nowait()
                if item is None:
                    set_busy(False)
                    break
                log_box.insert("end", item)
                log_box.see("end")
        except queue.Empty:
            pass
        root.after(120, pump)

    def build_cli_cmd(*, deploy_ftp: bool, deploy_only: bool = False) -> list[str]:
        cmd = [str(paths.python_bin), "-u", "-m", "builder.cli", "--out", vars_map["out"].get().strip()]
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
                "--res", vars_map["res"].get(),
                "--hz", vars_map["hz"].get(),
                "--frame-gen", vars_map["frame_gen"].get(),
                "--scale", vars_map["scale"].get(),
                "--lang", vars_map["lang"].get(),
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
        set_busy(True)
        log_box.delete("1.0", "end")
        log_box.insert("end", f">>> {label}\n")

        def worker() -> None:
            proc = subprocess.Popen(
                cmd,
                cwd=str(paths.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                q.put(line)
            rc = proc.wait()
            q.put(f"\n=== {label} terminó con código {rc} ===\n")
            q.put(None)

        threading.Thread(target=worker, daemon=True).start()

    btn_row = tk.Frame(root, bg=bg)
    btn_row.pack(pady=(0, 10))

    b1 = tk.Button(
        btn_row,
        text="Compilar PS5 (PPSA99199)",
        command=lambda: run_cmd_async(build_cli_cmd(deploy_ftp=False), "Compilar PS5"),
        bg=accent,
        fg="#09110f",
        font=("Sans", 9, "bold"),
        padx=12,
        pady=5,
    )
    b1.pack(side="left", padx=5)

    b2 = tk.Button(
        btn_row,
        text="Compilar + Enviar Todo a PS5 (FTP)",
        command=lambda: run_cmd_async(build_cli_cmd(deploy_ftp=True), "Compilar + Enviar a PS5"),
        bg="#3898ff",
        fg="#061018",
        font=("Sans", 9, "bold"),
        padx=12,
        pady=5,
    )
    b2.pack(side="left", padx=5)

    b3 = tk.Button(
        btn_row,
        text="Enviar Salida por FTP",
        command=lambda: run_cmd_async(build_cli_cmd(deploy_ftp=True, deploy_only=True), "Enviar por FTP"),
        bg=btn_bg,
        fg=fg,
        padx=10,
        pady=5,
    )
    b3.pack(side="left", padx=5)

    def check_kit() -> None:
        rc = cli_main(["--check"])
        messagebox.showinfo("Kit Check", "PS5 TOTK Builder Kit OK!" if rc == 0 else "Kit check failed")

    b4 = tk.Button(btn_row, text="Self-Check Kit", command=check_kit, bg=btn_bg, fg=fg, padx=10, pady=5)
    b4.pack(side="left", padx=5)

    action_buttons.extend([b1, b2, b3, b4])
    root.after(120, pump)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(launch_gui())
