"""Gate C.6 (R4): 案例库多模板真实导入与只读案例明确隔离实测。

覆盖：
1. catalog 真实加载 3 个光学模板（凸透镜、凹透镜、照相机成像原理）；
2. 基于各模板创建真实独立实验，种子版本具有各自独立的原生场景，消除静默回退；
3. 负向测试：未登记/未适配的案例 ID 严格拒放（TemplateNotFound / 404），杜绝伪造定制；
4. 工具服务 search_experiments 动态检索全部已在位模板，支持不同模板的调参与教学视图配置；
5. thin_lens_reference 理论公式对凹透镜负焦距与照相机大于二倍焦距实像自洽计算；
6. 案例库元数据严格区分 3 个支持案例与 78 个只读演示案例。
"""
from __future__ import annotations

import asyncio
import json
import math
import tempfile
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import asyncpg
import pgserver
import pytest

from eduforge.application.experiment_service import ExperimentService, TemplateNotFound
from eduforge.domain.contracts import SetParameter, SetView
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    ConfigureTeachingViewsInput,
    JobContext,
    OpenExperimentInput,
    SearchExperimentsInput,
)
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.catalog import list_templates, load_native, load_template
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.validation.scientific.optics import thin_lens_reference

ROOT = Path(__file__).resolve().parents[2]
GALLERY_DATA = ROOT / "apps" / "teacher-web" / "src" / "data" / "galleryData.json"


def test_catalog_loads_three_distinct_optics_templates():
    """清单动态枚举包含 3 套真实光学模板，字段与原生场景各自独立。"""
    templates = list_templates()
    template_ids = {t.template_id for t in templates}

    assert "optics.convex_lens" in template_ids
    assert "optics.concave_lens" in template_ids
    assert "optics.camera_principle" in template_ids

    # 凹透镜模板校验
    concave = load_template("optics.concave_lens")
    assert concave.title == "凹透镜发散与成像"
    assert concave.engine_id == "ray_optics"
    assert concave.units_per_unit == 10
    concave_f = next(c for c in concave.controls if c.parameter == "focal_length_cm")
    assert concave_f.min < 0 and concave_f.max < 0  # 负焦距量程

    concave_native = load_native("optics.concave_lens")
    assert concave_native["version"] == 5
    lens_obj = next(o for o in concave_native["objs"] if o.get("name") == "lens_1")
    assert lens_obj["type"] == "IdealLens"
    assert lens_obj["focalLength"] < 0

    # 照相机模板校验
    camera = load_template("optics.camera_principle")
    assert camera.title == "照相机成像原理"
    assert camera.engine_id == "ray_optics"
    camera_native = load_native("optics.camera_principle")
    assert any(o.get("name") == "sensor_1" for o in camera_native["objs"])
    assert any(o.get("name") == "aperture_1" for o in camera_native["objs"])


def test_gallery_metadata_separates_customizable_and_readonly():
    """81 个案例库中严格只有 3 个真实适配模板带有 templateId，其余 78 个为只读演示。"""
    assert GALLERY_DATA.exists()
    items = json.loads(GALLERY_DATA.read_text(encoding="utf-8"))
    assert len(items) == 81

    customizable = [it for it in items if it.get("templateId")]
    readonly = [it for it in items if not it.get("templateId")]

    assert len(customizable) == 3
    assert len(readonly) == 78

    c_map = {it["id"]: it["templateId"] for it in customizable}
    assert c_map["convex-lens"] == "optics.convex_lens"
    assert c_map["concave-lens"] == "optics.concave_lens"
    assert c_map["the-principle-of-camera-imaging"] == "optics.camera_principle"

    # 原先被误映射的“两面镜子成像”严格为只读
    two_mirrors = next(it for it in items if it["id"] == "images-formed-by-two-mirrors")
    assert "templateId" not in two_mirrors or two_mirrors["templateId"] is None


def test_thin_lens_reference_supports_concave_lens():
    """薄透镜独立参考公式正确处理凹透镜负焦距与实像/虚像分类。"""
    # 凹透镜（显式声明 allow_diverging 或使用 concave_lens_reference）：f = -10cm, u = 30cm => v = -7.5cm (虚像), m = 0.25 (正立缩小)
    res_concave = thin_lens_reference(-10.0, 30.0, allow_diverging=True)
    assert res_concave["image_kind"] == "virtual"
    assert math.isclose(res_concave["image_distance_cm"], -7.5, rel_tol=1e-4)
    assert math.isclose(res_concave["magnification"], 0.25, rel_tol=1e-4)

    # 默认凸透镜模式下，负焦距必须被拒（保持与原有 GATE-2 协议测试严格兼容）
    with pytest.raises(ValueError):
        thin_lens_reference(-10.0, 30.0)

    # 照相机：f = 15.5cm, u = 97.7cm (> 2f) => 15.5 < v < 31cm (倒立缩小实像)
    res_camera = thin_lens_reference(15.5, 97.7)
    assert res_camera["image_kind"] == "real"
    assert 15.5 < res_camera["image_distance_cm"] < 31.0
    assert -1.0 < res_camera["magnification"] < 0.0

    # 异常校验：物距非正、焦距为 0 均被拒
    with pytest.raises(ValueError):
        thin_lens_reference(0.0, 30.0)
    with pytest.raises(ValueError):
        thin_lens_reference(10.0, -5.0)


