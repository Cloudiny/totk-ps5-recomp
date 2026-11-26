# TOTK → PS5 Empirical Porting Inventory

- **Source scanned:** `<TOTK_UPSTREAM_SRC>` (`runtime, tools/xlate`)
- **Total scanned LOC:** `222,168`
- **Files with platform dependencies:** `46`

## Dependency Category Summary (file counts)

| Category | Files | PS5 Replacement Strategy |
|---|---:|---|
| `linux_futex` | 1 | FreeBSD/PS5 `_umtx_op` or `pthread_cond`/`sceKernelWaitEventFlag` |
| `linux_userfaultfd` | 1 | PS5 `sceKernelReserveVirtualRange` + `SIGSEGV` handler + `sceKernelMapDirectMemory` |
| `linux_epoll_eventfd` | 1 | PS5 `kqueue` / `poll` / `libps5platform.a` |
| `process_spawn` | 2 | **BLOCKER on PS5** — link `tools/xlate` in-process as static library |
| `dlopen_vulkan` | 1 | Static `libvulkan_radeon.ps5.a` via `vk_icdGetInstanceProcAddr` |
| `sdl3` | 14 | Native `VK_KHR_display` + `libScePad` + `libSceAudioOut` |
| `libopus` | 1 | Already precompiled in PS5 kit (`kit/obj/opus_*.o`!) |
| `libvpx_or_ffmpeg` | 1 | Replace `libvpx` with kit's precompiled `kit/lib/libavcodec.a` |
| `win32_only` | 17 | Excluded from PS5 build |
| `vulkan_ext` | 19 | Verify each required ext against `libvulkan_radeon.ps5.a` |
| `mmap_direct` | 1 | Map guest RAM via `sceKernelAllocateDirectMemory` + `sceKernelMapDirectMemory` |
| `pthreads` | 1 | Native `libkernel` + `libps5platform.a` `--wrap=pthread_*` |
| `signals` | 1 | PS5 `sigaction(SIGSEGV, ...)` + `ucontext_t` (`mc_rip`/`mc_rax`) |

## Vulkan Extensions Referenced in TOTK Runtime

