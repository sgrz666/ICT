"""交付包构建：**一次**构建决定发布出去的每一份字节。

Gate C §C.4 之前有三处不一致，每一处都能让「模型改的那份就是发布的那份」这句话漏掉：

1. 工具层 `build_package` 建离线包，Worker 的 packaging 阶段**根本不建**
   （`building` 还显式传 `export_offline_zip=False`）——同一个任务走哪条路径，
   决定交付物里到底有没有离线运行包。
2. Worker 与工具层各自拼 `artifacts` 列表、各自算产物 id，两份代码可以悄悄漂移。
3. 引擎往 `offline_package/manifest.json` 写交付元数据（入口、引擎版本、是否需要
   随包静态服务、许可），Python 又用「逐文件哈希表」**覆盖同一路径**，元数据在落盘的
   最后一刻消失——剩下的清单只认得文件哈希，不认得这份包该怎么打开。

本模块把三件事合成一次构建：产物字节由候选内容派生并逐字节回读核对；离线包由引擎组装，
但**包内场景文件替换成交付的那一份字节**（引擎按 `JSON.stringify(x, null, 2)` 写的漂亮副本
与 `native.json` 语义相同、字节不同，「验的就是发的」在包内也必须成立）；最终 manifest 同时
带引擎元数据、逐文件 SHA256 与整包摘要。
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from eduforge.application.candidate_service import CandidateState, native_bytes, views_bytes
from eduforge.domain.errors import DeliveryIntegrityError
from eduforge.infrastructure.db.repositories import artifact_id_for, revision_id_for

MANIFEST_NAME = "manifest.json"
# 引擎写的那几个键属于交付契约：合并进最终 manifest，不被哈希表顶掉
ENGINE_METADATA_KEYS = (
    "engine_id", "engine_version", "native_format_version",
    "entry", "requires_local_static_server", "license",
)
DEFAULT_TITLE = "EduForge 凸透镜成像实验"


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def package_digest(files: list[dict[str, str]]) -> str:
    """整包摘要：对「路径:sha256」按路径排序后拼接再取哈希。

    为什么不只看 manifest 自身的哈希：那个数锁的是这张清单的字节。逐文件表加上清单自哈希，
    仍挡不住「改一个 www/ 里的文件，再重新生成一张自洽的清单」；整包摘要是与清单写法无关的
    一个数，核对方把它和逐文件表放在一起比才查得出篡改。
    """
    lines = "".join(f"{f['path']}:{f['sha256']}\n" for f in sorted(files, key=lambda x: x["path"]))
    return _digest(lines.encode("utf-8"))


@dataclass(frozen=True)
class BuiltPackage:
    candidate_revision_id: UUID
    artifacts: list[dict[str, Any]]
    native_sha256: str
    package_sha256: str | None
    offline: dict[str, Any] | None


class PackageBuilder:
    """不判断「能不能发」，只把已冻结的候选变成可核对的交付字节。"""

    def __init__(self, *, engine_client: Any, artifact_dir: Path) -> None:
        self.engine_client = engine_client
        self.artifact_dir = Path(artifact_dir)

    def revision_dir(self, state: CandidateState) -> Path:
        return self.artifact_dir / "revisions" / str(revision_id_for(state.job_id, state.content_hash))

    async def build(
        self, state: CandidateState, *, include_offline: bool = True, title: str = DEFAULT_TITLE
    ) -> BuiltPackage:
        job_id = state.job_id
        cand = revision_id_for(job_id, state.content_hash)
        cand_dir = self.revision_dir(state)
        cand_dir.mkdir(parents=True, exist_ok=True)

        artifacts: list[dict[str, Any]] = []
        payload = native_bytes(state.native_data)
        native_file = self._write_verifying(cand_dir / "native.json", payload)
        native_digest = _digest(payload)
        artifacts.append(self._artifact(job_id, "native", native_file, native_digest))

        views_payload = views_bytes(state.teaching_views) if state.teaching_views else None
        if views_payload is not None:
            views_file = self._write_verifying(cand_dir / "teaching_views.json", views_payload)
            artifacts.append(self._artifact(job_id, "teaching_views", views_file, _digest(views_payload)))

        offline: dict[str, Any] | None = None
        pkg_sha: str | None = None
        if include_offline:
            more, offline, pkg_sha = await self._offline(
                state, job_id, payload, views_payload, native_digest, title
            )
            artifacts.extend(more)

        return BuiltPackage(
            candidate_revision_id=cand,
            artifacts=artifacts,
            native_sha256=native_digest,
            package_sha256=pkg_sha,
            offline=offline,
        )

    async def _offline(
        self,
        state: CandidateState,
        job_id: UUID,
        payload: bytes,
        views_payload: bytes | None,
        native_digest: str,
        title: str,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
        pkg_dir = self.revision_dir(state) / "offline_package"
        res = await self.engine_client.export_offline_package(
            state.native_data, out_dir=str(pkg_dir), options={"title": title}
        )
        pkg_dir = Path(res.get("dir") or pkg_dir)

        scene_file = pkg_dir / "www" / "scene" / "native.json"
        if not scene_file.is_file():
            raise DeliveryIntegrityError(f"离线包里没有引擎写出的场景文件：{scene_file}")
        # 替换成交付字节：包内那份场景与登记在 artifacts 的 native.json 必须逐字节相同
        self._write_verifying(scene_file, payload)
        if views_payload is not None:
            self._write_verifying(pkg_dir / "www" / "scene" / "teaching_views.json", views_payload)

        metadata = self._engine_metadata(pkg_dir / MANIFEST_NAME)
        # 只排除**这一份**清单本身：上游 dist 里另有一个 www/manifest.json（PWA 清单），
        # 按文件名排除会把一个真实交付物漏在哈希表外面。
        files = [
            {"path": rel, "sha256": _digest(p.read_bytes())}
            for p in sorted(pkg_dir.rglob("*"), key=lambda x: x.as_posix())
            if p.is_file() and (rel := _rel(p, pkg_dir)) != MANIFEST_NAME
        ]
        pkg_sha = package_digest(files)
        manifest_bytes = (
            json.dumps(
                {**metadata, "scene_sha256": native_digest, "file_count": len(files),
                 "files": files, "package_sha256": pkg_sha},
                ensure_ascii=False, indent=2,
            )
            + "\n"
        ).encode("utf-8")
        manifest_file = self._write_verifying(pkg_dir / MANIFEST_NAME, manifest_bytes)
        manifest_digest = _digest(manifest_bytes)

        index_file = Path(res.get("index_file") or pkg_dir / "www" / "index.html")
        # Gate C §C.5：交付前用真浏览器实测这份包。测不过就拿不到包，也就发布不出去。
        verification = await self._verify_package(pkg_dir)
        self._write_verifying(
            pkg_dir.parent / "offline_verification.json",
            (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        artifacts = [
            self._artifact(job_id, "offline_manifest", manifest_file, manifest_digest)
        ]
        offline = {
            "dir": str(pkg_dir),
            "index_file": str(index_file),
            # 入口在盘上只是必要条件；能不能跑出光路由浏览器实测说了算（见 verification）
            "index_present": index_file.is_file(),
            "file_count": len(files),
            "manifest_sha256": manifest_digest,
            "package_sha256": pkg_sha,
            "entry": metadata["entry"],
            "requires_local_static_server": metadata["requires_local_static_server"],
            "license": metadata["license"],
            "engine_version": metadata["engine_version"],
            "verification": verification,
        }
        return artifacts, offline, pkg_sha

    async def _verify_package(self, pkg_dir: Path) -> dict[str, Any]:
        """让引擎宿主用 Chromium 真打开这份包，拿逐项判据回来。

        判据在引擎侧产生：入口存在、欢迎页被隐藏（场景真进去了）、光层画出了像素、
        零出网、无页面错误。任何一条不成立就抛 `DeliveryIntegrityError`——
        「发布出去的包打开是空白」和「科学验证不通过」一样，必须是可见的失败。
        """
        verify = getattr(self.engine_client, "verify_offline_package", None)
        if verify is None:
            raise DeliveryIntegrityError("引擎客户端不支持离线包浏览器实测，不能凭推断放行")
        result = await verify(str(pkg_dir))
        checks = result.get("checks", [])
        if not result.get("ok"):
            failed = ", ".join(
                f"{c.get('id')}→{str(c.get('observed'))[:80]}" for c in checks if not c.get("passed")
            )
            raise DeliveryIntegrityError(
                f"离线包浏览器实测未通过：{failed or '引擎未回报判据'}", code="OFFLINE_NOT_RENDERED"
            )
        return {
            "source": "browser:chromium",
            "ok": True,
            "checks": checks,
            "screenshot_sha256": result.get("screenshot_sha256"),
            "scene_sha256_seen": result.get("scene_sha256"),
        }

    def _engine_metadata(self, manifest_path: Path) -> dict[str, Any]:
        """读回引擎写的交付元数据。缺一个键就说明引擎的交付契约变了，不静默补默认值。"""
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise DeliveryIntegrityError(f"引擎没有产出交付元数据：{manifest_path}") from None
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DeliveryIntegrityError(f"交付元数据不可解析：{manifest_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise DeliveryIntegrityError(f"交付元数据不是对象：{manifest_path}")
        # 重新生成过的包，manifest 已是我们上次写的合并版：那些键还在就仍然成立
        missing = [k for k in ENGINE_METADATA_KEYS if k not in raw]
        if missing:
            raise DeliveryIntegrityError(f"交付元数据缺键 {missing}（引擎交付契约变了）：{manifest_path}")
        return {k: raw[k] for k in ENGINE_METADATA_KEYS}

    def _artifact(self, job_id: UUID, name: str, path: Path, digest: str) -> dict[str, Any]:
        return {
            "id": str(artifact_id_for(job_id, name, digest)),
            "storage_key": _rel(path, self.artifact_dir),
            "sha256": digest,
            "media_type": "application/json",
        }

    def _write_verifying(self, path: Path, payload: bytes) -> Path:
        """落盘后逐字节回读核对。

        这条不是洁癖：Worker 的 packaging 阶段以前只相信「building 阶段写过这个文件」，
        交付字节与候选内容不一致时静默发布。现在写入即核对，不一致就抛可见的交付完整性错误。
        """
        if path.is_file() and path.read_bytes() == payload:
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        actual = path.read_bytes()
        if actual != payload:
            raise DeliveryIntegrityError(
                f"{path} 回读字节与候选内容不一致："
                f"{_digest(actual)[:12]} != {_digest(payload)[:12]}"
            )
        return path


def _rel(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")
