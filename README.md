# PS5 Tears of the Kingdom Recomp (`PPSA99199`)

Port nativo de **The Legend of Zelda: Tears of the Kingdom** para **PlayStation 5 (Prospero)** usando Mesa RADV PS5 (`VK_KHR_display`), libScePad (DualSense), libSceAudioOut, FFmpeg VP9 nativo y aislamiento automático de partidas por usuario de PS5 (`libSceUserService`).

## Características principales

- **Video 1440p / 1080p @ 60 Hz o 120 Hz nativo (`VK_KHR_display`)**: selección automática del modo de salida de la TV según `output_res` y `TOTK_PS5_HZ` (`60` o `120`) en `totk.ini`. *(Nota: el Mesa RADV del `ps5-kit` actualmente expone swapchains SDR `BGRA8`, sin formato HDR10 PQ de 10 bits.)*
- **AMD FSR 3.1.5 Frame Generation nativo (`30 → 60 FPS`)**: habilitado en el menú **`Touchpad + Options → Frame rate → Frame generation`**, con soporte completo de vectores de movimiento por objeto (`mvprev`) pre-traducidos en `shader-cache.pack` (`~0.8 ms` CPU / `0.005 ms` espera GPU).
- **Sistema de 38 Trofeos PS5**: 17 Bronce, 12 Plata, 8 Oro y 1 Platino verificados contra `progress.sav`, con notificación nativa del SO de PS5 (`sceKernelSendNotificationRequest`), banner ImGui, pestaña **Trofeos** en `Touchpad + Options` y progreso aislado por usuario en `trophies.json`.
- **Controles DualSense e íconos PlayStation por defecto (`△ ○ × □`)**:
  - **`○` (Círculo)** = Confirmar / Interactuar (Switch `A`)
  - **`×` (Equis)** = Cancelar / Correr (Switch `B`)
  - **`△` (Triángulo)** = Saltar (Switch `X`)
  - **`□` (Cuadrado)** = Atacar (Switch `Y`)
  - **`Touchpad (clic) + Options`** = Abrir menú de opciones y Trofeos
  - **`L3 + R3`** = Mostrar / cambiar overlay de FPS y rendimiento
- **Partidas independientes por usuario de PS5**: cada perfil de PS5 guarda automáticamente en `/data/totk-ps5/saves/user_<id>/` (migración automática sin pérdida desde `/data/totk-ps5/saves/` incluyendo `account.uid`).
- **Cinemáticas VP9 1080p nativas**: decodificación multi-hilo por slices con FFmpeg VP9 (`libavcodec.a` + `libdav1d.a`).
- **Planificación estable en PS5**: `replay_async = 0` por defecto y sin fijación agresiva de hilos en tiempo real para evitar inanición de hilos guest.
- **AppImage todo-en-uno**: compila `eboot.bin`, genera íconos PlayStation, pre-traduce/empaqueta shaders para RADV PS5 (`TOTK_ZERO_LOCALS=0` + `mvprev`), soporta presets `60/120 Hz` y `FSR 3 FG`, incluye **MODS RomFS** y envía todo directo a la PS5 por FTP.

---

## Estructura exacta en la PS5

```text
/data/homebrew/PPSA99199/
  ├── eboot.bin                 # Binario FSELF firmado de TOTK PS5
  ├── sce_module/
  │   └── libc.prx
  └── sce_sys/
      ├── icon0.png
      ├── pic0.dds
      ├── pic1.dds
      └── param.json            # Subir al final para ShadowMountPlus

/data/totk-ps5/
  ├── totk.ini                  # Configuración PS5 (1440p, 100%, ○=A, íconos PS, es-419)
  ├── romfs-index.bin           # Índice RomFS
  ├── totk_xlate.id             # Identidad de caché de shaders RADV PS5
  ├── shader-prepared.bin       # Use-masks de 28,667 shaders
  ├── shader-programs.bin
  ├── shader-answers.bin
  ├── shader-cache/
  │   └── shader-cache.pack     # Shaders pre-traducidos para PS5 RADV
  ├── romfs-patches-playstation/       # Íconos PlayStation (○ confirmar)
  ├── romfs-patches-playstation-xbox/  # Íconos PlayStation (× confirmar)
  ├── exefs/                    # main, main.npdm, sdk, subsdk0
  ├── romfs/
  │   └── romfs.bin             # RomFS extraído (~15.86 GiB)
  ├── mods/                     # MODS RomFS (gestionables en Touchpad + Options)
  │   └── <mi_mod>/romfs/...
  ├── saves/                    # Separado automáticamente por usuario de PS5
  │   ├── user_<id_1>/
  │   └── user_<id_2>/
  └── logs/
      └── totk.log
```

---

## Compilación desde código fuente

### 1. Reconstruir runtime PS5 y binario `eboot.bin`
```bash
python3 scripts/probe_runtime_compile.py
python3 scripts/link_runtime_ps5.py
.venv/bin/python -m builder.cli --build-runtime-lib
.venv/bin/python -m builder.cli \
  --exefs /ruta/a/exefs \
  --romfs /ruta/a/romfs \
  --pretranslate-shaders \
  --out ./out \
  --jobs 10
```

### 2. Generar el AppImage todo-en-uno desde cero (0 datos de Nintendo)
```bash
# 1) Compilar traductor de shaders (con parche mvprev) + prep_mvprev + hactool
python3 ../totk-linux-native-recomp/tools/build_xlate.py --out build/xlate_mvprev
clang -O2 -I../totk-linux-native-recomp/runtime \
  scripts/prep_mvprev_main.c \
  ../totk-linux-native-recomp/runtime/{gfx_shader.c,cfg.c,platform/linux.c,platform/common.c,sha256.c} \
  -lpthread -ldl -lm -o build/xlate_mvprev/prep_mvprev
python3 ../totk-linux-native-recomp/tools/build_hactool.py --src build/hactool_src --out build/hactool

# 2) Compilar runtime PS5 + empaquetar AppImage autocontenido
python3 scripts/probe_runtime_compile.py
python3 scripts/link_runtime_ps5.py
.venv/bin/python -m builder.cli --build-runtime-lib
python3 scripts/make_appimage.py
# Salida: out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage
```

### 3. Uso del AppImage (solo necesitas tu copia legal del juego + `prod.keys`)
- **Interfaz gráfica (4 pestañas: Compilar & Shaders / MODS / Enviar a PS5 FTP / Layout PS5):**
  ```bash
  ./out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage
  ```
- **CLI desde archivo `.xci`/`.nsp` (+ update `.nsp` opcional) + `prod.keys`:**
  ```bash
  ./out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
    --game /ruta/a/totk_base.xci \
    --update /ruta/a/totk_v143.nsp \
    --keys /ruta/a/prod.keys \
    --pretranslate-shaders \
    --mod /ruta/a/mi_mod.zip \
    --deploy-ftp <IP_DE_TU_PS5> --ftp-port 2121
  ```
- **CLI desde `exefs/` + `romfs/` ya extraídos:**
  ```bash
  ./out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage \
    --exefs /ruta/a/exefs --romfs /ruta/a/romfs \
    --pretranslate-shaders \
    --deploy-ftp <IP_DE_TU_PS5> --ftp-port 2121
  ```
- **Ver layout PS5 desde terminal:**
  ```bash
  ./out/PS5TotkBuilder-v0.1.0-linux-x64.AppImage --show-layout
  ```

### 4. Tests
```bash
pytest -v tests/test_totk_ps5_project.py
```
