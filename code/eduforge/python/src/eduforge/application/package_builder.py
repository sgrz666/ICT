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

import asyncio
import hashlib
import json
import re
import zipfile
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


def verify_package_on_disk(pkg_dir: Path | str) -> dict[str, Any]:
    """按清单重算磁盘字节：想知道"这份包还是不是发布时那份"就用它（§C.5b）。

    为什么不能只信清单自己那份哈希：改一个 `www/` 里的文件、再重新生成一张自洽的清单，
    清单哈希照样对得上。所以逐文件重算、并与清单记录的 `package_sha256` 比；
    多出来/少了/内容变了都要单独列出来，否则"校验失败"这句话没法定位。
    """
    root = Path(pkg_dir)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return {"ok": False, "reason": "manifest_missing", "checked_files": 0,
                "missing": [], "unexpected": [], "changed": [],
                "package_sha256": None, "declared_package_sha256": None}
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    recorded = {e["path"]: e["sha256"] for e in declared.get("files", []) if isinstance(e, dict)}
    actual = {
        rel: _digest(p.read_bytes())
        for p in sorted(root.rglob("*"), key=lambda x: x.as_posix())
        if p.is_file() and (rel := _rel(p, root)) != MANIFEST_NAME
    }
    changed = sorted(p for p in set(recorded) & set(actual) if recorded[p] != actual[p])
    recomputed = package_digest([{"path": p, "sha256": s} for p, s in actual.items()])
    declared_sha = declared.get("package_sha256")
    return {
        "ok": not changed and not (set(recorded) ^ set(actual)) and recomputed == declared_sha,
        "reason": "disk_matches_manifest" if (
            not changed and not (set(recorded) ^ set(actual)) and recomputed == declared_sha
        ) else "disk_differs_from_manifest",
        "checked_files": len(actual),
        "declared_files": len(recorded),
        "missing": sorted(set(recorded) - set(actual))[:10],
        "unexpected": sorted(set(actual) - set(recorded))[:10],
        "changed": changed[:10],
        "package_sha256": recomputed,
        "declared_package_sha256": declared_sha,
        "entry": declared.get("entry"),
        "scene_sha256": declared.get("scene_sha256"),
    }


OFFLINE_README_TEMPLATE = """# EduForge 离线实验运行说明

本实验包为 EduForge 平台导出的独立离线运行包。

## 运行方式

由于现代浏览器的安全策略（CORS / 同源策略）限制通过 `file://` 协议直接加载本地语言包与资源，推荐通过本地静态服务器打开：

1. **Python 方式（推荐）**：
   在当前解压目录下打开终端并运行：
   ```bash
   python -m http.server 8080
   ```
   然后在浏览器中访问：`http://localhost:8080/www/index.html`

2. **Node.js 方式**：
   在当前解压目录下运行：
   ```bash
   npx serve www
   ```
   然后在浏览器中访问控制台打印的本地地址。

3. **入口文件**：
   `www/index.html`（实验场景数据已内置并可通过 `www/scene/native.json` 查看）。

## 许可证

本实验包基于 Apache-2.0 许可证分发，详见包内 `LICENSE` 文件。
"""

OFFLINE_LICENSE_FALLBACK = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION

   1. Definitions.
      "License" shall mean the terms and conditions for use, reproduction,
      and distribution as defined by Sections 1 through 9 of this document.

   2. Grant of Copyright License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      copyright license to reproduce, prepare Derivative Works of,
      publicly display, publicly perform, sublicense, and distribute the
      Work and such Derivative Works in Source or Object form.

   3. Grant of Patent License. Subject to the terms and conditions of
      this License, each Contributor hereby grants to You a perpetual,
      worldwide, non-exclusive, no-charge, royalty-free, irrevocable
      patent license to make, have made, use, offer to sell, sell, import,
      and otherwise transfer the Work.
