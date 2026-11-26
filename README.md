# PS5 Tears of the Kingdom Recomp (`PPSA99199`)

[![License: MIT](https://img.shields.io/badge/License-MIT-2EE6A6.svg)](LICENSE)
[![Target](https://img.shields.io/badge/Target-PS5%20(Mesa%20RADV)-38BDF8.svg)](#features)
[![Builder](https://img.shields.io/badge/Builder-Linux%20x64%20AppImage-E6C36A.svg)](#quick-start-appimage)

> **Native PlayStation 5 port of *The Legend of Zelda: Tears of the Kingdom* (v1.4.3)** built via static AArch64 → x86\_64 recompilation (`-O2 -march=znver2`), direct `VK_KHR_display` rendering on Mesa RADV (`NAVI21`), AMD FSR 3.1.5 Frame Generation (`mvprev`), DualSense with PlayStation button prompts, 38 native PS5 Trophies, automatic per-PS5-user save isolation, and an all-in-one bilingual (**ES / EN**) Linux AppImage builder with a built-in **GameBanana Mod Browser**.
>
> **Port nativo para PlayStation 5 de *The Legend of Zelda: Tears of the Kingdom* (v1.4.3)** con recompilación estática AArch64 → x86\_64 (`-O2 -march=znver2`), renderizado directo `VK_KHR_display` en Mesa RADV, AMD FSR 3.1.5 Frame Generation (`mvprev`), DualSense con íconos PlayStation, 38 Trofeos PS5 nativos, partidas aisladas por usuario de PS5 y un AppImage todo-en-uno bilingüe (**ES / EN**) con buscador integrado de mods de **GameBanana**.

> [!IMPORTANT]
> **Legal Notice / Aviso Legal:** This repository and the pre-release AppImage contain **ZERO Nintendo game data, ROMs, ExeFS/RomFS assets, shaders, or encryption keys**. You must supply your own legally dumped copy of *Tears of the Kingdom* (`.xci`/`.nsp` + `prod.keys`, or extracted `exefs/` + `romfs/`).

---

## Features / Características Principales

- **Native 1440p & 1080p @ 60 Hz / 120 Hz (`VK_KHR_display`):** Automatic HDMI display mode selection (`2560×1440 @ 119.88 Hz` or `59.94 Hz`, `1920×1080 @ 119.88 Hz` or `59.94 Hz`) via `output_res` and `TOTK_PS5_HZ` in `totk.ini`.
- **AMD FSR 3.1.5 Frame Generation (`45–60 FPS` @ 1440p 120 Hz):**
  - FidelityFX SDK 1.1.4 Frame Interpolation & Optical Flow running natively on PS5 RADV (`NAVI21`) with our PS5 2-byte `wchar_t` UTF-16 fix (`0.79–1.0 ms` CPU overhead, `0.005 ms` GPU wait).
  - Full **per-object motion vectors (`mvprev`, 14,765 pre-translated vertex shader variants)** eliminating character shimmer around Link (`TOTK_FG_OBJECTS=1`), toggleable live in `Touchpad + Options → Frame rate → Frame generation`.
- **DualSense + Default PlayStation Button Icons (`△ ○ × □`):**
  - Native `libScePad` DualSense input and `libSceAudioOut` 48 kHz HDMI audio.
  - Bundled PlayStation glyph RomFS overlay (`romfs-patches-playstation` for `○` Confirm / `×` Cancel, plus `romfs-patches-playstation-xbox` for `×` Confirm / `○` Cancel).
- **Automatic Per-PS5-User Save Isolation (`libSceUserService`):**
  - Detects the signed-in PS5 user (`sceUserServiceGetInitialUser`) and isolates saves, backups, `account.uid`, playtime, and trophies under **`/data/totk-ps5/saves/user_<uid>/`**.
  - Multiple players on the same PS5 (Profile A, Profile B, etc.) automatically get completely independent save slots and trophy progress.
  - Legacy saves from `/data/totk-ps5/saves/` are migrated automatically and non-destructively on first launch.
- **38 Native PS5 Trophies (17 Bronze, 12 Silver, 8 Gold, 1 Platinum):**
  - Verified directly against TOTK v1.4.3 `progress.sav` MurmurHash3-32 flag hashes (`0.00 ms` gameplay overhead — scanned on save mount/commit).
  - Triggers native **PS5 OS notifications** (`sceKernelSendNotificationRequest`), a sleek top-right **ImGui trophy toast banner**, a dedicated **`Trofeos` tab** inside `Touchpad + Options`, and per-user persistence in `<TOTK_PROFILE_DIR>/trophies.json`.
- **Native 1080p VP9 Cutscenes:** Multi-threaded slice decoding via static `libavcodec.a` + `libdav1d.a` + `libavutil.a` (verified 6,421 frames @ 1080p with 0 errors).
- **All-in-One Bilingual (ES / EN) Linux AppImage (`~153 MiB`):**
  - Zero external setup — bundles `clang`, `ld.lld`, `ps5-native-tool`, Mesa RADV PS5, PS5 SDK, `libtotkrt_ps5.a`, `hactool` + `extract.py`, `recomp/gen.py`, `make_romfs_patches.py`, and game-free `prep_mvprev` + `totk_xlate` (with patch `0015-motion-previous-position`).
  - **Built-in GameBanana Mod Browser (TOTK Game ID `7617`):** Search, pick `.zip` archives, auto-detect `romfs/` roots, stage into `/data/totk-ps5/mods/`, and push directly to PS5 over FTP.
  - **Custom PS5 Artwork:** Ships with custom `icon0.png` + 4K BC7 `pic0.dds`/`pic1.dds`, plus optional cover download from any PNG/JPG URL.
  - **Safe FTP Deployer (`SAFE_PREFIXES`):** Writes strictly inside `/data/homebrew/PPSA99199` and `/data/totk-ps5`, skips already-uploaded files by size, never overwrites saves, and uploads `param.json` last for ShadowMountPlus / Itemzflow.
- **Zero-Overhead Hang Detector Watchdog:** Automatically monitors `gfx_counters.frames` every 2 s (`0.000%` CPU) and dumps full thread backtraces (`SIGUSR1`) + free/flexible memory to `/data/totk-ps5/logs/totk.log` if rendering stalls for 8 s.

---

## DualSense Controls / Controles en PS5

| DualSense Button | Action / Acción | Switch Equivalent |
|---|---|---|
| **`○` (Circle)** | Confirm / Interact *(default)* | `A` |
| **`×` (Cross)** | Cancel / Sprint *(default)* | `B` |
| **`△` (Triangle)** | Jump | `X` |
| **`□` (Square)** | Attack | `Y` |
| **`Touchpad (click) + Options`** | Open In-Game Settings, Mods & **Trophies** Menu | Menu |
| **`L3 + R3`** | Cycle FPS / Performance Overlay | Overlay |

*(You can switch between Nintendo `○=Confirm` and Western `×=Confirm` layouts anytime inside `Touchpad + Options → Controls`.)*

---

## Quick Start (AppImage) / Inicio Rápido

### 1. GUI (Recommended / Recomendado)
Download `PS5TotkBuilder-v0.1.0-linux-x64.AppImage` from **Releases**, mark executable, and launch:
```bash
chmod +x PS5TotkBuilder-v0.1.0-linux-x64.AppImage
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage
```
1. Select your **Base Game (`.xci`/`.nsp`)** + optional **Update `.nsp` (v1.4.3)** + **`prod.keys`** (or already-extracted **`exefs/`** + **`romfs/`** folders).
2. *(Optional)* Open **`○ Mods & GameBanana`** to browse and inject RomFS mods (e.g., *Serfrost's Defogger (Native)*).
3. Open **`× Deploy to PS5`**, enter your PS5's local `ftpsrv` IP (port `2121`), check **"Upload `romfs.bin`"** on first install, and click **`⚡ Build + Deploy to PS5`**.

### 2. CLI (Headless / Automation)
From `.xci`/`.nsp` + `prod.keys`:
```bash
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
  --game /path/to/totk_base.xci \
  --update /path/to/totk_v143.nsp \
  --keys /path/to/prod.keys \
  --pretranslate-shaders \
  --res 2560x1440 --hz 120 --frame-gen fsr3 --scale game --lang es-419 \
  --deploy-ftp <PS5_IP> --ftp-port 2121 --deploy-romfs
```
From already-extracted `exefs/` + `romfs/`:
```bash
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
  --exefs /path/to/exefs --romfs /path/to/romfs \
  --pretranslate-shaders \
  --mod /path/to/mod.zip \
  --deploy-ftp <PS5_IP> --ftp-port 2121
```
Inspect PS5 directory layout or verify toolchain:
```bash
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage --check
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage --show-layout
```

---

## Exact PS5 Directory Layout / Estructura Exacta en la PS5

```text
/data/homebrew/PPSA99199/
  ├── eboot.bin                       # Signed PS5 FSELF (-O2 -march=znver2)
  ├── sce_module/
  │   └── libc.prx
  └── sce_sys/
      ├── icon0.png                   # 512x512 cover icon
      ├── pic0.dds                    # 4K BC7 title logo
      ├── pic1.dds                    # 4K BC7 background artwork
      └── param.json                  # Uploaded last for ShadowMountPlus

/data/totk-ps5/
  ├── totk.ini                        # PS5 config (1440p@120Hz, FSR 3 FG, low-VRAM limits)
  ├── romfs-index.bin                 # RomFS index
  ├── totk_xlate.id                   # PS5 RADV shader cache identity
  ├── shader-prepared.bin             # Pre-warmed shader variant index (43,432 variants)
  ├── shader-cache/
  │   └── shader-cache.pack           # Pre-translated RADV + mvprev shader pack (~2.7 GiB)
  ├── romfs-patches-playstation/      # PlayStation prompts (○ Confirm / × Cancel)
  ├── romfs-patches-playstation-xbox/ # PlayStation prompts (× Confirm / ○ Cancel)
  ├── exefs/                          # main, main.npdm, sdk, subsdk0 (user supplied)
  ├── romfs/
  │   └── romfs.bin                   # Extracted RomFS ~15.86 GiB (user supplied)
  ├── mods/                           # RomFS mods (toggleable in Touchpad + Options)
  │   └── <mod_name>/romfs/...
  ├── saves/                          # Automatically isolated per PS5 user profile
  │   ├── user_<ps5_uid_1>/           # Save slots, account.uid, playtime.txt, trophies.json
  │   └── user_<ps5_uid_2>/
  └── logs/
      └── totk.log                    # Runtime telemetry & hang-detector backtraces
```

---

## Performance & Known Limitations / Rendimiento y Limitaciones

| Profile on PS5 (FW 13.40, RADV `NAVI21`) | Resolution | FPS (Great Sky Island) | Notes |
|---|---|---|---|
| **Recommended (Default)** | `2560×1440 @ 120 Hz` (`render_scale = game`, `2128×1200`) | **45–60 FPS** (`FSR 3 FG` + `TOTK_FG_OBJECTS=1`) | Sharp 1440p, zero character shimmer, ~1.6 GiB VRAM headroom |
| **Max Fluidity** | `2560×1440 @ 120 Hz` (`TOTK_FG_OBJECTS=0`) | **55–60 FPS** (`FSR 3 FG`) | Slight halo around Link in motion |
| **Native (No FG)** | `2560×1440 @ 60/120 Hz` (`frame_gen = off`) | **28–36 FPS** (open world) / **49–60 FPS** (caves) | Zero interpolation latency |

**Known Limitations (Pre-Release `v0.1.0-alpha`):**
- **HDR10 & VRR:** The precompiled `ps5-kit` Mesa RADV `VK_KHR_display` WSI currently exposes only 8-bit SDR swapchains (`B8G8R8A8_UNORM` / `B8G8R8A8_SRGB`). Native HDR10 PQ (`A2B10G10R10` / `ST2084`) and VRR require rebuilding Mesa RADV's PS5 WSI against 10-bit `libSceVideoOut`.
- **4K (`3840×2160`) output:** Exceeds PS5's unified VRAM headroom with TOTK's render targets; use **`2560×1440`** with `render_scale = game` (`83%`) or `1920×1080`.
- **Do NOT enable `scene_upscaler = fsr3` or `replay_workers > 0`** on PS5 (causes heavy CPU replay overhead).
- **Mods with custom `.bfsha`/`.bnsh` shaders or PC ReShade presets:** PS5 has no runtime shader translator (`totk_xlate`), so ReShade presets do not run and new `.bfsha` shaders require PC pre-translation. Standard RomFS mods (outfits, models, UI, `EnvPalette` defoggers like *Serfrost's Defogger*, gameplay tweaks) work out of the box.
- **Occasional long-session freezes:** An always-on `0.000 ms` hang detector is now active in `eboot.bin` to capture exact thread backtraces in `/data/totk-ps5/logs/totk.log` for ongoing stability fixes.

---

## Building From Source / Compilar Desde Código Fuente

Requires Linux x64, Python 3.12+, `clang`, `ninja`, `.NET 10 SDK` (for `totk_xlate`), `appimagetool`, an upstream checkout of `totk-linux-native-recomp` (set via `TOTK_UPSTREAM_SRC` or sibling folder `../totk-linux-native-recomp`), and an extracted `third_party/ps5-kit` toolchain.

```bash
# 1. Build host shader pre-translator (with mvprev patch 0015) + prep_mvprev + hactool
python3 ../totk-linux-native-recomp/tools/build_xlate.py --out build/xlate_mvprev
clang -O2 -I../totk-linux-native-recomp/runtime \
  scripts/prep_mvprev_main.c \
  ../totk-linux-native-recomp/runtime/{gfx_shader.c,cfg.c,platform/linux.c,platform/common.c,sha256.c} \
  -lpthread -ldl -lm -o build/xlate_mvprev/prep_mvprev
python3 ../totk-linux-native-recomp/tools/build_hactool.py --src build/hactool_src --out build/hactool

# 2. Cross-compile PS5 runtime + archive libtotkrt_ps5.a
python3 scripts/probe_runtime_compile.py
python3 scripts/link_runtime_ps5.py
.venv/bin/python -m builder.cli --build-runtime-lib

# 3. Package 100% self-contained AppImage (zero game data)
python3 scripts/make_appimage.py
# Output: out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage

# 4. Run verification tests
pytest -v tests/test_totk_ps5_project.py
```

---

## Credits & License

- **Upstream TOTK Recompilation Runtime & Lifter:** `totk-linux-native-recomp` / Savage Wind contributors & MacNativeGames shader/extraction tooling.
- **PS5 Homebrew Toolchain & Mesa RADV PS5:** PS5 homebrew & `ps5-kit` / Mesa RADV contributors.
- **AMD FidelityFX SDK 1.1.4 (FSR 3.1.5):** Advanced Micro Devices, Inc. (MIT).
- **License:** Released under the **MIT License** — see [LICENSE](LICENSE).
- **Legal notice / Aviso legal:** see [NOTICE](NOTICE) — zero Nintendo data, keys or ROMs included; bring your own legal dump.
