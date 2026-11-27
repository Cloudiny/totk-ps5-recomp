#!/usr/bin/env python3
"""Safe FTP deployer for PS5 Tears of the Kingdom (PPSA99199 + /data/totk-ps5/).

Used by both the AppImage GUI/CLI and scripts/deploy_ftp.py.
Strictly restricts all writes to /data/homebrew/PPSA99199 and /data/totk-ps5
(never touches PPSA99198 / Longshot Plus or any other title).
"""

from __future__ import annotations

import ftplib
import time
from pathlib import Path
from typing import Callable

ALLOWED_REMOTE_PREFIXES = (
    "/data/homebrew/PPSA99199",
    "/data/totk-ps5",
)

PS5_LAYOUT_TEXT = """\
======================================================================
  ESTRUCTURA EXACTA EN PS5 (FTP / USB) — TOTK PS5 Recomp (PPSA99199)
======================================================================

/data/homebrew/PPSA99199/
  ├── eboot.bin                 (FSELF firmado de TOTK PS5)
  ├── sce_module/
  │   └── libc.prx
  └── sce_sys/
      ├── icon0.png             (ícono del juego)
      ├── pic0.dds              (logo 4K BC7)
      ├── pic1.dds              (fondo 4K BC7)
      └── param.json            (metadata PPSA99199 — subir al final)

/data/totk-ps5/
  ├── totk.ini                  (config PS5: 1440p, 100%, ○=A / ×=B, íconos PS, es-419)
  ├── romfs-index.bin           (índice RomFS generado al compilar)
  ├── totk_xlate.id             (identidad del traductor de shaders RADV PS5)
  ├── shader-prepared.bin       (28,667 use-masks precompilados)
  ├── shader-programs.bin       (registro de programas)
  ├── shader-answers.bin        (respuestas de shaders)
  ├── shader-cache/
  │   └── shader-cache.pack     (pack completo de shaders pre-traducidos RADV PS5)
  ├── romfs-patches-playstation/       (íconos PlayStation △ ○ × □ — layout ○ confirmar)
  ├── romfs-patches-playstation-xbox/  (íconos PlayStation △ ○ × □ — layout × confirmar)
  ├── exefs/
  │   ├── main
  │   ├── main.npdm
  │   ├── sdk
  │   └── subsdk0
  ├── romfs/
  │   └── romfs.bin             (~15.86 GiB RomFS extraído)
  ├── mods/                     (carpeta de MODS RomFS; gestionables desde el menú)
  │   └── <nombre_del_mod>/romfs/...
  ├── saves/                    (partidas separadas AUTOMÁTICAMENTE por usuario de PS5)
  │   ├── user_<id_1>/          (partida + backups + trofeos + tiempo de juego Usuario 1)
  │   └── user_<id_2>/          (partida independiente Usuario 2)
  └── logs/
      └── totk.log

Controles en DualSense (PS5):
  • ○ (Círculo)       = Confirmar / Interactuar (Switch A)
  • × (Equis)         = Cancelar / Correr       (Switch B)
  • △ (Triángulo)     = Saltar                  (Switch X)
  • □ (Cuadrado)      = Atacar                  (Switch Y)
  • Touchpad + Options = Abrir menú de ajustes en pantalla
  • L3 + R3           = Mostrar/cambiar overlay de FPS y rendimiento
======================================================================
"""


def _assert_safe_remote(remote_path: str) -> None:
    norm = "/" + remote_path.lstrip("/")
    if not any(norm == p or norm.startswith(p + "/") for p in ALLOWED_REMOTE_PREFIXES):
        raise ValueError(f"Refusing to write outside TOTK PS5 paths: {remote_path}")


