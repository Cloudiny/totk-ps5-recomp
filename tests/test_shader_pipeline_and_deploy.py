"""TDD tests for MacNativeGames shader_list download, seed generation, and PS5 shader-only FTP deploy."""

from __future__ import annotations

import hashlib
import struct
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _make_fake_seed_programs(path: Path) -> tuple[str, str]:
    """Create a valid TOTKSPRG v1 file with 1 VS and 1 FS shader; return (vs_key, fs_key)."""
    buf = bytearray(b"TOTKSPRG" + struct.pack("<II", 1, 0))
    keys: list[str] = []
    for stage_id, seed_byte in ((0, 0x11), (4, 0x22)):
        control = bytearray(0x880)
        control[0:4] = b"\x34\x12\x76\x98"
        code = bytes([seed_byte]) * 64
        c1 = code[48:64]
        struct.pack_into("<II", control, 0x700, 48, len(code))
        h = hashlib.sha256(
            struct.pack("<I", stage_id)
            + bytes(control)
            + struct.pack("<Q", len(code))
            + code
            + struct.pack("<I", len(c1))
            + c1
        ).digest()
        key = hashlib.sha256(bytes(control) + code).hexdigest()
        keys.append(key)
        buf.extend(struct.pack("<III", stage_id, len(code), len(c1)) + h + bytes(control) + code + c1)
    path.write_bytes(bytes(buf))
    return keys[0], keys[1]


def test_extract_shader_list_history_recovers_dropped_v_rows(tmp_path: Path) -> None:
    from builder.shaders import MACNATIVEGAMES_LIST_PATH, extract_shader_list_history_from_repo

    repo = tmp_path / "mng"
    repo.mkdir()
    list_file = repo / MACNATIVEGAMES_LIST_PATH
    list_file.parent.mkdir(parents=True)

    env = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.com",
        "PATH": "/usr/bin:/bin",
    }

    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, env=env)
    old_v = "V\t" + ("a" * 64) + '\t{"attr":{"0":"uint"}}\n'
    kept_v = "V\t" + ("b" * 64) + '\t{"tex":{"0":"2darray"}}\n'
    list_file.write_text(old_v + kept_v, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "v1"], check=True, env=env)

    # Commit 2 prunes old_v and adds a warm S row
    warm_s = "S\t" + ("b" * 64) + "\t0\tt\n"
    list_file.write_text(kept_v + warm_s, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, env=env)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "v2"], check=True, env=env)
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(repo), "update-ref", "refs/remotes/origin/HEAD", head], check=True, env=env)

    combined = extract_shader_list_history_from_repo(repo)
    assert kept_v.strip() in combined.splitlines()
    assert old_v.strip() in combined.splitlines()
    assert warm_s.strip() in combined.splitlines()


def test_build_seed_answers_from_programs_includes_non_default_and_mvprev(tmp_path: Path) -> None:
    from builder.shaders import build_seed_answers_from_programs

    prog_bin = tmp_path / "seed-programs.bin"
    vs_key, fs_key = _make_fake_seed_programs(prog_bin)

    tsv = tmp_path / "shader_list.tsv"
    tsv.write_text(
        f'V\t{vs_key}\t{{"attr":{{"2":"uint"}},"tex":{{"0":"2d"}}}}\n'
        f'V\t{fs_key}\t{{"tex":{{"1":"2darray","3":"cube"}},"fout":{{"0":"sint"}}}}\n'
        f"S\t{vs_key}\t0\tt\n",
        encoding="utf-8",
    )

    out_ans = tmp_path / "seed-answers.bin"
    stats = build_seed_answers_from_programs(prog_bin, tsv, out_ans, add_mvprev=True)

    assert stats["programs"] == 2
    assert stats["matched_v_rows"] == 2
    assert stats["non_default_attr"] >= 1
    assert stats["non_default_tex"] >= 1
    assert stats["non_default_fout"] >= 1
    # 2 non-default + 2 default = 4 base+list, plus 2 mvprev VS copies (non-default VS + default VS) = 6
    assert stats["base_and_list"] == 4
    assert stats["mvprev_vs"] == 2
    assert stats["total_records"] == 6

    raw = out_ans.read_bytes()
    magic, ver, rsz = struct.unpack_from("<8sII", raw, 0)
    assert magic == b"TOTKSANS" and ver == 1 and rsz == 216
    assert len(raw) == 16 + 6 * 216

    # Check title priority=0 on the warm VS record and mvprev bit 0x80 on 2 records
    mv_flags = [raw[16 + i * 216 + 68 + 146] & 0x80 for i in range(6)]
    assert sum(1 for f in mv_flags if f) == 2
    prios = [raw[16 + i * 216 + 215] for i in range(6)]
    assert 0 in prios


