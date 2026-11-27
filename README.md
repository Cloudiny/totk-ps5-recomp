# PS5 Tears of the Kingdom Recomp (`PPSA99199`)

[![License: MIT](https://img.shields.io/badge/License-MIT-2EE6A6.svg)](LICENSE)
[![Target](https://img.shields.io/badge/Target-PS5%20(Mesa%20RADV)-38BDF8.svg)](#features--características-principales)
[![Builder](https://img.shields.io/badge/Builder-Linux%20x64%20AppImage-5CE1E6.svg)](#quick-start-appimage--inicio-rápido)

> **Native PlayStation 5 port of *The Legend of Zelda: Tears of the Kingdom* (v1.4.3)** built via static AArch64 → x86\_64 recompilation (`-O2`/`-O3` hot-chunk Zen 2 + `--symbol-ordering-file`), cached Vulkan ICD dispatch on Mesa RADV (`NAVI21`) with direct `VK_KHR_display` rendering, AMD FSR 3.1.5 Frame Generation (`mvprev`), native DualSense with SixAxis gyro/accelerometer aiming and PlayStation button prompts (compatible with RomFS text mods), built-in `MacNativeGames` complete shader pre-translation, 38 native PS5 Trophies, automatic per-PS5-user save isolation, and a 100% self-contained bilingual (**ES / EN**) PyQt6 Linux AppImage builder with a filtered **GameBanana PS5-RomFS Mod Browser**.
>
> **Port nativo para PlayStation 5 de *The Legend of Zelda: Tears of the Kingdom* (v1.4.3)** con recompilación estática AArch64 → x86\_64 (`-O2`/`-O3` Zen 2 en funciones críticas), despacho Vulkan cacheado sobre `VK_KHR_display` en Mesa RADV, AMD FSR 3.1.5 Frame Generation (`mvprev`), DualSense nativo con giroscopio/acelerómetro e íconos PlayStation (compatibles con mods de `Mals/`), pre-traducción completa de shaders `MacNativeGames`, 38 Trofeos PS5 nativos, partidas aisladas por usuario de PS5 y un AppImage Linux 100% autocontenido bilingüe (**ES / EN**) con interfaz editorial PyQt6 y buscador filtrado de mods **GameBanana**.

> [!IMPORTANT]
> **Legal Notice / Aviso Legal:** This repository and its release AppImage contain **ZERO Nintendo game data, ROMs, ExeFS/RomFS assets, shaders, or encryption keys**. You must supply your own legally dumped copy of *Tears of the Kingdom* (v1.4.3 `.xci`/`.nsp` + `prod.keys`, or extracted `exefs/` + `romfs/`).

---

## Features / Características Principales

- **Native 1440p & 1080p @ 60 Hz / 120 Hz (`VK_KHR_display`):** Automatic HDMI display mode selection (`2560×1440 @ 119.88 Hz` or `59.94 Hz`, `1920×1080 @ 119.88 Hz` or `59.94 Hz`) via `output_res` and `TOTK_PS5_HZ` in `totk.ini`.
- **60 FPS Native Patches + AMD FSR 3.1.5 Frame Generation (`45–60 FPS` @ 1440p 120 Hz):**
  - Built-in `fps60`, `realtime`, `cloth`, `bounce`, and `climb` runtime patches.
  - FidelityFX SDK 1.1.4 Frame Interpolation & Optical Flow running natively on PS5 RADV (`NAVI21`) with our PS5 2-byte `wchar_t` UTF-16 fix (`0.79–1.0 ms` CPU overhead, `0.005 ms` GPU wait).
  - Full **per-object motion vectors (`mvprev`, 14,765+ pre-translated vertex shader variants)** eliminating ghosting around Link (`TOTK_FG_OBJECTS=1`), toggleable live in `Touchpad + Options → Frame rate → Frame generation`.
- **Native DualSense + SixAxis Gyro Aiming + PlayStation Button Icons (`△ ○ × □`, `L1/R1/L2/R2`):**
  - Native `libScePad` buttons, rumble, and verified `ScePadData` SixAxis gyro/accelerometer ABI (`acceleration @ 0x1C`, `angularVelocity @ 0x28`) for stable bow, Ultrahand, and Scope aiming, plus `libSceAudioOut` 48 kHz HDMI audio.
  - Bundled PlayStation glyph RomFS overlay (`romfs-patches-playstation` for `○` Confirm / `×` Cancel, plus `romfs-patches-playstation-xbox` for `×` Confirm / `○` Cancel), engineered to stay active even when RomFS mods override `Mals/` text archives.
- **Built-In Complete Shader Pre-Translation (`MacNativeGames`, MIT):**
  - Downloads the MIT-licensed `MacNativeGames` shader variant list directly from the GUI or CLI (`--download-shaders` / `--deploy-shaders-only`), translates non-default + `mvprev` variants offline for PS5 RADV on PC, repacks `shader-cache.pack`, and pushes `totk_xlate.id`, `shader-prepared.bin`, and `shader-cache.pack` atomically over FTP without touching saves or `totk.ini`.
- **Automatic Per-PS5-User Save Isolation (`libSceUserService`):**
  - Detects the signed-in PS5 user (`sceUserServiceGetInitialUser`) and isolates saves, backups, `account.uid`, playtime, and trophies under **`/data/totk-ps5/saves/user_<uid>/`**.
  - Legacy saves from `/data/totk-ps5/saves/` are migrated automatically and non-destructively on first launch.
- **38 Native PS5 Trophies (17 Bronze, 12 Silver, 8 Gold, 1 Platinum):**
  - Verified directly against TOTK v1.4.3 `progress.sav` MurmurHash3-32 flag hashes (`0.00 ms` gameplay overhead — scanned on save mount/commit).
  - Triggers native **PS5 OS notifications** (`sceKernelSendNotificationRequest`), a top-right **ImGui trophy toast banner**, a dedicated **`Trofeos` tab** inside `Touchpad + Options`, and per-user persistence in `<TOTK_PROFILE_DIR>/trophies.json`.
- **Native 1080p VP9 Cutscenes with Linear 1440p Scaling:** Multi-threaded slice decoding via static `libavcodec.a` + `libdav1d.a` + `libavutil.a` (`EAGAIN`/`EOF` resilient), paired with forced linear NV12 plane sampling (`vk_sampler_movie_linear_locked`) and `dynamic_res = 0` so pre-rendered `.webm` and real-time cutscenes stay crisp at `2560×1440`.
- **100% Self-Contained Bilingual (ES / EN) PyQt6 Linux AppImage:**
  - **Zero host dependencies** — bundles standalone **CPython 3.13**, **PyQt6**, **Pillow**, `capstone`, `lz4`, `zstandard`, `numpy`, `fontTools`, `clang`, `ld.lld`, `llvm-nm`, `ps5-native-tool`, Mesa RADV PS5, PS5 SDK, `libtotkrt_ps5.a`, `hactool` + `extract.py`, `recomp/gen.py`, `make_romfs_patches.py`, and game-free `prep_mvprev` + `totk_xlate` (with patch `0015-motion-previous-position`).
  - **Editorial TOTK UI + Startup PS5 FTP Connect:** Prompts to connect to your PS5 (`ftpsrv`) on startup or on demand, remembers your last LAN IP locally (`~/.config/ps5-totk-builder/ui_prefs.json`), and lists/manages active mods directly on `/data/totk-ps5/mods/`.
  - **Filtered GameBanana Mod Browser (TOTK Game ID `7617`):** 2-column visual card grid with thumbnails, category tabs with live counts, full detail modal with gallery zoom, live MB/% download & FTP progress banner, and automatic filtering that hides incompatible PC ReShade / Switch ExeFS code-patch (`.ips`/`.pchtxt`/`subsdk`) mods by default.
  - **Custom PS5 Artwork:** Includes custom `icon0.png` + 4K BC7 `pic0.dds`/`pic1.dds`, plus 1-click custom `icon0.png` download from any PNG/JPG URL.
  - **Safe FTP Deployer (`ALLOWED_REMOTE_PREFIXES`):** Writes strictly inside `/data/homebrew/PPSA99199` and `/data/totk-ps5`, skips unchanged files by size, never overwrites saves, and uploads `param.json` last for ShadowMountPlus / Itemzflow.
- **Zero-Overhead Hang Detector Watchdog:** Monitors `gfx_counters.frames` every 2 s (`0.000%` CPU) and logs full thread backtraces (`SIGUSR1`) + memory stats to `/data/totk-ps5/logs/totk.log` if rendering stalls for 8 s.

---

## DualSense Controls / Controles en PS5

| DualSense Button | Action / Acción | Switch Equivalent |
|---|---|---|
| **`○` (Circle)** | Confirm / Interact *(default)* | `A` |
| **`×` (Cross)** | Cancel / Sprint *(default)* | `B` |
| **`△` (Triangle)** | Jump | `X` |
| **`□` (Square)** | Attack | `Y` |
| **SixAxis Motion** | Gyro / Accelerometer Aiming (Bow, Ultrahand, Scope) | Gyro / Accel |
| **`Touchpad (click) + Options`** | Open In-Game Settings, Mods & **Trophies** Menu | Menu |
| **`L3 + R3`** | Cycle FPS / Performance Overlay | Overlay |

*(You can switch between Nintendo `○=Confirm` and Western `×=Confirm` layouts anytime inside `Touchpad + Options → Controls`.)*

---

## Quick Start (AppImage) / Inicio Rápido

### 1. GUI (Recommended / Recomendado)
Download `PS5TotkBuilder-v0.1.0-linux-x64.AppImage` from **Releases**, mark executable, and launch on any Linux x64 distro (Ubuntu, SteamOS, Arch, Fedora, Debian, Mint — no Python or PyQt6 installation needed):
```bash
chmod +x PS5TotkBuilder-v0.1.0-linux-x64.AppImage
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage
```
1. *(Optional)* Connect to your PS5 (`ftpsrv` IP + port `2121`) in the startup prompt, or click **Continue Offline**.
2. Select your **Base Game (`.xci`/`.nsp`)** + optional **Update `.nsp` (v1.4.3)** + **`prod.keys`** (or already-extracted **`exefs/`** + **`romfs/`** folders).
3. *(Optional)* Open **`○ Mods & GameBanana`** to browse PS5-compatible RomFS mods and install/delete directly on your PS5.
4. Open **`× Deploy to PS5`**, check **"Upload `romfs.bin`"** on first install, and click **`⚡ Build + Deploy to PS5`** (or use the **Complete Shaders (MacNativeGames)** card to download, pre-translate, and atomically push the full PS5 shader pack).

### 2. CLI (Headless / Automation)
From `.xci`/`.nsp` + `prod.keys`:
```bash
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
  --game /path/to/totk_base.xci \
  --update /path/to/totk_v143.nsp \
  --keys /path/to/prod.keys \
  --pretranslate-shaders \
  --res 2560x1440 --hz 120 --frame-gen fsr3 --scale 75 --fps-limit 60 --lang es-419 \
  --deploy-ftp <PS5_IP> --ftp-port 2121 --deploy-romfs
```
Download & pre-translate the full `MacNativeGames` shader pack and push atomically over FTP:
```bash
./PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
  --download-shaders \
  --deploy-shaders-only \
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
  ├── eboot.bin                       # Signed PS5 FSELF (-O2/-O3 Zen 2 + -O3 runtime)
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
  ├── shader-prepared.bin             # Pre-warmed shader variant index
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

| Profile on PS5 (RADV `NAVI21`) | Resolution | FPS (Great Sky Island) | Notes |
|---|---|---|---|
| **Recommended (Default)** | `2560×1440 @ 120 Hz` (`render_scale = 75`, `1920×1080` locked 3D scene) | **60 FPS** (`FSR 3 FG` + `fps_limit = 60` + `TOTK_FG_OBJECTS=1`) | Native 1440p HUD/text, exact 2-vblank `119.88 Hz` FIFO pacing, zero ghosting, crisp cutscenes |
| **Native 1440p (Higher 3D Scale)** | `2560×1440 @ 120 Hz` (`render_scale = game`, `2128×1200`) | **45–60 FPS** (`FSR 3 FG` + `TOTK_FG_OBJECTS=1`) | Higher internal 3D scale, ~1.6 GiB VRAM headroom |
| **Native (No FG)** | `2560×1440 @ 60/120 Hz` (`frame_gen = off`) | **30–54 FPS** (open world / caves) | Zero interpolation latency; `TOTK_SYNC_AHEAD=1` active automatically |

**Known Limitations (`v0.1.0`):**
- **HDR10 & VRR:** The precompiled `ps5-kit` Mesa RADV `VK_KHR_display` WSI currently exposes only 8-bit SDR swapchains (`B8G8R8A8_UNORM` / `B8G8R8A8_SRGB`). On non-VRR `119.88 Hz` `FIFO` displays, keep `fps_limit = 60` with `frame_gen = fsr3` for smooth 1:2 vblank pacing (use `--fps-limit 120` or `display` on VRR displays).
- **4K (`3840×2160`) output:** Exceeds PS5's unified VRAM headroom with TOTK's render targets; use **`2560×1440`** with `render_scale = 75` or `game`.
- **Do NOT enable `scene_upscaler = fsr3` or `replay_workers > 0`** on PS5.
- **ExeFS Code Mods & ReShade Presets:** Switch ExeFS code mods (`.ips`, `.pchtxt`, `subsdk*`) and PC ReShade presets cannot be activated via FTP RomFS alone; the built-in GameBanana browser filters them out by default and blocks incompatible archives. Standard RomFS mods (outfits, models, UI, audio, `EnvPalette` defoggers like *Serfrost's Defogger*) work out of the box.

---

## Building From Source / Compilar Desde Código Fuente

Requires Linux x64, Python 3.12+, `clang`, `ninja`, `unsquashfs`, `appimagetool`, `.NET 10 SDK` (for `totk_xlate`), system dev headers (`vulkan-headers`, `opus`, `zstd`), an upstream checkout of `totk-linux-native-recomp` (set `TOTK_UPSTREAM_SRC` or place beside this repo at `../totk-linux-native-recomp`), and the PS5 RADV/SDK toolchain kit.

```bash
# 1. Bootstrap third-party headers (VMA v3.3.0 + Vulkan/Opus/Zstd headers) and PS5 RADV kit
python3 scripts/setup_deps.py
python3 scripts/extract_ps5_kit.py --appimage /path/to/PS5LongshotPlusBuilder.AppImage

# 2. Build host shader pre-translator (with mvprev patch 0015) + prep_mvprev + hactool
python3 "${TOTK_UPSTREAM_SRC:-../totk-linux-native-recomp}/tools/build_xlate.py" --out build/xlate_mvprev
clang -O2 -I"${TOTK_UPSTREAM_SRC:-../totk-linux-native-recomp}/runtime" \
  scripts/prep_mvprev_main.c \
  "${TOTK_UPSTREAM_SRC:-../totk-linux-native-recomp}"/runtime/{gfx_shader.c,cfg.c,platform/linux.c,platform/common.c,sha256.c} \
  -lpthread -ldl -lm -o build/xlate_mvprev/prep_mvprev
python3 "${TOTK_UPSTREAM_SRC:-../totk-linux-native-recomp}/tools/build_hactool.py" --src build/hactool_src --out build/hactool

# 3. Cross-compile PS5 runtime + archive libtotkrt_ps5.a
python3 scripts/probe_runtime_compile.py
python3 scripts/link_runtime_ps5.py
python3 -m builder.cli --build-runtime-lib

# 4. Package 100% self-contained AppImage (downloads CPython 3.13 standalone + PyQt6 + wheels)
python3 scripts/make_appimage.py
# Output: out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage

# 5. Run verification tests & AppImage self-check
pytest -v tests/
./out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage --check
```

---

## Credits & License

- **Upstream TOTK Recompilation Runtime & Lifter:** `totk-linux-native-recomp` / Savage Wind contributors.
- **Shader Variant List:** `MacNativeGames` (`totk-shaders`, MIT License).
- **PS5 Homebrew Toolchain & Mesa RADV PS5:** `PS5_Vulkan`, `PS5_Longshot_Plus`, OpenOrbis & `ps5-payload-sdk` contributors.
- **AMD FidelityFX SDK 1.1.4 (FSR 3.1.5):** Advanced Micro Devices, Inc. (MIT).
- **License:** Released under the **MIT License** — see [LICENSE](LICENSE).
- **Legal notice & attributions:** see [NOTICE](NOTICE) — zero Nintendo data, keys, or ROMs included; bring your own legal dump.