class PS5Deployer:
    def __init__(
        self,
        host: str,
        port: int = 2121,
        timeout: int = 60,
        log_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.log = log_fn or (lambda msg: print(msg, flush=True))
        self.ftp = ftplib.FTP()
        self.ftp.connect(host, port, timeout=timeout)
        self.ftp.login()
        self.ftp.set_pasv(True)
        self.log(f"[ftp] Connected to {host}:{port}")

    def close(self) -> None:
        try:
            self.ftp.quit()
        except Exception:
            try:
                self.ftp.close()
            except Exception:
                pass

    def mkdir_p(self, remote_dir: str) -> None:
        _assert_safe_remote(remote_dir)
        parts = [p for p in remote_dir.strip("/").split("/") if p]
        cur = ""
        for part in parts:
            cur += "/" + part
            try:
                self.ftp.sendcmd(f"MKD {cur}")
            except ftplib.error_perm:
                pass

    def list_sizes(self, remote_dir: str) -> dict[str, int]:
        sizes: dict[str, int] = {}
        try:
            lines: list[str] = []
            self.ftp.retrlines(f"LIST {remote_dir}", lines.append)
            for line in lines:
                cols = line.split(None, 8)
                if len(cols) >= 9 and not cols[0].startswith("d"):
                    sizes[cols[8]] = int(cols[4])
        except Exception:
            pass
        return sizes

    def list_dirs(self, remote_dir: str) -> list[str]:
        _assert_safe_remote(remote_dir)
        dirs: list[str] = []
        try:
            lines: list[str] = []
            self.ftp.retrlines(f"LIST {remote_dir}", lines.append)
            for line in lines:
                cols = line.split(None, 8)
                if len(cols) >= 9 and cols[0].startswith("d"):
                    name = cols[8].strip()
                    if name not in (".", ".."):
                        dirs.append(name)
        except Exception:
            pass
        return sorted(dirs, key=str.lower)

    def rm_rf(self, remote_path: str) -> None:
        _assert_safe_remote(remote_path)
        lines: list[str] = []
        try:
            self.ftp.retrlines(f"LIST {remote_path}", lines.append)
        except Exception:
            self.delete_quiet(remote_path)
            return
        for line in lines:
            cols = line.split(None, 8)
            if len(cols) < 9:
                continue
            name = cols[8].strip()
            if name in (".", ".."):
                continue
            child = f"{remote_path.rstrip('/')}/{name}"
            if cols[0].startswith("d"):
                self.rm_rf(child)
            else:
                self.delete_quiet(child)
        try:
            self.ftp.rmd(remote_path)
        except Exception:
            pass

    def delete_quiet(self, remote_path: str) -> None:
        _assert_safe_remote(remote_path)
        try:
            self.ftp.delete(remote_path)
        except ftplib.error_reply as exc:
            # PS5 ftpsrv returns "226 File deleted" instead of 250
            if not str(exc).startswith("226"):
                raise
        except ftplib.error_perm:
            pass

    def chmod_777(self, remote_path: str) -> None:
        try:
            self.ftp.sendcmd(f"SITE CHMOD 777 {remote_path}")
        except Exception:
            pass

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        existing_sizes: dict[str, int] | None = None,
        force: bool = False,
        delete_first: bool = False,
    ) -> None:
        _assert_safe_remote(remote_path)
        if not local_path.is_file():
            raise FileNotFoundError(local_path)
        total = local_path.stat().st_size
        name = remote_path.rsplit("/", 1)[-1]
        if not force and existing_sizes is not None and existing_sizes.get(name) == total:
            self.log(f"[skip] {remote_path} already present ({total:,} bytes)")
            return

        if delete_first:
            self.delete_quiet(remote_path)

        sent = 0
        t0 = time.monotonic()
        last_pct = -10

        def on_chunk(chunk: bytes) -> None:
            nonlocal sent, last_pct
            sent += len(chunk)
            if total >= 25 * 1024 * 1024:
                pct = int(sent * 100 / total)
                if pct >= last_pct + 10 or sent == total:
                    last_pct = pct
                    elapsed = max(0.01, time.monotonic() - t0)
                    mbps = (sent / (1024 * 1024)) / elapsed
                    self.log(
                        f"  [upload] {name}: {pct:3d}% "
                        f"({sent / (1024**2):.1f}/{total / (1024**2):.1f} MiB, {mbps:.1f} MiB/s)"
                    )

        self.log(f"[put] {local_path.name} ({total / (1024**2):.2f} MiB) -> {remote_path}")
        try:
            with local_path.open("rb") as fp:
                self.ftp.storbinary(f"STOR {remote_path}", fp, blocksize=512 * 1024, callback=on_chunk)
        except ftplib.error_perm as exc:
            if "Text file busy" in str(exc) or "550" in str(exc):
                raise RuntimeError(
                    f"PS5 rechazó escribir {remote_path} ({exc}). "
                    "Cierra Tears of the Kingdom en la PS5 e inténtalo de nuevo."
                ) from exc
            raise
        self.chmod_777(remote_path)

    def upload_dir(
        self,
        local_dir: Path,
        remote_dir: str,
        force: bool = False,
    ) -> int:
        _assert_safe_remote(remote_dir)
        if not local_dir.is_dir():
            return 0
        self.mkdir_p(remote_dir)
        self.chmod_777(remote_dir)
        count = 0
        existing = self.list_sizes(remote_dir)
        for entry in sorted(local_dir.iterdir()):
            rpath = f"{remote_dir}/{entry.name}"
            if entry.is_dir():
                count += self.upload_dir(entry, rpath, force=force)
            elif entry.is_file():
                self.upload_file(entry, rpath, existing_sizes=existing, force=force)
                count += 1
        return count


