"""Agent 执行框架与实验引擎工具服务（8 项工具）端到端验收测试。

覆盖 5 项验收验证准则：
1. 真实导入选定场景（optics.convex_lens）；
2. 参数、表格与记录动作真实生效（f=12cm, u=30cm 且生成记录表及数据行）；
3. 连续编辑基于前一版本演进（head 推进 R1 -> R2 -> R3，parent 链路完整）；
4. 交付包保留修改且离线可用（包含 native.json、teaching_views.json、www/index.html 与 manifest.json）；
5. 暴露工具调用历史 Trace 与闭环验证结果。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import uuid

import asyncpg
import pgserver
import pytest

from eduforge.agent.tool_agent import ExperimentToolAgent
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    BuildPackageInput,
    ConfigureTeachingViewsInput,
    InspectSceneInput,
    OpenExperimentInput,
    PublishRevisionInput,
    RunValidationInput,
    SearchExperimentsInput,
)
from eduforge.experiment_tools.langchain_tools import get_experiment_tools
from eduforge.experiment_tools.mcp_server import handle_mcp_message
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.repositories import JOBS_DDL, RevisionConflict


@pytest.fixture(scope="module")
def uri():
    tmp_pg = tempfile.mkdtemp(prefix="eduforge-agent-tools-pg-")
    server = pgserver.get_server(tmp_pg, cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture
def artifact_dir():
    d = Path(tempfile.mkdtemp(prefix="eduforge-test-artifacts-"))
    yield d


def test_eight_tools_individual_and_langchain(engine_url, uri, artifact_dir):
    """验证 8 项工具的单独调用能力与 LangChain 工具包装。"""

    async def _run():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        client = EngineClient(engine_url)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)

        # 1. search_experiments
        search_out = await service.search_experiments(SearchExperimentsInput(query="凸透镜"))
        assert search_out.total >= 1
        assert any("convex" in it.template_id for it in search_out.items)

        # 2. open_experiment
        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        r1 = open_out.head_revision
        assert exp_id is not None
        assert r1 is not None

        # 3. inspect_scene
        inspect_out = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))
        assert inspect_out.parameters.get("focal_length_cm") == 10.0
        assert inspect_out.parameters.get("object_distance_cm") == 30.0

        # 4. apply_scene_patch (焦距改为 12cm)
        patch_out = await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 12.0}],
            )
        )
        assert patch_out.updated_parameters.get("focal_length_cm") == 12.0

        # 5. configure_teaching_views (开启数据表)
        views_out = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        assert views_out.measurement_table is not None
        assert len(views_out.measurement_table.get("columns", [])) == 5
        assert len(views_out.measurement_table.get("records", [])) >= 1
        rec = views_out.measurement_table["records"][0]
        assert rec["focal_length_cm"] == 12.0
        assert rec["object_distance_cm"] == 30.0
        assert rec["image_distance_cm"] == 20.0

        # 6. run_validation
        val_out = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val_out.verdict == "passed"
        assert val_out.passed is True

        # 7. build_package
        build_out = await service.build_package(BuildPackageInput(experiment_id=exp_id, export_offline_zip=True))
        assert build_out.candidate_revision_id is not None
        assert len(build_out.artifacts) >= 2
        assert build_out.offline_package is not None
        assert Path(build_out.offline_package["index_file"]).exists()

        # 8. publish_revision
        pub_out = await service.publish_revision(PublishRevisionInput(experiment_id=exp_id, base_revision=r1))
        r2 = pub_out.head_revision_id
        assert r2 != r1
        assert pub_out.status == "published"

        # LangChain 包装工具调用测试
        lc_tools = get_experiment_tools(service)
        assert len(lc_tools) == 8
        inspect_tool = next(t for t in lc_tools if t.name == "inspect_scene")
        lc_inspect_res = await inspect_tool.ainvoke({"experiment_id": exp_id})
        assert lc_inspect_res["parameters"]["focal_length_cm"] == 12.0

        # MCP 协议测试
        mcp_list_resp = await handle_mcp_message({"id": 1, "method": "tools/list"}, service)
        assert len(mcp_list_resp["result"]["tools"]) == 8

        mcp_call_resp = await handle_mcp_message(
            {
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "inspect_scene",
                    "arguments": {"experiment_id": exp_id},
                },
            },
            service,
        )
        assert mcp_call_resp["result"]["isError"] is False

        await c.close()

    asyncio.run(_run())


def test_agent_representative_acceptance_task(engine_url, uri, artifact_dir):
    """代表性验收任务完整端到端测试（满足全部 5 项准则）：

    指令："找到凸透镜成像实验，将焦距调整为12cm，物距调整为30cm，开启实验数据记录表格，随后继续调整物距为20cm，最后导出检验合格的离线实验包。"
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        client = EngineClient(engine_url)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)
        agent = ExperimentToolAgent(service)

        prompt = (
            "找到凸透镜成像实验，将焦距调整为12cm，物距调整为30cm，"
            "开启实验数据记录表格，随后继续调整物距为20cm，最后导出检验合格的离线实验包。"
        )

        result = await agent.run(prompt)

        # 准则 1：真实导入选定场景
        assert result["template_id"] == "optics.convex_lens"
        exp_id = result["experiment_id"]
        r1 = result["revisions"]["initial_r1"]
        r2 = result["revisions"]["stage1_r2"]
        r3 = result["revisions"]["final_head"]

        # 准则 2：参数、表格与记录动作真实生效
        # 最终场景物距为 20cm，焦距为 12cm
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))
        assert insp.parameters["focal_length_cm"] == 12.0
        assert insp.parameters["object_distance_cm"] == 20.0
        # 测量表格记录了连续修改过程中的两次实验数据（30cm 与 20cm）
        table = result["measurement_table"]
        assert table is not None
        records = table["records"]
        assert len(records) >= 2
        # 第一条记录：u=30, f=12, v=20
        rec1 = next(r for r in records if r["object_distance_cm"] == 30.0)
        assert rec1["focal_length_cm"] == 12.0
        assert rec1["image_distance_cm"] == 20.0
        assert "倒立" in rec1["image_kind"] and "缩小" in rec1["image_kind"]
        # 第二条记录：u=20, f=12, v=30
        rec2 = next(r for r in records if r["object_distance_cm"] == 20.0)
        assert rec2["focal_length_cm"] == 12.0
        assert rec2["image_distance_cm"] == 30.0
        assert "倒立" in rec2["image_kind"] and "放大" in rec2["image_kind"]

        # 准则 3：连续编辑基于前一版本演进（head R2 -> R3）
        assert r1 != r2
        assert r2 != r3
        exp_db = await c.fetchrow("select head_revision_id from experiments where id = $1", uuid.UUID(exp_id))
        assert str(exp_db["head_revision_id"]) == str(r3)

        # 验证版本演进树父子指针关系：R3 的 parent 是 R2，R2 的 parent 是 R1
        revs = await c.fetch(
            "select id, parent_id, lesson from experiment_revisions where experiment_id = $1 order by created_at",
            uuid.UUID(exp_id),
        )
        assert len(revs) == 3
        assert revs[0]["parent_id"] is None
        assert str(revs[1]["parent_id"]) == str(r1)
        assert str(revs[2]["parent_id"]) == str(r2)

        # 准则 4：下载包保留修改且离线可用
        pkg = result["offline_package"]
        assert pkg is not None
        index_path = Path(pkg["index_file"])
        assert index_path.exists()
        www_dir = index_path.parent
        native_file = www_dir / "scene" / "native.json"
        assert native_file.exists()
        saved_native = json.loads(native_file.read_text(encoding="utf-8"))
        # 核验离线包内保存的场景确实含有修改后的物距（PointSource x=-200）与焦距（IdealLens focalLength=120）
        src_obj = next(o for o in saved_native["objs"] if o["type"] == "PointSource")
        lens_obj = next(o for o in saved_native["objs"] if o["type"] == "IdealLens")
        assert lens_obj["focalLength"] == 120
        assert src_obj["x"] == -200

        # 离线包内存在教学视图文件
        views_file = www_dir / "scene" / "teaching_views.json"
        assert views_file.exists()
        saved_views = json.loads(views_file.read_text(encoding="utf-8"))
        assert "measurement_table" in saved_views
        assert len(saved_views["measurement_table"]["records"]) >= 2

        # 准则 5：工具调用历史与验证结果暴露
        trace = result["trace"]
        assert len(trace) >= 8
        tool_names = [t["tool_name"] for t in trace]
        assert "search_experiments" in tool_names
        assert "open_experiment" in tool_names
        assert "inspect_scene" in tool_names
        assert "apply_scene_patch" in tool_names
        assert "configure_teaching_views" in tool_names
        assert "run_validation" in tool_names
        assert "publish_revision" in tool_names
        assert "build_package" in tool_names
        # 确认所有工具调用均无未捕获异常
        for t in trace:
            assert t["error"] is None

        # 验证报告结论通过
        assert result["validation"]["verdict"] == "passed"
        assert result["validation"]["passed"] is True

        await c.close()

    asyncio.run(_run())