"""


def file_sha256(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_license_bytes() -> bytes:
    try:
        upstream_lic = Path(__file__).resolve().parents[6] / "source" / "upstream" / "ray-optics" / "LICENSE"
        if upstream_lic.is_file():
            return upstream_lic.read_bytes()
    except Exception:
        pass
    return OFFLINE_LICENSE_FALLBACK.strip().encode("utf-8") + b"\n"


def build_deterministic_zip(pkg_dir: Path | str, zip_dest: Path | str) -> tuple[int, str]:
    """在已验证的 offline_package/ 上生成确定性 ZIP（Gate C §C.5b R2）。

    确定性保障：
    1. 路径严格按 POSIX 格式字典序排序；
    2. 固定时间戳为 (2026, 1, 1, 0, 0, 0)；
    3. 固定外部属性权限 0o100644（普通只读/读写文件）；
    4. 固定压缩模式 ZIP_DEFLATED，compresslevel=6；
    5. 严格防御 Zip Slip（禁止 '..'、绝对路径与前导斜杠）与符号链接；
    6. 必备补充文件：离线启动说明（README.md）与 Apache-2.0 许可（LICENSE）；
    7. 落盘后逐字节回读核对，返回 (文件大小, sha256 摘要)。
    """
    root = Path(pkg_dir).resolve()
    dest = Path(zip_dest).resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)

    entries: dict[str, bytes] = {}
    for p in sorted(root.rglob("*"), key=lambda x: x.as_posix()):
        if p.is_symlink():
            raise DeliveryIntegrityError(f"离线包内禁止包含符号链接：{p}")
        if not p.is_file():
            continue
        rel = _rel(p, root)
        if ".." in rel or rel.startswith("/") or rel.startswith("\\"):
            raise DeliveryIntegrityError(f"离线包内检测到非法路径：{rel}")
        entries[rel] = p.read_bytes()

    if "README.md" not in entries:
        entries["README.md"] = OFFLINE_README_TEMPLATE.encode("utf-8")
    if "LICENSE" not in entries:
        entries["LICENSE"] = get_license_bytes()

    temp_dest = dest.with_suffix(".tmp.zip")
    try:
        with zipfile.ZipFile(temp_dest, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for arcname in sorted(entries.keys()):
                zinfo = zipfile.ZipInfo(filename=arcname, date_time=(2026, 1, 1, 0, 0, 0))
                zinfo.external_attr = 0o100644 << 16
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zf.writestr(zinfo, entries[arcname])

        zip_digest = file_sha256(temp_dest)
        zip_size = temp_dest.stat().st_size

        temp_dest.replace(dest)
        actual_digest = file_sha256(dest)
        if actual_digest != zip_digest:
            raise DeliveryIntegrityError(
                f"ZIP 落盘核对失败：{actual_digest[:12]} != {zip_digest[:12]}"
            )
        return zip_size, zip_digest
    finally:
        if temp_dest.exists():
            temp_dest.unlink(missing_ok=True)


def collect_manifest_files(pkg_dir: Path | str) -> list[dict[str, str]]:
    """收集离线包目录下除顶层清单外的全部文件及其哈希。"""
    root = Path(pkg_dir)
    return [
        {"path": rel, "sha256": _digest(p.read_bytes())}
        for p in sorted(root.rglob("*"), key=lambda x: x.as_posix())
        if p.is_file() and (rel := _rel(p, root)) != MANIFEST_NAME
    ]


def verify_offline_zip(zip_path: Path | str, expected_sha: str | None = None) -> dict[str, Any]:
    """验证导出的离线 ZIP 包完整性：
    1. ZIP 文件自身 SHA256 摘要核对；
    2. 防 Zip Slip 路径安全审查；
    3. 清单与逐文件 SHA256 核对；
    4. 离线说明与许可必备文件检查（非空）；
    5. 未经清单声明的额外意外文件检测（防后门与恶意篡改）；
    6. 整包摘要与清单一致性核对。
    """
    path = Path(zip_path)
    if not path.is_file():
        return {"ok": False, "reason": "zip_missing"}

    actual_sha = file_sha256(path)
    if expected_sha and actual_sha != expected_sha:
        return {"ok": False, "reason": "zip_sha256_mismatch", "actual": actual_sha, "expected": expected_sha}

    try:
        with zipfile.ZipFile(path, "r") as zf:
            namelist = zf.namelist()
            for name in namelist:
                if ".." in name or name.startswith("/") or name.startswith("\\"):
                    return {"ok": False, "reason": "zip_slip_detected", "path": name}

            if MANIFEST_NAME not in namelist:
                return {"ok": False, "reason": "manifest_missing"}
            if "README.md" not in namelist:
                return {"ok": False, "reason": "readme_missing"}
            if "LICENSE" not in namelist:
                return {"ok": False, "reason": "license_missing"}

            readme_bytes = zf.read("README.md")
            if not readme_bytes.strip():
                return {"ok": False, "reason": "readme_empty"}
            license_bytes = zf.read("LICENSE")
            if not license_bytes.strip():
                return {"ok": False, "reason": "license_empty"}

            manifest_raw = zf.read(MANIFEST_NAME).decode("utf-8")
            declared = json.loads(manifest_raw)
            recorded = {e["path"]: e["sha256"] for e in declared.get("files", []) if isinstance(e, dict)}

            missing: list[str] = []
            changed: list[str] = []
            actual_files: list[dict[str, str]] = []
            checked = 0
            for rel, exp_sha in recorded.items():
                if rel not in namelist:
                    missing.append(rel)
                    continue
                checked += 1
                content = zf.read(rel)
                actual_digest = _digest(content)
                if actual_digest != exp_sha:
                    changed.append(rel)
                actual_files.append({"path": rel, "sha256": actual_digest})

            # 严格审查：ZIP 内不允许出现未经清单声明的意外文件（防后门与恶意篡改）
            allowed_top_level = {MANIFEST_NAME, "README.md", "LICENSE"}
            unexpected = sorted(
                name for name in namelist
                if not name.endswith("/") and name not in allowed_top_level and name not in recorded
            )

            # 核对整包摘要与清单声明
            declared_package_sha = declared.get("package_sha256")
            recomputed_package_sha = package_digest(actual_files) if not missing and not changed else None
            package_sha_mismatch = (
                declared_package_sha is not None
                and recomputed_package_sha is not None
                and declared_package_sha != recomputed_package_sha
            )

            ok = not missing and not changed and not unexpected and not package_sha_mismatch
            reason = "zip_matches_manifest"
            if unexpected:
                reason = "zip_unexpected_files"
            elif missing or changed:
                reason = "zip_differs_from_manifest"
            elif package_sha_mismatch:
                reason = "zip_package_sha256_mismatch"

            return {
                "ok": ok,
                "reason": reason,
                "zip_sha256": actual_sha,
                "checked_files": checked,
                "declared_files": len(recorded),
                "missing": missing[:10],
                "changed": changed[:10],
                "unexpected": unexpected[:10],
                "package_sha256": recomputed_package_sha,
                "declared_package_sha256": declared_package_sha,
                "entry": declared.get("entry"),
            }
    except Exception as exc:
        return {"ok": False, "reason": f"corrupted_zip: {exc}"}



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
        files = await asyncio.to_thread(collect_manifest_files, pkg_dir)
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
        # Gate C §C.5/§C.5c：交付前用真浏览器实测这份包，并核对回报的场景哈希。测不过就拿不到包，也就发布不出去。
        verification = await self._verify_package(pkg_dir, expected_scene_sha256=native_digest)
        self._write_verifying(
            pkg_dir.parent / "offline_verification.json",
            (json.dumps(verification, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        )
        # Gate C §C.5b R2：在已验证的 offline_package/ 上生成确定性 ZIP，并登记产物
        zip_file = pkg_dir.parent / "offline_package.zip"
        zip_size, zip_digest = await asyncio.to_thread(build_deterministic_zip, pkg_dir, zip_file)

        artifacts = [
            self._artifact(job_id, "offline_manifest", manifest_file, manifest_digest),
            self._artifact(job_id, "offline_zip", zip_file, zip_digest, media_type="application/zip"),
        ]
        offline = {
            "dir": str(pkg_dir),
            "index_file": str(index_file),
            # 入口在盘上只是必要条件；能不能跑出光路由浏览器实测说了算（见 verification）
            "index_present": index_file.is_file(),
            "file_count": len(files),
            "manifest_sha256": manifest_digest,
            "package_sha256": pkg_sha,
            "zip_file": str(zip_file),
            "zip_sha256": zip_digest,
            "zip_size": zip_size,
            "entry": metadata["entry"],
            "requires_local_static_server": metadata["requires_local_static_server"],
            "license": metadata["license"],
            "engine_version": metadata["engine_version"],
            "verification": verification,
        }
        return artifacts, offline, pkg_sha

    async def _verify_package(self, pkg_dir: Path, expected_scene_sha256: str | None = None) -> dict[str, Any]:
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
        scene_seen = result.get("scene_sha256")
        if not scene_seen:
            raise DeliveryIntegrityError(
                "浏览器预检未回报场景哈希（观测来源缺失），禁止放行", code="SCENE_SHA256_MISSING"
            )
        if expected_scene_sha256 and scene_seen != expected_scene_sha256:
            raise DeliveryIntegrityError(
                f"浏览器预检回报场景哈希与候选哈希不一致：seen={scene_seen}, expected={expected_scene_sha256}",
                code="SCENE_SHA256_MISMATCH",
            )
        return {
            "source": "browser:chromium",
            "ok": True,
            "checks": checks,
            "screenshot_sha256": result.get("screenshot_sha256"),
            "scene_sha256_seen": scene_seen,
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

    def _artifact(
        self, job_id: UUID, name: str, path: Path, digest: str, media_type: str = "application/json"
    ) -> dict[str, Any]:
        return {
            "id": str(artifact_id_for(job_id, name, digest)),
            "storage_key": _rel(path, self.artifact_dir),
            "sha256": digest,
            "media_type": media_type,
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