def test_resolve_shader_list_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from builder.pipeline import KitPaths
    from builder.shaders import resolve_shader_list

    bundled_dir = tmp_path / "totk-src" / "tools" / "data"
    bundled_dir.mkdir(parents=True)
    bundled = bundled_dir / "shader_list.tsv"
    bundled.write_text("V\t" + ("0" * 64) + "\t{}\n", encoding="utf-8")

    cache_home = tmp_path / "xdg_cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache_home))
    cached = cache_home / "ps5-totk-builder" / "shader_list.tsv"

    explicit = tmp_path / "custom.tsv"
    explicit.write_text("V\t" + ("1" * 64) + "\t{}\n", encoding="utf-8")

    paths = KitPaths(
        project_root=tmp_path,
        kit_root=tmp_path,
        totk_src_root=tmp_path / "totk-src",
        ps5_src_root=tmp_path,
        compat_inc=tmp_path,
        vk_inc=tmp_path,
        vma_inc=tmp_path,
        assets_sce_sys=tmp_path,
        python_bin=Path(sys.executable),
    )

    # 1) Without cache, resolves bundled
    assert resolve_shader_list(paths) == bundled
    # 2) With cache present, cache takes precedence over bundled
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text("V\t" + ("2" * 64) + "\t{}\n", encoding="utf-8")
    assert resolve_shader_list(paths) == cached
    # 3) Explicit path takes precedence over cache
    assert resolve_shader_list(paths, explicit_list=explicit) == explicit


def test_deploy_shaders_to_ps5_uploads_only_shader_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import builder.deploy as deploy_mod

    data_dir = tmp_path / "data_totk_ps5"
    (data_dir / "shader-cache").mkdir(parents=True)
    (data_dir / "saves").mkdir(parents=True)
    (data_dir / "totk_xlate.id").write_text("7f4216ce\n", encoding="utf-8")
    (data_dir / "shader-prepared.bin").write_bytes(b"PREP" * 4)
    (data_dir / "shader-cache" / "shader-cache.pack").write_bytes(b"TKSPACK1" + b"\x00" * 16)
    (data_dir / "totk.ini").write_text("should_not_upload=1\n", encoding="utf-8")
    (data_dir / "saves" / "save.dat").write_bytes(b"SECRET_SAVE")

    uploaded: list[tuple[str, bool, bool]] = []
    mkdirs: list[str] = []

    class FakeDeployer:
        def __init__(self, host: str, port: int, log_fn=None) -> None:
            self.host = host
            self.port = port

        def mkdir_p(self, rdir: str) -> None:
            deploy_mod._assert_safe_remote(rdir)
            mkdirs.append(rdir)

        def chmod_777(self, rpath: str) -> None:
            pass

        def list_sizes(self, _rdir: str) -> dict[str, int]:
            return {}

        def upload_file(
            self,
            local_path: Path,
            remote_path: str,
            existing_sizes=None,
            force=False,
            delete_first=False,
            atomic=False,
        ) -> None:
            deploy_mod._assert_safe_remote(remote_path)
            assert local_path.is_file()
            uploaded.append((remote_path, force, atomic))

        def close(self) -> None:
            pass

    monkeypatch.setattr(deploy_mod, "PS5Deployer", FakeDeployer)
    sent = deploy_mod.deploy_shaders_to_ps5("192.0.2.10", 2121, data_dir, force=True)

    remote_paths = [p for p, _, _ in uploaded]
    assert remote_paths == [
        "/data/totk-ps5/totk_xlate.id",
        "/data/totk-ps5/shader-prepared.bin",
        "/data/totk-ps5/shader-cache/shader-cache.pack",
    ]
    assert sent == remote_paths
    assert all(f is True for _, f, _ in uploaded)
    assert all(a is True for _, _, a in uploaded)
    assert all("saves" not in p and "totk.ini" not in p and "eboot" not in p for p in remote_paths)


def test_gui_i18n_and_cli_shader_flags_exist() -> None:
    from builder import cli, gui

    for lang in ("es", "en"):
        for key in (
            "c_sh_t",
            "c_sh_s",
            "btn_sh_dl",
            "btn_sh_push",
            "btn_sh_both",
        ):
            assert key in gui.I18N[lang], f"Missing I18N[{lang!r}][{key!r}]"

    # Verify CLI accepts --download-shaders, --deploy-shaders-only, and --shader-list without error
    p = cli.build_arg_parser()
    args = p.parse_args(["--download-shaders", "--deploy-shaders-only", "--deploy-ftp", "192.0.2.10", "--shader-list", "/tmp/x.tsv"])
    assert args.download_shaders is True
    assert args.deploy_shaders_only is True
    assert args.deploy_ftp == "192.0.2.10"
    assert args.shader_list == Path("/tmp/x.tsv")
