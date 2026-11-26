"""Automated verification tests for totk-ps5-recomp (full TOTK v1.4.3 PS5 build + AppImage)."""

from __future__ import annotations

import os

import json
import struct
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KIT_ROOT = PROJECT_ROOT / "third_party" / "ps5-kit"
OUT_TITLE = PROJECT_ROOT / "out" / "PPSA99199"
OUT_DATA = PROJECT_ROOT / "out" / "data_totk_ps5"
APPIMAGE = PROJECT_ROOT / "out" / "PS5TotkBuilder-v0.1.0-linux-x64.AppImage"
TOTK_SOURCE = Path(os.environ.get("TOTK_UPSTREAM_SRC", str(Path(__file__).resolve().parent.parent.parent / "totk-linux-native-recomp")))


def test_ps5_kit_extracted_and_complete() -> None:
    required = [
        KIT_ROOT / "kit" / "kit.json",
        KIT_ROOT / "kit" / "lib" / "libvulkan_radeon.ps5.a",
        KIT_ROOT / "kit" / "sdk" / "target" / "lib" / "libps5platform.a",
        KIT_ROOT / "kit" / "obj" / "app_crt.o",
        KIT_ROOT / "tools" / "bin" / "clang",
        KIT_ROOT / "tools" / "bin" / "ld.lld",
        KIT_ROOT / "tools" / "bin" / "ps5-native-tool",
    ]
    for p in required:
        assert p.is_file(), f"Missing extracted PS5 kit file: {p}"


def test_radv_contains_required_totk_vulkan_extensions() -> None:
    blob = (KIT_ROOT / "kit" / "lib" / "libvulkan_radeon.ps5.a").read_bytes()
    for ext in (
        b"VK_KHR_swapchain",
        b"VK_KHR_push_descriptor",
        b"VK_EXT_depth_clip_control",
        b"VK_EXT_external_memory_host",
        b"VK_KHR_display",
        b"VK_KHR_dynamic_rendering",
    ):
        assert ext in blob, f"Required extension missing from libvulkan_radeon.ps5.a: {ext!r}"


