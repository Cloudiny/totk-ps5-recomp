#!/usr/bin/env python3
"""Deploy TOTK PS5 (PPSA99199 + /data/totk-ps5/) to a jailbroken PS5 via ftpsrv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from builder.deploy import deploy_to_ps5  # noqa: E402

DEFAULT_EXEFS = Path("/home/saul/Games/Hyrule/TOTK/ROM/exefs")
DEFAULT_ROMFS_BIN = Path("/home/saul/Games/Hyrule/TOTK/ROM/romfs/romfs.bin")


def main() -> int:
    p = argparse.ArgumentParser(description="Deploy TOTK PS5 (PPSA99199 + /data/totk-ps5/) via FTP")
    p.add_argument("--host", default="10.0.0.195")
    p.add_argument("--port", type=int, default=2121)
    p.add_argument("--out", type=Path, default=PROJECT_ROOT / "out")
    p.add_argument("--skip-romfs", action="store_true")
    p.add_argument("--skip-shaders", action="store_true")
    p.add_argument("--skip-ini", action="store_true")
    p.add_argument("--exefs", type=Path, default=DEFAULT_EXEFS)
    p.add_argument("--romfs-bin", type=Path, default=DEFAULT_ROMFS_BIN)
    args = p.parse_args()

    deploy_to_ps5(
        host=args.host,
        port=args.port,
        out_root=args.out.resolve(),
        exefs_dir=args.exefs if args.exefs.is_dir() else None,
        romfs_bin=args.romfs_bin if args.romfs_bin.is_file() else None,
        upload_shaders=not args.skip_shaders,
        upload_ini=not args.skip_ini,
        upload_romfs=not args.skip_romfs,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
