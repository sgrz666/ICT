"""Gate C §C.4：统一交付包构建器（`application/package_builder.py`）的核对面。

这里用**假引擎客户端**：只写几个文件当"包"，于是所有断言都落在构建器自己的职责上——
交付字节逐字节回读、引擎交付元数据不被哈希表覆盖、逐文件表完整、整包摘要可从磁盘重算。
真链路上的等价验证（同一个 builder、真上游 dist、2163 个文件）见
`test_chain_worker.py::test_chain_publishes_and_delivers_exactly_the_hashed_bytes`。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any

import pytest

from eduforge.application.candidate_service import CandidateState, native_bytes, views_bytes
from eduforge.application.package_builder import (
    MANIFEST_NAME,
    PackageBuilder,
    build_deterministic_zip,
    package_digest,
    verify_offline_zip,
    verify_package_on_disk,
)
from eduforge.domain.errors import DeliveryIntegrityError

JOB_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
NATIVE: dict[str, Any] = {"version": 5, "objs": [{"type": "IdealLens", "focalLength": 150}]}


def make_state(*, views: dict[str, Any] | None = None) -> CandidateState:
    views = views or {}
    digest = hashlib.sha256(
        json.dumps({"native": NATIVE, "views": views}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return CandidateState(
        candidate_id=uuid.uuid5(uuid.NAMESPACE_OID, "c"),
        job_id=JOB_ID,
        experiment_id=uuid.uuid5(uuid.NAMESPACE_OID, "e"),
        base_revision=uuid.uuid5(uuid.NAMESPACE_OID, "b"),
        owner_id="teacher-a",
        template_id="optics.convex_lens",
        native_data=NATIVE,
        teaching_views=views,
        content_hash=digest,
        status="frozen",
    )


class FakeEngine:
    """模拟引擎的离线包产出：包里放一个**嵌套的同名 manifest.json**（上游 dist 真有：www/simulator/manifest/manifest.json）。"""

    def __init__(self, *, metadata: bool = True, verify_ok: bool = True, supports_verify: bool = True) -> None:
        self.metadata = metadata
        self.verify_ok = verify_ok
        self.calls: list[str] = []
        self.verified: list[str] = []
        if not supports_verify:
            # 模拟一个还不认识"浏览器实测"这件事的引擎客户端（实例属性置空即可，
            # 删掉它会退回类上的方法，那条负向用例就测不出东西了）
            self.verify_offline_package = None  # type: ignore[assignment]

    async def export_offline_package(self, scene: dict, out_dir: str, options: dict | None = None) -> dict:
        self.calls.append(out_dir)
        root = Path(out_dir)
        scene_dir = root / "www" / "scene"
        scene_dir.mkdir(parents=True, exist_ok=True)
        (root / "www" / "index.html").write_text("<html>entry</html>", encoding="utf-8")
        nested = root / "www" / "simulator" / "manifest"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / MANIFEST_NAME).write_text('{"name":"上游自己的嵌套清单"}', encoding="utf-8")
        # 引擎按 JSON.stringify(x, null, 2) 写场景副本：语义相同，字节与交付的那一份不同
        (scene_dir / "native.json").write_text(json.dumps(scene, indent=2), encoding="utf-8")
        if self.metadata:
            (root / MANIFEST_NAME).write_text(
                json.dumps({
                    "engine_id": "ray_optics", "engine_version": "5.5.0",
                    "native_format_version": 5, "scene_sha256": "旧的漂亮副本哈希",
                    "entry": "www/index.html", "requires_local_static_server": True,
                    "license": "Apache-2.0 (Ray Optics)",
                }),
                encoding="utf-8",
            )
        return {"dir": str(root), "index_file": str(root / "www" / "index.html")}

    async def verify_offline_package(self, package_dir: str, timeout: float = 180.0) -> dict[str, Any]:
        """替身浏览器：只回报判据，真浏览器的行为在 engine-host 侧测（见 vitest）。"""
        self.verified.append(package_dir)
        if not self.verify_ok:
            return {
                "ok": False, "scene_sha256": None, "screenshot_sha256": None,
                "checks": [
                    {"id": "entry_file_present", "passed": True, "observed": "在"},
                    {"id": "rays_rendered", "passed": False, "observed": "光强 0，点亮像素 0（3 个 frame）"},
                ],
            }
        return {
            "ok": True, "scene_sha256": "abc", "screenshot_sha256": "f" * 64,
            "checks": [{"id": "rays_rendered", "passed": True, "observed": "光强 287776335，点亮像素 453202"}],
        }


def builder(tmp_path: Path, engine: FakeEngine) -> PackageBuilder:
    return PackageBuilder(engine_client=engine, artifact_dir=tmp_path)


def test_manifest_keeps_engine_metadata_and_adds_full_file_table(tmp_path):
    engine = FakeEngine()
    built = asyncio.run(builder(tmp_path, engine).build(make_state(), include_offline=True))
    manifest = json.loads((Path(built.offline["dir"]) / MANIFEST_NAME).read_text(encoding="utf-8"))

    # 交付元数据活下来了：以前 Python 的哈希表把这个路径整个覆盖掉
    assert manifest["entry"] == "www/index.html" and manifest["requires_local_static_server"] is True
    assert manifest["engine_version"] == "5.5.0" and manifest["license"].startswith("Apache")
    # 场景哈希改成交付字节的哈希，而不是引擎那份 pretty 副本
    assert manifest["scene_sha256"] == built.native_sha256
    # 逐文件表只排除**这一份**清单；嵌套的同名文件必须在表里（按文件名排除会漏交付物）
    paths = {f["path"] for f in manifest["files"]}
    assert "www/simulator/manifest/manifest.json" in paths and MANIFEST_NAME not in paths
    assert manifest["file_count"] == len(manifest["files"])
    assert manifest["package_sha256"] == package_digest(manifest["files"])


def test_scene_inside_package_is_the_delivered_bytes(tmp_path):
    """包内那份场景必须与登记在 artifacts 里的字节逐字节相同，否则"验的就是发的"在包内不成立。"""
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(make_state(), include_offline=True))
    in_pkg = Path(built.offline["dir"]) / "www" / "scene" / "native.json"
    assert in_pkg.read_bytes() == native_bytes(NATIVE) == (tmp_path / "revisions" / str(built.candidate_revision_id) / "native.json").read_bytes()


def test_tampering_a_package_file_breaks_the_stored_digest(tmp_path):
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(make_state(), include_offline=True))
    root = Path(built.offline["dir"])
    entry = next(e for e in json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))["files"]
                 if e["path"] == "www/index.html")
    (root / "www" / "index.html").write_text("<html>换了内容</html>", encoding="utf-8")

    assert hashlib.sha256((root / "www" / "index.html").read_bytes()).hexdigest() != entry["sha256"]
    # 重扫磁盘得到的逐文件表与清单对不上 ⇒ 篡改可查（与清单自身的写法无关的那个数）
    rescan = [
        {"path": str(p.relative_to(root)).replace("\\", "/"),
         "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in sorted(root.rglob("*")) if p.is_file() and str(p.relative_to(root)).replace("\\", "/") != MANIFEST_NAME
    ]
    assert package_digest(rescan) != built.package_sha256


def test_missing_engine_metadata_is_a_visible_refusal_not_a_silent_default(tmp_path):
    with pytest.raises(DeliveryIntegrityError, match="交付元数据"):
        asyncio.run(builder(tmp_path, FakeEngine(metadata=False)).build(make_state(), include_offline=True))


def test_rebuild_is_idempotent_on_content_derived_ids(tmp_path):
    state = make_state(views={"measurement_table": True})
    first = asyncio.run(builder(tmp_path, FakeEngine()).build(state))
    second = asyncio.run(builder(tmp_path, FakeEngine()).build(state))
    assert [a["id"] for a in first.artifacts] == [a["id"] for a in second.artifacts]
    assert first.native_sha256 == second.native_sha256
    assert first.package_sha256 == second.package_sha256
    # 教学视图：登记为产物，同时以**交付字节**放进包里
    keys = {a["storage_key"] for a in first.artifacts}
    assert any(k.endswith("teaching_views.json") for k in keys), keys
    in_pkg = Path(first.offline["dir"]) / "www" / "scene" / "teaching_views.json"
    assert in_pkg.read_bytes() == views_bytes(state.teaching_views)


def test_include_offline_false_writes_only_delivered_content(tmp_path):
    """工具层可以只要内容不要离线包（building 阶段），此时一个包文件都不该出现。"""
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(make_state(), include_offline=False))
    assert built.offline is None and built.package_sha256 is None
    assert [a["storage_key"].split("/")[-1] for a in built.artifacts] == ["native.json"]
    assert not (tmp_path / "revisions" / str(built.candidate_revision_id) / "offline_package").exists()


def test_a_stale_file_at_the_content_derived_path_is_rewritten_not_shipped(tmp_path):
    """路径由内容哈希派生，所以那里的"陈旧文件"只可能是同内容的坏写入。

    构建器的语义是：写之前先比，不同就重写，写完再回读核对。
    旧实现相反——发现盘上字节与候选不一致就直接拒绝发布，于是接管者从 packaging
    重跑时会被自己上次崩在半路的半成品卡死。这里钉住新语义，并保证坏字节发不出去。
    """
    state = make_state()
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=False))
    target = tmp_path / "revisions" / str(built.candidate_revision_id) / "native.json"
    stale = target.read_bytes()
    target.write_bytes(stale[:-30] + b"X" * 30)  # 破坏最后一行的一段字节

    again = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=False))
    assert target.read_bytes() == stale, "坏字节必须被候选内容重写"
    assert again.native_sha256 == built.native_sha256 == hashlib.sha256(stale).hexdigest()
    assert [a["id"] for a in again.artifacts] == [a["id"] for a in built.artifacts]


def test_package_that_does_not_render_cannot_be_built_or_published(tmp_path):
    """§C.5：浏览器实测不通过 ⇒ 这份包根本没建出来，发布链走不到 Publisher。

    以前只有 `index_present`（入口文件在盘上），打开是空白也算"交付完成"。
    """
    engine = FakeEngine(verify_ok=False)
    with pytest.raises(DeliveryIntegrityError, match="浏览器实测未通过"):
        asyncio.run(builder(tmp_path, engine).build(make_state(), include_offline=True))
    assert engine.verified, "根本没去实测"
    # 实测结论没通过时不落 verification.json，避免留下"看起来验过"的现场
    assert not (tmp_path / "revisions").exists() or not list(
        (tmp_path / "revisions").rglob("offline_verification.json")
    )


def test_verification_conclusion_is_recorded_next_to_the_package(tmp_path):
    engine = FakeEngine()
    built = asyncio.run(builder(tmp_path, engine).build(make_state(), include_offline=True))
    assert built.offline["verification"]["ok"] is True
    assert built.offline["verification"]["source"] == "browser:chromium"
    assert built.offline["verification"]["checks"][0]["id"] == "rays_rendered"
    record = tmp_path / "revisions" / str(built.candidate_revision_id) / "offline_verification.json"
    assert json.loads(record.read_text(encoding="utf-8"))["ok"] is True
    assert engine.verified == [built.offline["dir"]]


def test_engine_client_without_browser_verification_is_not_assumed_ok(tmp_path):
    """客户端不认识实测方法时，宁可拒绝也不能默认通过。"""
    with pytest.raises(DeliveryIntegrityError, match="不支持离线包浏览器实测"):
        asyncio.run(builder(tmp_path, FakeEngine(supports_verify=False)).build(make_state(), include_offline=True))


def test_disk_reverification_follows_the_manifest_not_the_manifest_hash(tmp_path):
    """§C.5b：按清单逐文件重算。改一个 www/ 里的文件必须被查出来。

    只看清单自身那份哈希是查不出篡改的——改完文件再重新生成一张自洽的清单，
    哈希照样对得上，所以这里比的是"盘上每一块字节 vs 清单记录的哈希"。
    """
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(make_state(), include_offline=True))
    root = Path(built.offline["dir"])

    clean = verify_package_on_disk(root)
    assert clean["ok"] is True and clean["reason"] == "disk_matches_manifest", clean
    # \u5047\u5f15\u64ce\u5199\u51fa\u7684\u6574\u5305\uff1a\u9996\u9875 + \u4e0a\u6e38\u90a3\u4efd\u5d4c\u5957\u6e05\u5355 + \u573a\u666f\u6587\u4ef6\uff08\u672c\u8f6e\u6ca1\u5f00\u89c6\u56fe\uff0c\u6545\u65e0 teaching_views\uff09
    assert clean["checked_files"] == clean["declared_files"] == 3, clean

    target = root / "www" / "index.html"
    target.write_bytes(b"<html>replaced by tamper</html>")
    tampered = verify_package_on_disk(root)
    assert tampered["ok"] is False and tampered["reason"] == "disk_differs_from_manifest"
    assert tampered["changed"] == ["www/index.html"], tampered
    assert tampered["package_sha256"] != tampered["declared_package_sha256"]

    (root / "www" / "extra.js").write_bytes(b"// extra file, never declared in the manifest")
    assert verify_package_on_disk(root)["unexpected"] == ["www/extra.js"]
    assert verify_package_on_disk(root / "nowhere")["reason"] == "manifest_missing"


def test_deterministic_zip_generates_identical_bytes_and_records_metadata(tmp_path):
    """Gate C §C.5b R2：同一候选构建的 ZIP 包必须字节级确定性，且登记产物元数据。"""
    state = make_state()
    engine1 = FakeEngine()
    engine2 = FakeEngine()
    b1 = builder(tmp_path / "run1", engine1)
    b2 = builder(tmp_path / "run2", engine2)

    res1 = asyncio.run(b1.build(state, include_offline=True))
    res2 = asyncio.run(b2.build(state, include_offline=True))

    zip1 = Path(res1.offline["zip_file"])
    zip2 = Path(res2.offline["zip_file"])
    assert zip1.is_file() and zip2.is_file()
    bytes1 = zip1.read_bytes()
    bytes2 = zip2.read_bytes()

    assert bytes1 == bytes2, "相同候选场景两次构建产生的 ZIP 文件字节必须逐位全等（确定性构建）"
    assert res1.offline["zip_sha256"] == hashlib.sha256(bytes1).hexdigest()
    assert res1.offline["zip_size"] == len(bytes1)
    assert res1.offline["zip_sha256"] == res2.offline["zip_sha256"]

    # 产物登记
    zip_art = [a for a in res1.artifacts if a["storage_key"].endswith("offline_package.zip")]
    assert len(zip_art) == 1
    assert zip_art[0]["media_type"] == "application/zip"
    assert zip_art[0]["sha256"] == res1.offline["zip_sha256"]


def test_deterministic_zip_contains_all_deliverables_and_passes_verification(tmp_path):
    """ZIP 必须包含 www/、manifest.json、离线启动说明 README.md 及许可文件 LICENSE。"""
    import zipfile
    state = make_state()
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=True))
    zip_path = Path(built.offline["zip_file"])

    res = verify_offline_zip(zip_path, built.offline["zip_sha256"])
    assert res["ok"] is True, res
    assert res["reason"] == "zip_matches_manifest"
    assert res["checked_files"] == 3

    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    assert (extract_dir / "manifest.json").is_file()
    assert (extract_dir / "README.md").is_file()
    assert (extract_dir / "LICENSE").is_file()
    assert (extract_dir / "www" / "index.html").is_file()

    readme_text = (extract_dir / "README.md").read_text(encoding="utf-8")
    assert "http.server" in readme_text
    license_text = (extract_dir / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text


def test_verify_offline_zip_detects_tampered_payload_or_missing_file(tmp_path):
    """负向测试：损坏的 ZIP 或摘要对不上必须被拦截。"""
    state = make_state()
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=True))
    zip_path = Path(built.offline["zip_file"])

    # 摘要不匹配拦截
    wrong_sha = "0" * 64
    mismatch = verify_offline_zip(zip_path, expected_sha=wrong_sha)
    assert mismatch["ok"] is False and mismatch["reason"] == "zip_sha256_mismatch"

    # 文件损坏拦截
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"not a valid zip file content")
    corrupt_res = verify_offline_zip(corrupt_zip)
    assert corrupt_res["ok"] is False and "corrupted_zip" in corrupt_res["reason"]


def test_build_deterministic_zip_rejects_symlinks(tmp_path):
    """安全审查：禁止向交付包注入符号链接。即使在无符号链接特权的平台也能实测校验。"""
    import os
    from unittest.mock import patch

    pkg = tmp_path / "unsafe_pkg"
    pkg.mkdir()
    (pkg / "manifest.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("secret", encoding="utf-8")
    sym = pkg / "symlink_file"
    try:
        os.symlink(target, sym)
        with pytest.raises(DeliveryIntegrityError, match="符号链接"):
            build_deterministic_zip(pkg, tmp_path / "out.zip")
    except (OSError, NotImplementedError):
        # 普通权限 Windows 不允许创建符号链接，通过 mock 注入 is_symlink=True，确保安全防线真被实测
        fake_sym = pkg / "fake_symlink"
        fake_sym.write_text("fake_sym_content", encoding="utf-8")
        orig_is_symlink = Path.is_symlink

        def mocked_is_symlink(self):
            if self.name == "fake_symlink":
                return True
            return orig_is_symlink(self)

        with patch.object(Path, "is_symlink", mocked_is_symlink):
            with pytest.raises(DeliveryIntegrityError, match="符号链接"):
                build_deterministic_zip(pkg, tmp_path / "out.zip")


def test_verify_offline_zip_rejects_unexpected_injected_files(tmp_path):
    """安全负向：ZIP 内塞入未在清单中声明的额外意外文件（如木马/后门）必须被拦截。"""
    import zipfile
    state = make_state()
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=True))
    orig_zip = Path(built.offline["zip_file"])

    tampered_zip = tmp_path / "injected.zip"
    with zipfile.ZipFile(orig_zip, "r") as zf_in, zipfile.ZipFile(tampered_zip, "w") as zf_out:
        for item in zf_in.infolist():
            zf_out.writestr(item, zf_in.read(item.filename))
        zf_out.writestr("backdoor.py", b"import os; os.system('bad')")

    res = verify_offline_zip(tampered_zip)
    assert res["ok"] is False
    assert res["reason"] == "zip_unexpected_files"
    assert "backdoor.py" in res["unexpected"]


def test_verify_offline_zip_rejects_tampered_package_sha256_or_empty_readme(tmp_path):
    """安全负向：清单中 package_sha256 被篡改，或 README.md 为空必须被拦截。"""
    import zipfile
    state = make_state()
    built = asyncio.run(builder(tmp_path, FakeEngine()).build(state, include_offline=True))
    orig_zip = Path(built.offline["zip_file"])

    # 1. 篡改清单中的 package_sha256
    tampered_manifest_zip = tmp_path / "tampered_manifest.zip"
    with zipfile.ZipFile(orig_zip, "r") as zf_in, zipfile.ZipFile(tampered_manifest_zip, "w") as zf_out:
        for item in zf_in.infolist():
            content = zf_in.read(item.filename)
            if item.filename == "manifest.json":
                data = json.loads(content.decode("utf-8"))
                data["package_sha256"] = "f" * 64
                content = json.dumps(data).encode("utf-8")
            zf_out.writestr(item, content)

    res_manifest = verify_offline_zip(tampered_manifest_zip)
    assert res_manifest["ok"] is False
    assert res_manifest["reason"] == "zip_package_sha256_mismatch"

    # 2. 空 README 拦截
    empty_readme_zip = tmp_path / "empty_readme.zip"
    with zipfile.ZipFile(orig_zip, "r") as zf_in, zipfile.ZipFile(empty_readme_zip, "w") as zf_out:
        for item in zf_in.infolist():
            content = zf_in.read(item.filename)
            if item.filename == "README.md":
                content = b"   \n"
            zf_out.writestr(item, content)

    res_readme = verify_offline_zip(empty_readme_zip)
    assert res_readme["ok"] is False
    assert res_readme["reason"] == "readme_empty"

