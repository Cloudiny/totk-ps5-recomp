/*
 * ps5/gfx_window_ps5.c
 *
 * PS5 VK_KHR_display window-system backend matching
 * totk-linux-native-recomp/runtime/gfx_wsys.h.
 *
 * Eliminates SDL3/X11/Wayland by creating a direct display-plane Vulkan
 * surface on PS5 HDMI output via Mesa RADV (libvulkan_radeon.ps5.a).
 */

#include "plat_ps5.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

extern PFN_vkVoidFunction vk_icdGetInstanceProcAddr(VkInstance instance, const char *pName);
extern void rt_log(const char *fmt, ...);
extern const char *cfg_get(const char *name) __attribute__((weak));

static int g_width = 1920;
static int g_height = 1080;
static int g_opened = 0;

static void want_display_size(int *out_w, int *out_h) {
    int w = 1920, h = 1080;
    const char *disp = cfg_get ? cfg_get("TOTK_PS5_DISPLAY") : NULL;
    if (!disp || !*disp) disp = cfg_get ? cfg_get("TOTK_OUTPUT_RES") : NULL;
    if (disp && *disp) {
        int pw = 0, ph = 0;
        if (sscanf(disp, "%dx%d", &pw, &ph) == 2 && pw >= 1280 && ph >= 720) {
            w = pw; h = ph;
        } else if (strstr(disp, "2160") || strstr(disp, "4k") || strstr(disp, "4K")) {
            w = 3840; h = 2160;
        } else if (strstr(disp, "1440")) {
            w = 2560; h = 1440;
        } else if (strstr(disp, "1080")) {
            w = 1920; h = 1080;
        }
    }
    *out_w = w;
    *out_h = h;
}

int wsys_open(void) {
    want_display_size(&g_width, &g_height);
    g_opened = 1;
    rt_log("ps5_wsys: wsys_open OK (%dx%d)", g_width, g_height);
    return 1;
}