def test_audit_script_reports_totk_platform_layer(tmp_path: Path) -> None:
    assert TOTK_SOURCE.is_dir(), "Reference totk-linux-native-recomp repo missing"
    out_json = tmp_path / "inv.json"
    out_md = tmp_path / "inv.md"
    res = subprocess.run(
        [
            "python3",
            str(PROJECT_ROOT / "scripts" / "audit_totk_port.py"),
            "--totk-root",
            str(TOTK_SOURCE),
            "--json-out",
            str(out_json),
            "--md-out",
            str(out_md),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "[ok] audited" in res.stdout
    data = json.loads(out_json.read_text())
    paths = {f["path"] for f in data["files"]}
    assert "runtime/platform/linux.c" in paths
    assert "runtime/gfx_window_sdl.c" in paths


def test_full_totk_v143_ps5_eboot_signed_and_valid() -> None:
    eboot = OUT_TITLE / "eboot.bin"
    assert eboot.is_file(), "Missing out/PPSA99199/eboot.bin"
    assert eboot.stat().st_size > 200 * 1024 * 1024, "Expected full lifted TOTK eboot.bin (>200 MiB)"

    magic = struct.unpack("<I", eboot.read_bytes()[:4])[0]
    assert magic == 0x1D3D154F, f"Unexpected FSELF magic: {magic:#x}"

    native_tool = str(KIT_ROOT / "tools" / "bin" / "ps5-native-tool")
    res = subprocess.run(
        [native_tool, "self", "--inspect", "--file", str(eboot)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "container: signed, plaintext" in res.stdout
    assert "integrity: valid" in res.stdout


def test_totk_custom_ps5_branding_and_metadata() -> None:
    sce_sys = OUT_TITLE / "sce_sys"
    assert (OUT_TITLE / "sce_module" / "libc.prx").is_file()
    assert (sce_sys / "icon0.png").is_file()
    assert (sce_sys / "pic0.dds").stat().st_size == 8_294_548
    assert (sce_sys / "pic1.dds").stat().st_size == 8_294_548

    # Verify DX10 BC7 DDS header magic ("DDS " + "DX10" at offset 84 + DXGI_FORMAT_BC7_UNORM=98 at offset 128)
    hdr = (sce_sys / "pic0.dds").read_bytes()[:148]
    assert hdr[:4] == b"DDS "
    assert hdr[84:88] == b"DX10"
    assert struct.unpack("<I", hdr[128:132])[0] == 98

    param = json.loads((sce_sys / "param.json").read_text(encoding="utf-8"))
    assert param["titleId"] == "PPSA99199"
    assert param["titleId"] != "PPSA99198"
    assert param["localizedParameters"]["en-US"]["titleName"] == "The Legend of Zelda: Tears of the Kingdom"
    assert param["localizedParameters"]["es-MX"]["titleName"] == "The Legend of Zelda: Tears of the Kingdom"


def test_staged_ps5_data_and_shader_caches() -> None:
    assert (OUT_DATA / "romfs-index.bin").is_file()
    assert (OUT_DATA / "romfs-index.bin").read_bytes()[:8] == b"TOTKRFS1"
    assert (OUT_DATA / "totk.ini").is_file()
    assert (OUT_DATA / "shader-programs.bin").is_file()
    assert (OUT_DATA / "shader-answers.bin").is_file()


def test_appimage_builder_self_check() -> None:
    assert APPIMAGE.is_file(), f"Missing AppImage at {APPIMAGE}"
    assert APPIMAGE.stat().st_size > 100 * 1024 * 1024
    res = subprocess.run([str(APPIMAGE), "--check"], capture_output=True, text=True, check=True)
    assert "PS5 TOTK Builder kit self-check PASSED" in res.stdout


def test_ps5_astc_lds_padding_and_spirv_valid(tmp_path: Path) -> None:
    import hashlib
    import re

    comp = PROJECT_ROOT / "ps5" / "shaders" / "astc_decode.comp"
    hdr = PROJECT_ROOT / "ps5" / "ps5_astc_decode_spv.h"
    assert comp.is_file(), "Missing ps5/shaders/astc_decode.comp"
    assert hdr.is_file(), "Missing ps5/ps5_astc_decode_spv.h"

    src = comp.read_text(encoding="utf-8")
    assert "shared uint s_w[MAXB][65];" in src
    assert "shared int s_cv[MAXB][19];" in src
    assert "int sx_wx = sx * (H.wx - 1), sy_wy = sy * (H.wy - 1);" in src
    assert "int vx = (sx_wx * x + 32) >> 6, vy = (sy_wy * y + 32) >> 6;" in src

    sha = hashlib.sha256(comp.read_bytes()).hexdigest()
    hdr_txt = hdr.read_text(encoding="utf-8")
    assert f"source sha256 {sha}" in hdr_txt

    words = [int(m, 16) for m in re.findall(r"0x[0-9a-fA-F]{8}", hdr_txt)]
    assert len(words) > 5000 and words[0] == 0x07230203
    spv = tmp_path / "astc.spv"
    spv.write_bytes(struct.pack(f"<{len(words)}I", *words))
    subprocess.run(["spirv-val", "--target-env", "vulkan1.1", str(spv)], check=True)


def test_ps5_prepare_threads_75pct_cap(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT))
    from builder.pipeline import prepare_thread_count

    cases = [(1, 1), (2, 2), (4, 3), (8, 6), (12, 9), (16, 12), (24, 18), (128, 64)]
    for cpus, expected in cases:
        assert prepare_thread_count(cpus) == expected
    assert prepare_thread_count(12, asked=4) == 4
    assert prepare_thread_count(12, asked=99) == 64

    harness = tmp_path / "test_pt.c"
    exe = tmp_path / "test_pt"
    harness.write_text(
        '#include <assert.h>\n'
        '#include "prepare_threads.h"\n'
        'int main(void) {\n'
        '    assert(ps5_prepare_threads(1, 0) == 1);\n'
        '    assert(ps5_prepare_threads(4, 0) == 3);\n'
        '    assert(ps5_prepare_threads(8, 0) == 6);\n'
        '    assert(ps5_prepare_threads(12, 0) == 9);\n'
        '    assert(ps5_prepare_threads(16, 0) == 12);\n'
        '    assert(ps5_prepare_threads(24, 0) == 18);\n'
        '    assert(ps5_prepare_threads(128, 0) == 64);\n'
        '    assert(ps5_prepare_threads(8, 5) == 5);\n'
        '    return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["cc", "-Wall", "-Wextra", "-Werror", f"-I{PROJECT_ROOT / 'ps5'}", str(harness), "-o", str(exe)],
        check=True,
    )
    subprocess.run([str(exe)], check=True)


def test_ps5_radv_mesh_nwg_guard_rewrites_and_validates(tmp_path: Path) -> None:
    harness = tmp_path / "test_nwg.c"
    exe = tmp_path / "test_nwg"
    out_spv = tmp_path / "guarded.spv"
    harness.write_text(
        '#include <assert.h>\n'
        '#include <stdio.h>\n'
        '#include "spirv_radv_mesh_nwg.h"\n'
        'static const uint32_t sample_mesh[] = {\n'
        '    0x07230203u, 0x00010500u, 0x00000000u, 20u, 0u,\n'
        '    (2u<<16)|17u, 1u,\n'
        '    (2u<<16)|17u, 5283u,\n'
        '    (5u<<16)|10u, 0x5f565053u, 0x5f545845u, 0x6873656du, 0x64616873u,\n'
        '    (3u<<16)|14u, 0u, 1u,\n'
        '    (6u<<16)|15u, 5365u, 1u, 0x6e69616du, 0u, 10u,\n'
        '    (4u<<16)|16u, 1u, 17u, 1u,\n'
        '    (4u<<16)|16u, 1u, 18u, 1u,\n'
        '    (4u<<16)|16u, 1u, 19u, 1u,\n'
        '    (4u<<16)|16u, 1u, 26u, 3u,\n'
        '    (4u<<16)|16u, 1u, 5270u, 1u,\n'
        '    (4u<<16)|71u, 10u, 11u, 24u,\n'
        '    (2u<<16)|19u, 2u,\n'
        '    (3u<<16)|33u, 3u, 2u,\n'
        '    (4u<<16)|21u, 4u, 32u, 0u,\n'
        '    (4u<<16)|23u, 5u, 4u, 3u,\n'
        '    (4u<<16)|32u, 6u, 1u, 5u,\n'
        '    (4u<<16)|59u, 6u, 10u, 1u,\n'
        '    (4u<<16)|43u, 4u, 11u, 3u,\n'
        '    (4u<<16)|43u, 4u, 12u, 1u,\n'
        '    (5u<<16)|54u, 2u, 1u, 0u, 3u,\n'
        '    (2u<<16)|248u, 13u,\n'
        '    (3u<<16)|5295u, 11u, 12u,\n'
        '    (1u<<16)|253u,\n'
        '    (1u<<16)|56u\n'
        '};\n'
        'int main(int argc, char **argv) {\n'
        '    (void)argc; (void)argv;\n'
        '    uint64_t out_n = 0;\n'
        '    uint32_t *res = spirv_radv_keep_num_workgroups(sample_mesh, sizeof(sample_mesh)/4, &out_n);\n'
        '    assert(res != NULL);\n'
        '    assert(out_n == sizeof(sample_mesh)/4 + 26);\n'
        '    uint32_t bad[5] = {0x07230203u, 0x00010500u, 0u, 4u, 0u};\n'
        '    assert(spirv_radv_keep_num_workgroups(bad, 5, &out_n) == NULL);\n'
        '    free(res);\n'
        '    return 0;\n'
        '}\n',
        encoding="utf-8",
    )
    subprocess.run(
        ["cc", "-Wall", "-Wextra", "-Werror", f"-I{PROJECT_ROOT / 'ps5'}", str(harness), "-o", str(exe)],
        check=True,
    )
    subprocess.run([str(exe), str(out_spv)], check=True)
