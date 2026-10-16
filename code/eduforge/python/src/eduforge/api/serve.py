"""uvicorn 入口：`python -m uvicorn eduforge.api.serve:app`。

配置只从环境变量来（EDUFORGE_DSN、EDUFORGE_ARTIFACT_DIR），缺一个就拒绝启动。
artifact_dir 不给默认值是有意的：产物字节必须有一个明确的交付目录，
否则下载接口只能回落到数据库里那份 jsonb 文本，哈希校验就成了假校验。
"""
from __future__ import annotations

import os

from eduforge.api.main import create_app

_dsn = (os.environ.get("EDUFORGE_DSN") or "").strip()
_artifact_dir = (os.environ.get("EDUFORGE_ARTIFACT_DIR") or "").strip()

if not _dsn or not _artifact_dir:
    raise SystemExit("EDUFORGE_DSN 与 EDUFORGE_ARTIFACT_DIR 都必须设置，拒绝启动")

app = create_app(_dsn, _artifact_dir)