VkSurfaceKHR wsys_surface(VkInstance inst) {
    if (!inst) {
        return VK_NULL_HANDLE;
    }

    PFN_vkEnumeratePhysicalDevices enum_gpus =
        (PFN_vkEnumeratePhysicalDevices)vk_icdGetInstanceProcAddr(
            inst, "vkEnumeratePhysicalDevices");
    PFN_vkGetPhysicalDeviceDisplayPropertiesKHR get_displays =
        (PFN_vkGetPhysicalDeviceDisplayPropertiesKHR)vk_icdGetInstanceProcAddr(
            inst, "vkGetPhysicalDeviceDisplayPropertiesKHR");
    PFN_vkGetDisplayModePropertiesKHR get_modes =
        (PFN_vkGetDisplayModePropertiesKHR)vk_icdGetInstanceProcAddr(
            inst, "vkGetDisplayModePropertiesKHR");
    PFN_vkCreateDisplayPlaneSurfaceKHR create_surf =
        (PFN_vkCreateDisplayPlaneSurfaceKHR)vk_icdGetInstanceProcAddr(
            inst, "vkCreateDisplayPlaneSurfaceKHR");

    if (!enum_gpus || !get_displays || !get_modes || !create_surf) {
        totk_ps5_klogf("[totk-ps5] wsys_surface: missing VK_KHR_display entry points\n");
        return VK_NULL_HANDLE;
    }

    uint32_t gpu_count = 1;
    VkPhysicalDevice gpu = VK_NULL_HANDLE;
    VkResult vr = enum_gpus(inst, &gpu_count, &gpu);
    if (vr < 0 || gpu_count == 0 || gpu == VK_NULL_HANDLE) {
        rt_log("ps5_wsys: vkEnumeratePhysicalDevices FAILED (%d, count=%u)", (int)vr, gpu_count);
        return VK_NULL_HANDLE;
    }

    uint32_t disp_count = 1;
    VkDisplayPropertiesKHR disp;
    vr = get_displays(gpu, &disp_count, &disp);
    if (vr < 0 || disp_count == 0) {
        rt_log("ps5_wsys: vkGetPhysicalDeviceDisplayPropertiesKHR FAILED (%d, count=%u)", (int)vr, disp_count);
        return VK_NULL_HANDLE;
    }

    uint32_t mode_count = 16;
    VkDisplayModePropertiesKHR modes[16];
    vr = get_modes(gpu, disp.display, &mode_count, modes);
    if (vr < 0 || mode_count == 0) {
        rt_log("ps5_wsys: vkGetDisplayModePropertiesKHR FAILED (%d, count=%u)", (int)vr, mode_count);
        return VK_NULL_HANDLE;
    }

    /* Pick display mode matching TOTK_PS5_DISPLAY / TOTK_OUTPUT_RES and TOTK_PS5_HZ (60 or 120 Hz) */
    int want_w = 1920, want_h = 1080;
    want_display_size(&want_w, &want_h);
    int want_120 = 0;
    const char *hz = cfg_get ? cfg_get("TOTK_PS5_HZ") : NULL;
    if (hz && atoi(hz) >= 100) want_120 = 1;
    const char *lim = cfg_get ? cfg_get("TOTK_FPS_LIMIT") : NULL;
    if (lim && atoi(lim) > 60) want_120 = 1;

    int pick = -1;
    for (uint32_t i = 0; i < mode_count; ++i) {
        const VkDisplayModeParametersKHR *p = &modes[i].parameters;
        rt_log("ps5_wsys: mode[%u] %ux%u @ %u mHz", i, p->visibleRegion.width, p->visibleRegion.height, p->refreshRate);
        if ((int)p->visibleRegion.width == want_w && (int)p->visibleRegion.height == want_h) {
            int is_fast = p->refreshRate >= 61000u;
            int has_fast = pick >= 0 && modes[pick].parameters.refreshRate >= 61000u;
            if (want_120) {
                if (pick < 0 || (is_fast && !has_fast)) pick = (int)i;
            } else {
                if (pick < 0 || (!is_fast && has_fast)) pick = (int)i;
            }
        }
    }
    if (pick < 0) pick = 0;

    const VkDisplayModeParametersKHR *mp = &modes[pick].parameters;
    g_width = (int)mp->visibleRegion.width;
    g_height = (int)mp->visibleRegion.height;

    VkDisplaySurfaceCreateInfoKHR ci;
    memset(&ci, 0, sizeof(ci));
    ci.sType = VK_STRUCTURE_TYPE_DISPLAY_SURFACE_CREATE_INFO_KHR;
    ci.displayMode = modes[pick].displayMode;
    ci.planeIndex = 0;
    ci.planeStackIndex = 0;
    ci.transform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR;
    ci.globalAlpha = 1.0f;
    ci.alphaMode = VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR;
    ci.imageExtent = mp->visibleRegion;

    VkSurfaceKHR surface = VK_NULL_HANDLE;
    vr = create_surf(inst, &ci, NULL, &surface);
    if (vr != VK_SUCCESS) {
        rt_log("ps5_wsys: vkCreateDisplayPlaneSurfaceKHR FAILED (%d)", (int)vr);
        totk_ps5_klogf("[totk-ps5] vkCreateDisplayPlaneSurfaceKHR failed: %d\n", (int)vr);
        return VK_NULL_HANDLE;
    }
    rt_log("ps5_wsys: VK_KHR_display surface created OK (%dx%d @ %u mHz)", g_width, g_height, mp->refreshRate);
    return surface;
}

void wsys_client_size(int *w, int *h) {
    if (w) *w = g_width;
    if (h) *h = g_height;
}

int wsys_minimized(void) {
    return g_opened ? 0 : 1;
}

void wsys_resize(int w, int h) {
    if (w > 0 && h > 0) {
        g_width = w;
        g_height = h;
    }
}

void wsys_probe_focus(int in) { (void)in; }
void wsys_probe_escape(void) {}
int wsys_probe_click(int where) {
    (void)where;
    return 0;
}

unsigned gfx_window_dpi(void) { return 96u; }
void gfx_window_apply_settings(void) {}
void gfx_window_request_close(void) {}
int gfx_window_monitor_size(int *w, int *h) {
    if (w) *w = g_width;
    if (h) *h = g_height;
    return 1;
}

int gfx_window_vk_extensions(const char **out, int max) {
    int n = 0;
    if (out && n < max) out[n++] = VK_KHR_SURFACE_EXTENSION_NAME;
    if (out && n < max) out[n++] = VK_KHR_DISPLAY_EXTENSION_NAME;
    return n;
}

int gfx_window_vk_presentable(VkInstance inst, VkPhysicalDevice pd, uint32_t family) {
    (void)inst;
    (void)pd;
    (void)family;
    return 1;
}