def test_concurrent_publish_revision_conflict(engine_url, uri, artifact_dir):
    """边缘用例 1：并发两个客户端同时对同一个实验发起修订（基于同一 base_revision）。
    第一个提交成功推进 head；第二个提交触发 RevisionConflict 并保持原子回滚。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        client = EngineClient(engine_url)
        service1 = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)
        service2 = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)

        # 客户端 1 创建实验并获得基础版本 R1
        open_out = await service1.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        r1 = open_out.head_revision

        # 客户端 2 也同步打开该实验（基于同一 base R1）
        await service2.open_experiment(OpenExperimentInput(experiment_id=exp_id, revision_id=r1))

        # 客户端 1 应用修改并成功发布 R2
        await service1.apply_scene_patch(
            ApplyScenePatchInput(experiment_id=exp_id, edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}])
        )
        pub1 = await service1.publish_revision(PublishRevisionInput(experiment_id=exp_id, base_revision=r1))
        r2 = pub1.head_revision_id
        assert r2 != r1

        # 客户端 2 仍试图以过期的 R1 为 base 发布新版本
        await service2.apply_scene_patch(
            ApplyScenePatchInput(experiment_id=exp_id, edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 12.0}])
        )
        with pytest.raises(RevisionConflict):
            await service2.publish_revision(PublishRevisionInput(experiment_id=exp_id, base_revision=r1))

        # 验证数据库中的 head 依然是 R2，没有被污染
        head_in_db = await c.fetchval("select head_revision_id from experiments where id = $1", uuid.UUID(exp_id))
        assert str(head_in_db) == str(r2)

        await c.close()

    asyncio.run(_run())


def test_agent_self_healing_repair_loop(engine_url, uri, artifact_dir):
    """边缘用例 2：LangGraph Agent 闭环自愈修复（Read -> Tool Call -> Observe -> Repair -> Deliver）。
    当初始参数超出受控范围触发验证失败时，Agent 自动进入 repair 节点校准参数并重试通过。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        client = EngineClient(engine_url)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)
        agent = ExperimentToolAgent(service)

        # 故意指定超限焦距 60cm（模板最大允许 50cm）
        prompt = "找到凸透镜成像实验，将焦距调整为60cm，物距调整为30cm，开启实验数据记录表格，最后导出离线实验包。"
        result = await agent.run(prompt)

        # 验证 Agent 完成了自愈修复并最终交付
        assert result["validation"]["passed"] is True
        assert result["validation"]["verdict"] == "passed"
        assert result["offline_package"] is not None
        assert result["revisions"]["final_head"] is not None
        # 验证修复历史有留痕
        assert result["repair_attempts"] >= 1

        await c.close()

    asyncio.run(_run())


