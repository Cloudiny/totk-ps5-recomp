/*
 * TOTK-PS5 Phase 0 Smoke Executable (Title ID: PPSA99199)
 *
 * Verifies end-to-end PS5 cross-compilation, static Mesa RADV Vulkan
 * initialization via vk_icdGetInstanceProcAddr, PS5 direct/flexible memory
 * reporting, and live presence of every required TOTK Vulkan extension.
 */

#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <ps5platform/kernel.h>
#include <ps5platform/klog.h>
#include <ps5platform/memory.h>

extern int32_t sceSystemServiceHideSplashScreen(void);
extern int32_t sceKernelUsleep(uint32_t microseconds);

/* Direct static entry point exported by libvulkan_radeon.ps5.a */
extern PFN_vkVoidFunction vk_icdGetInstanceProcAddr(VkInstance instance, const char *pName);

static void klog_printf(const char *fmt, ...) {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    sceKernelDebugOutText(0, buf);
}

static bool has_ext_name(const VkExtensionProperties *exts, uint32_t count, const char *name) {
    for (uint32_t i = 0; i < count; ++i) {
        if (strcmp(exts[i].extensionName, name) == 0) {
            return true;
        }
    }
    return false;
}

int main(void) {
    ps5_klog_capture_stderr("[totk-ps5] ");
    sceSystemServiceHideSplashScreen();

    klog_printf("[totk-ps5] ==================================================\n");
    klog_printf("[totk-ps5] TOTK-PS5 Phase 0 Vulkan/RADV Smoke Test (PPSA99199)\n");
    klog_printf("[totk-ps5] ==================================================\n");

    struct ps5_kernel_sw_version sw;
    memset(&sw, 0, sizeof(sw));
    sw.size = sizeof(sw);
    if (sceKernelGetSystemSwVersion(&sw) == 0) {
        klog_printf("[totk-ps5] PS5 Firmware: %s (0x%08x)\n", sw.text, sw.version);
    }

    struct ps5_memory_stats mem;
    if (ps5_memory_query(&mem)) {
        klog_printf(
            "[totk-ps5] Memory: direct_total=%llu MiB, direct_free=%llu MiB, "
            "largest=%llu MiB, flexible_free=%llu MiB, ranges=%u\n",
            (unsigned long long)(mem.total_bytes >> 20),
            (unsigned long long)(mem.free_bytes >> 20),
            (unsigned long long)(mem.largest_bytes >> 20),
            (unsigned long long)(mem.flexible_bytes >> 20),
            mem.free_ranges
        );
    } else {
        klog_printf("[totk-ps5] WARN: ps5_memory_query() returned false\n");
    }

    PFN_vkEnumerateInstanceExtensionProperties pfn_enum_inst_ext =
        (PFN_vkEnumerateInstanceExtensionProperties)vk_icdGetInstanceProcAddr(
            VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    PFN_vkCreateInstance pfn_create_inst =
        (PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance");

    if (!pfn_enum_inst_ext || !pfn_create_inst) {
        klog_printf("[totk-ps5] FAIL: vk_icdGetInstanceProcAddr returned NULL\n");
        sceKernelUsleep(2000000);
        return 1;
    }

    uint32_t inst_ext_count = 0;
    pfn_enum_inst_ext(NULL, &inst_ext_count, NULL);
    VkExtensionProperties *inst_exts = NULL;
    if (inst_ext_count > 0) {
        inst_exts = (VkExtensionProperties *)calloc(inst_ext_count, sizeof(*inst_exts));
        if (inst_exts) {
            pfn_enum_inst_ext(NULL, &inst_ext_count, inst_exts);
        }
    }
    klog_printf("[totk-ps5] Vulkan instance extensions advertised: %u\n", inst_ext_count);

    const char *want_inst_exts[4];
    uint32_t enabled_inst_ext_count = 0;
    if (inst_exts && has_ext_name(inst_exts, inst_ext_count, VK_KHR_SURFACE_EXTENSION_NAME)) {
        want_inst_exts[enabled_inst_ext_count++] = VK_KHR_SURFACE_EXTENSION_NAME;
    }
    if (inst_exts && has_ext_name(inst_exts, inst_ext_count, VK_KHR_DISPLAY_EXTENSION_NAME)) {
        want_inst_exts[enabled_inst_ext_count++] = VK_KHR_DISPLAY_EXTENSION_NAME;
    }

    VkApplicationInfo app_info;
    memset(&app_info, 0, sizeof(app_info));
    app_info.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    app_info.pApplicationName = "TOTK-PS5-Smoke";
    app_info.applicationVersion = VK_MAKE_VERSION(0, 1, 0);
    app_info.pEngineName = "totk-ps5-recomp";
    app_info.engineVersion = VK_MAKE_VERSION(0, 1, 0);
    app_info.apiVersion = VK_API_VERSION_1_3;

    VkInstanceCreateInfo inst_ci;
    memset(&inst_ci, 0, sizeof(inst_ci));
    inst_ci.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    inst_ci.pApplicationInfo = &app_info;
    inst_ci.enabledExtensionCount = enabled_inst_ext_count;
    inst_ci.ppEnabledExtensionNames = enabled_inst_ext_count ? want_inst_exts : NULL;

    VkInstance instance = VK_NULL_HANDLE;
    VkResult vr = pfn_create_inst(&inst_ci, NULL, &instance);
    if (vr != VK_SUCCESS || instance == VK_NULL_HANDLE) {
        klog_printf("[totk-ps5] FAIL: vkCreateInstance failed (VkResult=%d)\n", (int)vr);
        free(inst_exts);
        sceKernelUsleep(2000000);
        return 2;
    }

    PFN_vkEnumeratePhysicalDevices pfn_enum_gpus =
        (PFN_vkEnumeratePhysicalDevices)vk_icdGetInstanceProcAddr(
            instance, "vkEnumeratePhysicalDevices");
    PFN_vkGetPhysicalDeviceProperties pfn_gpu_props =
        (PFN_vkGetPhysicalDeviceProperties)vk_icdGetInstanceProcAddr(
            instance, "vkGetPhysicalDeviceProperties");
    PFN_vkEnumerateDeviceExtensionProperties pfn_enum_dev_ext =
        (PFN_vkEnumerateDeviceExtensionProperties)vk_icdGetInstanceProcAddr(
            instance, "vkEnumerateDeviceExtensionProperties");
    PFN_vkGetPhysicalDeviceDisplayPropertiesKHR pfn_get_displays =
        (PFN_vkGetPhysicalDeviceDisplayPropertiesKHR)vk_icdGetInstanceProcAddr(
            instance, "vkGetPhysicalDeviceDisplayPropertiesKHR");
    PFN_vkDestroyInstance pfn_destroy_inst =
        (PFN_vkDestroyInstance)vk_icdGetInstanceProcAddr(instance, "vkDestroyInstance");

    uint32_t gpu_count = 0;
    vr = pfn_enum_gpus(instance, &gpu_count, NULL);
    klog_printf("[totk-ps5] vkEnumeratePhysicalDevices: vr=%d count=%u\n", (int)vr, gpu_count);

    int missing_required = 0;
    if (vr == VK_SUCCESS && gpu_count > 0) {
        VkPhysicalDevice gpus[4];
        if (gpu_count > 4) gpu_count = 4;
        pfn_enum_gpus(instance, &gpu_count, gpus);

        VkPhysicalDeviceProperties props;
        pfn_gpu_props(gpus[0], &props);
        klog_printf(
            "[totk-ps5] GPU[0]: %s (vendor=0x%04x device=0x%04x api=%u.%u.%u)\n",
            props.deviceName,
            props.vendorID,
            props.deviceID,
            VK_VERSION_MAJOR(props.apiVersion),
            VK_VERSION_MINOR(props.apiVersion),
            VK_VERSION_PATCH(props.apiVersion)
        );

        uint32_t dev_ext_count = 0;
        pfn_enum_dev_ext(gpus[0], NULL, &dev_ext_count, NULL);
        VkExtensionProperties *dev_exts =
            (VkExtensionProperties *)calloc(dev_ext_count, sizeof(*dev_exts));
        if (dev_exts) {
            pfn_enum_dev_ext(gpus[0], NULL, &dev_ext_count, dev_exts);
            klog_printf("[totk-ps5] GPU[0] device extensions: %u\n", dev_ext_count);

            static const char *const kRequired[] = {
                VK_KHR_SWAPCHAIN_EXTENSION_NAME,
                VK_KHR_PUSH_DESCRIPTOR_EXTENSION_NAME,
                VK_EXT_DEPTH_CLIP_CONTROL_EXTENSION_NAME,
                VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME,
            };
            static const char *const kBonus[] = {
                VK_KHR_DYNAMIC_RENDERING_EXTENSION_NAME,
                VK_EXT_GRAPHICS_PIPELINE_LIBRARY_EXTENSION_NAME,
                VK_EXT_EXTENDED_DYNAMIC_STATE_3_EXTENSION_NAME,
                VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME,
            };

            for (size_t i = 0; i < sizeof(kRequired) / sizeof(kRequired[0]); ++i) {
                bool ok = has_ext_name(dev_exts, dev_ext_count, kRequired[i]);
                klog_printf("[totk-ps5]   REQUIRED %-44s : %s\n", kRequired[i], ok ? "OK" : "MISSING");
                if (!ok) ++missing_required;
            }
            for (size_t i = 0; i < sizeof(kBonus) / sizeof(kBonus[0]); ++i) {
                bool ok = has_ext_name(dev_exts, dev_ext_count, kBonus[i]);
                klog_printf("[totk-ps5]   OPTIONAL %-44s : %s\n", kBonus[i], ok ? "OK" : "missing");
            }
            free(dev_exts);
        }

        if (pfn_get_displays) {
            uint32_t disp_count = 0;
            VkResult dr = pfn_get_displays(gpus[0], &disp_count, NULL);
            klog_printf("[totk-ps5] VK_KHR_display count=%u (vr=%d)\n", disp_count, (int)dr);
        }
    } else {
        missing_required = 99;
    }

    if (pfn_destroy_inst) {
        pfn_destroy_inst(instance, NULL);
    }
    free(inst_exts);

    if (missing_required == 0) {
        klog_printf("[totk-ps5] PHASE 0 SMOKE PASS: PS5 RADV Vulkan ready for TOTK!\n");
    } else {
        klog_printf("[totk-ps5] PHASE 0 SMOKE FAIL: missing_required=%d\n", missing_required);
    }

    sceKernelUsleep(3000000);
    return missing_required == 0 ? 0 : 3;
}
