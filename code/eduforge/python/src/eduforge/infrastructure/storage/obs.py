"""华为云 OBS 对象存储桩。

对齐方案 §1.2：
- 规划第 7～8 周接入真实华为云 OBS；
- 当前提供符合 ArtifactStoragePort 的接口桩，未配 OBS 凭证时提示保留位。
"""
from __future__ import annotations

import os

from eduforge.domain.errors import EduForgeError
from eduforge.domain.ports import ArtifactStoragePort


class OBSArtifactStorage(ArtifactStoragePort):
    """华为云 OBS 存储桩。"""

    def __init__(
        self,
        endpoint: str | None = None,
        bucket_name: str | None = None,
        ak: str | None = None,
        sk: str | None = None,
    ):
        self.endpoint = endpoint or os.getenv("HUAWEI_OBS_ENDPOINT")
        self.bucket = bucket_name or os.getenv("HUAWEI_OBS_BUCKET")
        self.ak = ak or os.getenv("HUAWEI_OBS_AK")
        self.sk = sk or os.getenv("HUAWEI_OBS_SK")

    def _ensure_client(self) -> None:
        if not (self.endpoint and self.ak and self.sk and self.bucket):
            raise EduForgeError(
                "华为云 OBS 凭证未配置。按方案第 7～8 周排期接入，当前请使用 LocalArtifactStorage。",
                code="OBS_NOT_CONFIGURED",
            )

    async def put(self, key: str, data: bytes, media_type: str) -> str:
        self._ensure_client()
        raise NotImplementedError("OBS 真实客户端在第 7～8 周华为云联调中接入。")

    async def get(self, key: str) -> bytes | None:
        self._ensure_client()
        raise NotImplementedError("OBS 真实客户端在第 7～8 周华为云联调中接入。")

    async def exists(self, key: str) -> bool:
        self._ensure_client()
        return False