def deploy_to_ps5(
    host: str,
    port: int,
    out_root: Path,
    *,
    exefs_dir: Path | None = None,
    romfs_bin: Path | None = None,
    upload_title: bool = True,
    upload_prompts: bool = True,
    upload_shaders: bool = True,
    upload_mods: bool = True,
    upload_ini: bool = True,
    upload_romfs: bool = False,
    force_eboot: bool = True,
    log_fn: Callable[[str], None] | None = None,
) -> None:
    """Deploy built TOTK PS5 output directory to a jailbroken PS5 over FTP."""
    log = log_fn or (lambda msg: print(msg, flush=True))
    title_dir = out_root / "PPSA99199"
    data_dir = out_root / "data_totk_ps5"

    d = PS5Deployer(host, port, log_fn=log)
    try:
        # 1. Prepare /data/totk-ps5/ skeleton
        for rdir in (
            "/data/totk-ps5",
            "/data/totk-ps5/exefs",
            "/data/totk-ps5/romfs",
            "/data/totk-ps5/shader-cache",
            "/data/totk-ps5/mods",
            "/data/totk-ps5/saves",
            "/data/totk-ps5/tmp",
            "/data/totk-ps5/logs",
        ):
            d.mkdir_p(rdir)
            d.chmod_777(rdir)

        data_sizes = d.list_sizes("/data/totk-ps5")

        # 2. totk.ini + romfs-index.bin
        if upload_ini and (data_dir / "totk.ini").is_file():
            d.upload_file(data_dir / "totk.ini", "/data/totk-ps5/totk.ini", force=True, delete_first=True)
        if (data_dir / "romfs-index.bin").is_file():
            d.upload_file(data_dir / "romfs-index.bin", "/data/totk-ps5/romfs-index.bin", data_sizes)

        # 3. Pre-translated shader caches
        if upload_shaders:
            for fname in ("totk_xlate.id", "shader-prepared.bin", "shader-programs.bin", "shader-answers.bin"):
                src = data_dir / fname
                if src.is_file():
                    d.upload_file(src, f"/data/totk-ps5/{fname}", data_sizes)
            pack = data_dir / "shader-cache" / "shader-cache.pack"
            if pack.is_file():
                sc_sizes = d.list_sizes("/data/totk-ps5/shader-cache")
                d.upload_file(pack, "/data/totk-ps5/shader-cache/shader-cache.pack", sc_sizes)

        # 4. PlayStation button prompts overlays
        if upload_prompts:
            for pfolder in ("romfs-patches-playstation", "romfs-patches-playstation-xbox"):
                src_dir = data_dir / pfolder
                if src_dir.is_dir():
                    n = d.upload_dir(src_dir, f"/data/totk-ps5/{pfolder}")
                    log(f"[ok] Uploaded {pfolder} ({n} files)")

        # 5. User MODS (RomFS)
        if upload_mods and (data_dir / "mods").is_dir():
            mod_entries = [p for p in (data_dir / "mods").iterdir() if p.is_dir()]
            if mod_entries:
                n = d.upload_dir(data_dir / "mods", "/data/totk-ps5/mods")
                log(f"[ok] Uploaded {len(mod_entries)} mod(s) ({n} files) to /data/totk-ps5/mods")

        # 6. ExeFS binaries
        if exefs_dir and exefs_dir.is_dir():
            exefs_sizes = d.list_sizes("/data/totk-ps5/exefs")
            for fname in ("main", "main.npdm", "sdk", "subsdk0"):
                src = exefs_dir / fname
                if src.is_file():
                    d.upload_file(src, f"/data/totk-ps5/exefs/{fname}", exefs_sizes)

        # 7. /data/homebrew/PPSA99199/ (param.json last so ShadowMountPlus sees complete title)
        if upload_title and title_dir.is_dir():
            for rdir in (
                "/data/homebrew/PPSA99199",
                "/data/homebrew/PPSA99199/sce_module",
                "/data/homebrew/PPSA99199/sce_sys",
            ):
                d.mkdir_p(rdir)
                d.chmod_777(rdir)

            mod_sizes = d.list_sizes("/data/homebrew/PPSA99199/sce_module")
            sys_sizes = d.list_sizes("/data/homebrew/PPSA99199/sce_sys")
            title_sizes = d.list_sizes("/data/homebrew/PPSA99199")

            if (title_dir / "eboot.bin").is_file():
                d.upload_file(
                    title_dir / "eboot.bin",
                    "/data/homebrew/PPSA99199/eboot.bin",
                    existing_sizes=title_sizes,
                    force=force_eboot,
                    delete_first=force_eboot,
                )
            libc = title_dir / "sce_module" / "libc.prx"
            if libc.is_file():
                d.upload_file(libc, "/data/homebrew/PPSA99199/sce_module/libc.prx", mod_sizes)
            for fname in ("icon0.png", "pic0.dds", "pic1.dds"):
                art = title_dir / "sce_sys" / fname
                if art.is_file():
                    d.upload_file(art, f"/data/homebrew/PPSA99199/sce_sys/{fname}", sys_sizes)
            param = title_dir / "sce_sys" / "param.json"
            if param.is_file():
                d.upload_file(param, "/data/homebrew/PPSA99199/sce_sys/param.json", sys_sizes)
            log("[ok] PPSA99199 title uploaded!")

        # 8. Optional full romfs.bin (~15.86 GiB)
        if upload_romfs and romfs_bin and romfs_bin.is_file():
            romfs_sizes = d.list_sizes("/data/totk-ps5/romfs")
            d.upload_file(romfs_bin, "/data/totk-ps5/romfs/romfs.bin", romfs_sizes)
            log("[ok] Full romfs.bin uploaded!")

        log("[ok] PS5 FTP deploy complete!")
    finally:
        d.close()
