"""启动本地 PostgreSQL 服务供开发和全系统一键启动使用（基于 pgserver）。"""
from __future__ import annotations

import argparse
import atexit
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
import pgserver


def _stop_postgres(data_dir: Path) -> None:
    venv_dir = Path(sys.executable).parent.parent
    pg_ctl = venv_dir / "Lib" / "site-packages" / "pgserver" / "pginstall" / "bin" / "pg_ctl.exe"
    if not pg_ctl.exists():
        pg_ctl = Path("pg_ctl")
    try:
        subprocess.run([str(pg_ctl), "-D", str(data_dir), "stop", "-m", "fast"], capture_output=True, timeout=5)
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Postgres server via pgserver")
    parser.add_argument("--data-dir", required=True, help="Path to postgres data directory")
    parser.add_argument("--uri-file", help="Path to write the connection URI to")
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    try:
        server = pgserver.get_server(str(data_dir), cleanup_mode=None)
    except Exception as exc:
        print(f"[ERROR] Failed to start PostgreSQL at {data_dir}: {exc}", file=sys.stderr)
        print("[ERROR] Database directory preserved for inspection. Not killing unrelated processes.", file=sys.stderr)
        raise

    uri = server.get_uri()
    print(f"[OK] PostgreSQL ready: {uri}", flush=True)

    if args.uri_file:
        uri_path = Path(args.uri_file).resolve()
        uri_path.parent.mkdir(parents=True, exist_ok=True)
        uri_path.write_text(uri, encoding="utf-8")

    def _cleanup():
        if args.uri_file:
            Path(args.uri_file).resolve().unlink(missing_ok=True)
        _stop_postgres(data_dir)

    atexit.register(_cleanup)

    def _handle_signal(signum, frame):
        _cleanup()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _cleanup()


if __name__ == "__main__":
    main()
