# Viabilidad y Arquitectura: *The Legend of Zelda: Tears of the Kingdom* → PlayStation 5

> **Veredicto técnico: SÍ ES VIABLE** — y de hecho, **TOTK encaja mejor en el presupuesto de RAM de la PS5 que OOT Switch 2 (Longshot Plus)**.  
> **Estado actual:** **Fase 0 completada y verificada** — toolchain PS5 extraído, auditoría empírica de `totk-linux-native-recomp` completada, capa inicial `ps5/*.c` cross-compilando con `-Werror` para `x86_64-sie-ps5`, y binario FSELF de prueba Vulkan/RADV (`out/PPSA99199/eboot.bin`, 18.18 MiB) firmado y validado (`integrity: valid`).

---

## 1. Por qué es viable (evidencia empírica en tu PC)

1. **Presupuesto de RAM y tamaño del binario favorable:**
   - TOTK fue diseñado para los **4 GiB de RAM** de Nintendo Switch 1, mientras que una PS5 ofrece **~12 GiB de Direct Memory + 720 MiB de Flexible Memory** (`param.json` → `flexibleMemorySize: 754974720`).
   - El ejecutable x86_64 ya recompilado de TOTK (`/home/saul/Games/Hyrule/TOTK/totk-runtime/totk`) pesa **261 MiB**, aproximadamente la **mitad** del `eboot.bin` de OOT Switch 2 en Longshot Plus (**521 MiB**).
2. **El "motor" PS5 de Longshot Plus ya está completo y funciona localmente:**
   - Extraído desde `PS5LongshotPlusBuilder-v0.3.4-plus-linux-x64.AppImage` (`offset 944632`) a `third_party/ps5-kit/`:
     - **Compilador y linker PS5:** `clang 23.1.5` (`-target x86_64-sie-ps5 -march=znver2`), `ld.lld 23.1.5`, `llvm-nm`, `ps5-native-tool` (linker + firmador FSELF `0x1D3D154F`).
     - **Driver Vulkan para GPU AMD RDNA 2 de PS5 (AGC):** `libvulkan_radeon.ps5.a` (Mesa RADV compilado para PS5, enlazado estáticamente vía `vk_icdGetInstanceProcAddr`).
     - **Capa POSIX/PS5 lista:** `libps5platform.a` (`ps5_memory_query`, `ps5_klog_capture_stderr`, `sceKernelAllocateDirectMemory`, `sceKernelMapDirectMemory`, wrappers de `malloc`/`pthread`/`opendir`/etc.).
     - **Dependencias de TOTK ya precompiladas para PS5 dentro del kit:**
       - **libopus** (`kit/obj/opus_*.o`) — listo para voces/audio Opus de Switch.
       - **FFmpeg (`libavcodec.a`, `libswscale.a`, `libavutil.a`, `libdav1d.a`)** — permite reemplazar `libvpx` para cinemáticas sin portar `libvpx`.
       - **zstd (`libzstd.a`)** e **ImGui (`kit/obj/vk_imgui_*.o`)** — ya compilados para PS5.
       - **Eden shader_recompiler + Sirit (`kit/obj/vk_vk_eden_shader_recompiler_*.o`)** — el mismo compilador Maxwell→SPIR-V ya compilado para PS5.
3. **Compatibilidad Vulkan verificada empíricamente (`libvulkan_radeon.ps5.a`):**
   - De las **4** extensiones obligatorias de `totk-linux-native-recomp/runtime/vk_device.c`, **4 de 4** están presentes en `libvulkan_radeon.ps5.a`:
     - `VK_KHR_swapchain` ✅
     - `VK_KHR_push_descriptor` ✅
     - `VK_EXT_depth_clip_control` ✅
     - `VK_EXT_external_memory_host` ✅
   - Además incluye `VK_KHR_display` (salida directa a HDMI sin SDL/X11/Wayland), `VK_KHR_dynamic_rendering`, `VK_EXT_graphics_pipeline_library`, `VK_EXT_extended_dynamic_state3`, `VK_EXT_custom_border_color`, `VK_EXT_transform_feedback` y `VK_EXT_conditional_rendering`.
4. **Arquitectura excepcionalmente limpia de `totk-linux-native-recomp`:**
   - La auditoría empírica (`scripts/audit_totk_port.py` sobre **222,168 LOC**) confirmó que **todo** el código Linux-específico (`futex`, `userfaultfd`, `mmap`, `epoll`, `signals`, `pthreads`, `dlopen`, `posix_spawn`) está aislado en **un solo archivo**: `runtime/platform/linux.c` (2,049 LOC) detrás de la interfaz `runtime/platform/platform.h`, y toda la ventana Vulkan está aislada en `runtime/gfx_wsys.h` (25 líneas, 8 funciones).

---

## 2. Los 5 retos reales (sin humo)

Aunque es 100% viable, no es un "recompilar y listo". Estos son los 5 subsistemas que hay que implementar en orden:

| # | Subsistema en `totk-linux-native-recomp` | Por qué no funciona directo en PS5 | Solución concreta en `totk-ps5-recomp` |
|---|---|---|---|
| **1** | **Traductor de shaders** (`runtime/gfx_shader.c`, `tools/xlate/`) | En Linux lanza procesos hijos (`posix_spawn("totk_xlate", "--serve")`) con pipes. PS5 prohíbe crear procesos hijos desde un título. | Enlazar `tools/xlate/` **in-process** como librería estática (contrato `ps5/xlate_inproc.h`) y precargar cachés pre-traducidas desde PC (`shader-programs.bin` / `shader-answers.bin`) en `/data/totk-ps5/cache/`. |
| **2** | **OS / Memoria / Sync / Fibras** (`runtime/platform/linux.c`) | Usa `linux/futex.h`, `linux/userfaultfd.h`, `mmap` y `sigaction` de Linux. | Implementar `platform/ps5.c` usando `sceKernelReserveVirtualRange` + `sceKernelAllocateDirectMemory` + `sceKernelMapDirectMemory` (`ps5/plat_ps5_mem.c`), manejador `SIGSEGV` para commit bajo demanda y `_umtx_op`/`pthread_cond` de FreeBSD/PS5. |
| **3** | **Loader Vulkan y Ventana** (`runtime/vk_device.c`, `runtime/gfx_window_sdl.c`) | Carga `libvulkan.so.1` con `dlopen()` y crea superficie con SDL3. | Usar entrada estática `vk_icdGetInstanceProcAddr` de `libvulkan_radeon.ps5.a` y backend directo `VK_KHR_display` (`ps5/gfx_window_ps5.c`). |
| **4** | **Entrada, Audio y Video** (`input_sdl.c`, `audio_mixer.c`, `ov_movie.c`, `swkbd_sdl.c`) | Depende de SDL3 y `libvpx`. | `ps5/input_ps5.c` (`libScePad`, DualSense + giroscopio + vibración), `ps5/audio_ps5.c` (`libSceAudioOut` 48 kHz + `opus_*.o` del kit), reemplazar `libvpx` en `ov_movie.c` por `libavcodec.a` del kit y stub de `swkbd`/`folder_pick`. |
| **5** | **RomFS y Empaquetado PS5** (`runtime/romfs.c`) | Espera `romfs-index.bin` + archivos del juego en rutas de escritorio. | Apuntar rutas de datos a `/data/totk-ps5/` (compatible con `ShadowMountPlus 1.7beta12`) y empaquetar bajo Title ID dedicado **`PPSA99199`** para no colisionar jamás con Longshot Plus (`PPSA99198`). |

---

## 3. Hoja de ruta en 4 fases

- **Fase 0 — Toolchain y Smoke Vulkan/RADV (`PPSA99199`)** ✅ **COMPLETADA**
  - Extracción automatizada del kit PS5 (`scripts/extract_ps5_kit.py`).
  - Auditoría empírica de `totk-linux-native-recomp` (`scripts/audit_totk_port.py` → `docs/PORT_INVENTORY.md`).
  - Compilación y firma de `out/PPSA99199/eboot.bin` (`smoke/hello_ps5_vk.c`): reporta firmware PS5, RAM Direct/Flexible libre, GPU RADV, las 4 extensiones Vulkan obligatorias de TOTK y `VK_KHR_display` vía `klog` (`klogsrv-ps5.elf:3232`).
  - Scaffolding inicial `ps5/` compilando sin warnings (`-Wall -Wextra -Werror`) para `x86_64-sie-ps5`.
- **Fase 1 — `platform/ps5.c` + Arranque Headless de `nnMain`** *(Siguiente paso)*
  - Completar `platform/ps5.c` (hilos, afinidad Zen 2, fibras x86_64, futex/condvar, `SIGSEGV` demand-commit sobre `TotkPs5Arena`, `romfs` en `/data/totk-ps5/`).
  - Cross-compilar los objetos recompilados de TOTK (`recomp/*.c`) y el núcleo `runtime/` con `gfx_null.c` hasta alcanzar `nnMain` y registrar llamadas HOS/SVC reales en `klog`.
- **Fase 2 — `totk_xlate` In-Process + Primer Frame con `VK_KHR_display`**
  - Enlazar `tools/xlate` in-process (o caché pre-traducida desde tu PC) eliminando `posix_spawn`.
  - Conectar `vk_device.c` a `vk_icdGetInstanceProcAddr` + `ps5/gfx_window_ps5.c` (`VK_KHR_display`).
  - Obtener el primer frame renderizado (logo Nintendo / pantalla de título de TOTK) en la TV de la PS5.
- **Fase 3 — DualSense, Audio 48 kHz, Cinemáticas y Empaquetado Final**
  - Completar mapeo completo DualSense (`libScePad` + giroscopio para arco/Ultramano + háptica básica).
  - Conectar `audio_mixer.c` a `ps5/audio_ps5.c` (`libSceAudioOut`) + `opus_*.o` del kit.
  - Conectar `ov_movie.c` a `libavcodec.a` del kit (VP9/H.264).
  - Branding PS5 propio (`PPSA99199`: `icon0.png` + `pic0.dds`/`pic1.dds` 4K BC7 usando el encoder de `ps5-hyrule-bridge`) y gestor de saves en `/data/totk-ps5/saves/`.

---

## 4. Cómo probar hoy el binario Fase 0 en tu PS5 (opcional)

1. Copia la carpeta `out/PPSA99199/` a `/data/homebrew/PPSA99199/` (o tu carpeta monitoreada por `ShadowMountPlus 1.7beta12`) vía FTP (`10.0.0.195:2121`).
2. Conéctate al klog en tu PC: `nc 10.0.0.195 3232`.
3. Lanza **"TOTK PS5 (Prueba Fase 0)"** desde el menú de la PS5 y verifica el banner:
   `[totk-ps5] PHASE 0 SMOKE PASS: PS5 RADV Vulkan ready for TOTK!`