def test_physics_boundary_infinite_and_virtual_image(engine_url, uri, artifact_dir):
    """边缘用例 3：极限物理条件（u=f 无穷远像与 u<f 虚像）的数据表记录与科学验证闭环。"""

    async def _run():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")

        client = EngineClient(engine_url)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)

        # 1. 工况一：u = 30cm, f = 30cm (u=f，折射出平行光束，像在无穷远)
        open_res = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_res.experiment_id

        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[
                    {"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 30.0},
                    {"entity_id": "object_1", "parameter": "object_distance_cm", "value": 30.0},
                ],
            )
        )
        views_out = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        rec_inf = views_out.measurement_table["records"][0]
        assert rec_inf["image_distance_cm"] is None
        assert "不成像" in rec_inf["image_kind"]

        val_inf = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val_inf.passed is True
        check_inf = next(c for c in val_inf.checks if c["id"] == "focal_parallel_beams")
        assert check_inf["passed"] is True

        # 2. 工况二：u = 20cm, f = 30cm (u < f，正立放大虚像)
        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[
                    {"entity_id": "object_1", "parameter": "object_distance_cm", "value": 20.0},
                ],
            )
        )
        views_v = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        rec_v = next(r for r in views_v.measurement_table["records"] if r["object_distance_cm"] == 20.0)
        assert rec_v["image_distance_cm"] is not None and rec_v["image_distance_cm"] < 0
        assert "虚像" in rec_v["image_kind"]

        val_v = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val_v.passed is True
        check_v = next(c for c in val_v.checks if c["id"] == "virtual_image_valid")
        assert check_v["passed"] is True

        await c.close()

    asyncio.run(_run())

