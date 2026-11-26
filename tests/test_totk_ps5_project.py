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