def test_create_experiment_from_multiple_templates():
    """真实数据库环境下基于不同模板创建实验，初始原生数据各自独立无串扰。"""
    async def go():
        srv = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-test-c6-"), cleanup_mode=None)
        conn = await asyncpg.connect(srv.get_uri())
        try:
            from eduforge.infrastructure.db.migrations import apply_migrations
            await apply_migrations(conn)

            service = ExperimentService(conn)
            owner_id = "teacher_c6_tester"

            # 1. 创建凸透镜实验
            exp_convex = await service.create_from_template(owner_id=owner_id, template_id="optics.convex_lens")
            assert exp_convex.template_id == "optics.convex_lens"

            # 2. 创建凹透镜实验
            exp_concave = await service.create_from_template(owner_id=owner_id, template_id="optics.concave_lens")
            assert exp_concave.template_id == "optics.concave_lens"
            assert exp_concave.experiment_id != exp_convex.experiment_id

            # 3. 创建相机原理实验
            exp_camera = await service.create_from_template(owner_id=owner_id, template_id="optics.camera_principle")
            assert exp_camera.template_id == "optics.camera_principle"

            # 从数据库中核对各自初始 native_data 确实不同
            rev_concave = await conn.fetchrow(
                "select native_data from experiment_revisions where id = $1", exp_concave.base_revision
            )
            concave_json = json.loads(rev_concave["native_data"])
            lens = next(o for o in concave_json["objs"] if o.get("name") == "lens_1")
            assert lens["focalLength"] < 0

            rev_camera = await conn.fetchrow(
                "select native_data from experiment_revisions where id = $1", exp_camera.base_revision
            )
            camera_json = json.loads(rev_camera["native_data"])
            assert any(o.get("name") == "sensor_1" for o in camera_json["objs"])

            # 4. 负向测试：传入未适配或不存在的模板 ID，坚决报 TemplateNotFound，绝不静默回退
            with pytest.raises(TemplateNotFound):
                await service.create_from_template(owner_id=owner_id, template_id="optics.two_mirrors")

            with pytest.raises(TemplateNotFound):
                await service.create_from_template(owner_id=owner_id, template_id="images-formed-by-two-mirrors")
        finally:
            await conn.close()
            stop = getattr(srv, "stop", None)
            if callable(stop):
                stop()

    asyncio.run(go())


def test_tool_service_dynamic_search_and_experiment_open():
    """工具服务 search_experiments 动态呈现全部 3 套模板，且支持打开并调参。"""
    async def go():
        mock_engine = AsyncMock(spec=EngineClient)
        # mock apply 返回自洽 native
        async def fake_apply(native, edits):
            import copy
            patched = copy.deepcopy(native)
            for e in edits:
                if e.get("entity_id") == "lens_1" and e.get("parameter") == "focal_length_cm":
                    for o in patched.get("objs", []):
                        if o.get("name") == "lens_1":
                            o["focalLength"] = float(e["value"]) * 10
            return {
                "validation": {"ok": True, "version": 5, "objs": patched.get("objs", [])},
                "base_untouched": True,
                "native": patched,
                "measurement": {"processedRayCount": 1855, "probes": []},
            }
        mock_engine.apply.side_effect = fake_apply

        srv = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-test-c6-tools-"), cleanup_mode=None)
        conn = await asyncpg.connect(srv.get_uri())
        try:
            from eduforge.infrastructure.db.migrations import apply_migrations
            await apply_migrations(conn)

            owner_id = "teacher_user"
            exp_id, rev_id = uuid.uuid4(), uuid.uuid4()
            job_id = uuid.uuid4()
            token = uuid.uuid4().hex

            await conn.execute(
                "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1, $2, 'optics.concave_lens', $3)",
                exp_id, owner_id, rev_id,
            )
            await conn.execute(
                "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1, $2, 'ray_optics', $3::jsonb)",
                rev_id, exp_id, json.dumps(load_native("optics.concave_lens")),
            )
            await conn.execute(
                """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                                     idempotency_key, request_hash, lease_token, lease_until)
                   values ($1, $2, $3, $4, '把焦距改成 -15cm 并打开记录表', 'running', $1, 'h', $5, now() + interval '600 seconds')""",
                job_id, owner_id, exp_id, rev_id, token,
            )

            job = JobContext(job_id=job_id, owner_id=owner_id, experiment_id=exp_id, base_revision=rev_id, lease_token=token)
            tool_service = ExperimentToolService(engine_client=mock_engine, conn=conn, job=job)

            # 1. 动态检索全部实验
            search_res = await tool_service.search_experiments(SearchExperimentsInput(query=""))
            found_ids = {it.template_id for it in search_res.items}
            assert "optics.convex_lens" in found_ids
            assert "optics.concave_lens" in found_ids
            assert "optics.camera_principle" in found_ids

            # 2. 打开凹透镜实验
            open_res = await tool_service.open_experiment(
                OpenExperimentInput(experiment_id=str(exp_id), template_id="optics.concave_lens")
            )
            assert open_res.experiment_id == str(exp_id)

            # 3. 调参：将焦距由 -10 改为 -15cm
            patch_res = await tool_service.apply_scene_patch(
                ApplyScenePatchInput(
                    experiment_id=str(exp_id),
                    edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": -15.0}],
                )
            )
            assert patch_res.status == "applied"
            assert patch_res.updated_parameters["focal_length_cm"] == -15.0

            # 4. 配置教学视图：开启 measurement_table
            view_res = await tool_service.configure_teaching_views(
                ConfigureTeachingViewsInput(
                    experiment_id=str(exp_id),
                    views={"measurement_table": True},
                )
            )
            tbl = view_res.measurement_table
            assert tbl is not None
            records = tbl.get("records", [])
            assert len(records) > 0
            # 记录中正确标注虚像
            assert records[0]["image_kind"] == "正立缩小虚像 (virtual)"
            assert records[0]["focal_length_cm"] == -15.0
        finally:
            await conn.close()
            stop = getattr(srv, "stop", None)
            if callable(stop):
                stop()

    asyncio.run(go())