- `VK_EXT_ATTACHMENT_FEEDBACK_LOOP_LAYOUT_EXTENSION_NAME`
- `VK_EXT_CALIBRATED_TIMESTAMPS_EXTENSION_NAME`
- `VK_EXT_CONDITIONAL_RENDERING_EXTENSION_NAME`
- `VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME`
- `VK_EXT_DEBUG_UTILS_EXTENSION_NAME`
- `VK_EXT_DEPTH_CLIP_CONTROL_EXTENSION_NAME`
- `VK_EXT_DESCRIPTOR_INDEXING_EXTENSION_NAME`
- `VK_EXT_DEVICE_ADDRESS_BINDING_REPORT_EXTENSION_NAME`
- `VK_EXT_DEVICE_FAULT_EXTENSION_NAME`
- `VK_EXT_EXTENDED_DYNAMIC_STATE_2_EXTENSION_NAME`
- `VK_EXT_EXTENDED_DYNAMIC_STATE_3_EXTENSION_NAME`
- `VK_EXT_EXTENDED_DYNAMIC_STATE_EXTENSION_NAME`
- `VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME`
- `VK_EXT_FRAGMENT_SHADER_INTERLOCK_EXTENSION_NAME`
- `VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME`
- `VK_EXT_HDR_METADATA_EXTENSION_NAME`
- `VK_EXT_MEMORY_BUDGET_EXTENSION_NAME`
- `VK_EXT_PCI_BUS_INFO_EXTENSION_NAME`
- `VK_EXT_PROVOKING_VERTEX_EXTENSION_NAME`
- `VK_EXT_ROBUSTNESS_2_EXTENSION_NAME`
- `VK_EXT_SUBGROUP_SIZE_CONTROL_EXTENSION_NAME`
- `VK_EXT_SWAPCHAIN_COLOR_SPACE_EXTENSION_NAME`
- `VK_EXT_TRANSFORM_FEEDBACK_EXTENSION_NAME`
- `VK_EXT_VERTEX_INPUT_DYNAMIC_STATE_EXTENSION_NAME`
- `VK_EXT_attachment_feedback_loop_dynamic_state`
- `VK_EXT_attachment_feedback_loop_layout`
- `VK_EXT_conditional_rendering`
- `VK_EXT_debug_utils`
- `VK_EXT_depth_clip_control`
- `VK_EXT_device_address_binding_report`
- `VK_EXT_device_fault`
- `VK_EXT_extended_dynamic_state3`
- `VK_EXT_external_memory_host`
- `VK_EXT_graphics_pipeline_library`
- `VK_EXT_hdr_metadata`
- `VK_EXT_index_type_uint8`
- `VK_EXT_memory_budget`
- `VK_EXT_pci_bus_info`
- `VK_EXT_vertex_attribute_divisor`
- `VK_EXT_vertex_input_dynamic_state`
- `VK_KHR_ACCELERATION_STRUCTURE_EXTENSION_NAME`
- `VK_KHR_CALIBRATED_TIMESTAMPS_EXTENSION_NAME`
- `VK_KHR_DEDICATED_ALLOCATION_EXTENSION_NAME`
- `VK_KHR_DYNAMIC_RENDERING_LOCAL_READ_EXTENSION_NAME`
- `VK_KHR_PIPELINE_LIBRARY_EXTENSION_NAME`
- `VK_KHR_PRESENT_ID_EXTENSION_NAME`
- `VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME`
- `VK_KHR_SHADER_FLOAT16_INT8_EXTENSION_NAME`
- `VK_KHR_SURFACE_EXTENSION_NAME`
- `VK_KHR_SWAPCHAIN_EXTENSION_NAME`
- `VK_KHR_SYNCHRONIZATION_2_EXTENSION_NAME`
- `VK_KHR_WIN32_SURFACE_EXTENSION_NAME`
- `VK_KHR_dynamic_rendering`
- `VK_KHR_index_type_uint8`
- `VK_KHR_maintenance5`
- `VK_KHR_pipeline_library`
- `VK_KHR_present_id`
- `VK_KHR_push_descriptor`
- `VK_KHR_swapchain`

## Key Files Requiring PS5 Porting Attention

| File | LOC | Tags |
|---|---:|---|
| `runtime/audio_mixer.c` | 1161 | `sdl3`(57) |
| `runtime/folder_pick_sdl.c` | 43 | `sdl3`(4) |
| `runtime/gfx_window_sdl.c` | 341 | `sdl3`(95), `win32_only`(2) |
| `runtime/input.c` | 1528 | `sdl3`(196) |
| `runtime/input.h` | 194 | `sdl3`(1) |
| `runtime/input_sdl.c` | 373 | `sdl3`(114) |
| `runtime/input_sdl.h` | 27 | `sdl3`(5) |
| `runtime/ov_input.c` | 519 | `sdl3`(1) |
| `runtime/ov_media.c` | 180 | `libopus`(7) |
| `runtime/ov_movie.c` | 1068 | `libvpx_or_ffmpeg`(16) |
| `runtime/ov_probe.c` | 1246 | `sdl3`(1) |
| `runtime/platform/linux.c` | 2049 | `dlopen_vulkan`(1), `linux_epoll_eventfd`(5), `linux_futex`(8), `linux_userfaultfd`(9), `mmap_direct`(14), `process_spawn`(5), `pthreads`(2), `sdl3`(3), `signals`(12), `vulkan_ext`(1) |
| `runtime/swkbd_sdl.c` | 22 | `sdl3`(1) |
| `runtime/third_party/imgui/imgui.cpp` | 17061 | `process_spawn`(2), `sdl3`(3), `win32_only`(1) |
| `runtime/third_party/imgui/imgui.h` | 3766 | `sdl3`(1) |
| `runtime/ui/menu_sdl.cpp` | 83 | `sdl3`(41) |
