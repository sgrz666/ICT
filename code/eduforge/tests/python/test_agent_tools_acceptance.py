"""实验引擎工具服务（8 项工具）端到端验收测试。

覆盖 5 项验收验证准则：
1. 真实导入选定场景（optics.convex_lens）；
2. 参数、表格与记录动作真实生效（f=12cm, u=30cm 且生成记录表及数据行）；
3. 连续编辑基于前一版本演进（head 推进 R1 -> R2 -> R3，parent 链路完整）；
4. 交付包保留修改且离线可用（包含 native.json、teaching_views.json、www/index.html 与 manifest.json）；
5. 暴露工具调用历史 Trace 与闭环验证结果。

工具层的每一次落库都必须带服务端签发的 JobContext（归属/job/租约三者）；
准则 5 的智能体层部分随 Deep Agents 运行时移到了 `test_deepagents_runtime.py`，
旧的规则式 `ExperimentToolAgent` 已删除（它的「自愈」靠伪造验证记录）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import uuid

import asyncpg
import pgserver
import pytest

from eduforge.agent.policy import Rejected
from eduforge.domain.errors import ConflictError
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    BuildPackageInput,
    ConfigureTeachingViewsInput,
    InspectSceneInput,
    JobContext,
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


async def _reset(c):
    await c.execute(JOBS_DDL)
    for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
        await c.execute(f"delete from {t}")


async def _bind_job(c, *, owner: str = "teacher-a") -> JobContext:
    """在服务端造一个持有租约的 running job，并把执行上下文交给工具服务。

    发布走的是持久层那条四道闸门事务，没有这条 job 行就没有执行权。
    """
    job_id = uuid.uuid4()
    lease_token = uuid.uuid4().hex
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                             idempotency_key, request_hash, lease_token, lease_until)
           values ($1,$2,$3,$4,'验收任务','running',$1,$5,$6, now() + interval '300 seconds')""",
        job_id, owner, uuid.uuid4(), uuid.uuid4(), "acceptance-hash", lease_token,
    )
    return JobContext(job_id=job_id, owner_id=owner, lease_token=lease_token)


def test_eight_tools_individual_and_langchain(engine_url, uri, artifact_dir):
    """验证 8 项工具的单独调用能力与 LangChain 工具包装。"""

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

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

        # 发布必须留下可追溯的验证报告行（工具路径以前完全不写这张表）
        verdicts = await c.fetch(
            "select verdict from validation_reports where job_id = $1", job.job_id
        )
        assert len(verdicts) >= 1 and all(v["verdict"] == "passed" for v in verdicts)

        # 交付字节与登记必须对得上：产物行存在、哈希与磁盘文件一致
        db_arts = await c.fetch(
            "select storage_key, sha256 from artifacts where revision_id = $1", uuid.UUID(r2)
        )
        assert len(db_arts) == len(build_out.artifacts)
        for row in db_arts:
            on_disk = artifact_dir / row["storage_key"]
            assert on_disk.is_file()
            assert hashlib.sha256(on_disk.read_bytes()).hexdigest() == row["sha256"]
        offline_manifest = next(
            (a for a in build_out.artifacts if a["storage_key"].endswith("manifest.json")), None
        )
        assert offline_manifest is not None, "离线包整包必须有 manifest 才能复核交付字节"

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


def test_continuous_edit_acceptance_chain(engine_url, uri, artifact_dir):
    """连续编辑验收链（准则 1-4）：一个 job 内两轮「改场景 → 配视图 → 验证 → 构建 → 发布」。

    顺序刻意是先构建、核验交付包、再原子发布——旧的 ExperimentToolAgent 是先发布、
    最后才构建，那份最终候选的产物行从不入库（发布事务里才登记），交付出去的
    revision id 在库里不存在。智能体自主决策的部分由 `test_deepagents_runtime.py` 承接。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        r1 = open_out.head_revision
        assert open_out.template_id == "optics.convex_lens"

        # 第一轮：f=12cm、u=30cm、开数据记录表
        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[
                    {"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 12.0},
                    {"entity_id": "object_1", "parameter": "object_distance_cm", "value": 30.0},
                ],
            )
        )
        views1 = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        val1 = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val1.passed is True
        build1 = await service.build_package(BuildPackageInput(experiment_id=exp_id))
        pub1 = await service.publish_revision(
            PublishRevisionInput(experiment_id=exp_id, base_revision=r1), close_job=False
        )
        r2 = pub1.head_revision_id

        # 第二轮：以 R2 为基础继续把物距调到 20cm
        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[{"entity_id": "object_1", "parameter": "object_distance_cm", "value": 20.0}],
            )
        )
        views2 = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        val2 = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val2.passed is True
        build2 = await service.build_package(BuildPackageInput(experiment_id=exp_id))
        pub2 = await service.publish_revision(
            PublishRevisionInput(experiment_id=exp_id, base_revision=r2), close_job=True
        )
        r3 = pub2.head_revision_id

        # 准则 2：参数与记录动作真实生效
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))
        assert insp.parameters["focal_length_cm"] == 12.0
        assert insp.parameters["object_distance_cm"] == 20.0
        records = views2.measurement_table["records"]
        assert len(records) >= 2
        rec1 = next(r for r in records if r["object_distance_cm"] == 30.0)
        assert rec1["focal_length_cm"] == 12.0 and rec1["image_distance_cm"] == 20.0
        assert "倒立" in rec1["image_kind"] and "缩小" in rec1["image_kind"]
        rec2 = next(r for r in records if r["object_distance_cm"] == 20.0)
        assert rec2["focal_length_cm"] == 12.0 and rec2["image_distance_cm"] == 30.0
        assert "倒立" in rec2["image_kind"] and "放大" in rec2["image_kind"]
        assert views1.measurement_table is not None

        # 准则 3：head R1 -> R2 -> R3，parent 链路完整
        assert r1 != r2 != r3
        exp_db = await c.fetchrow("select head_revision_id from experiments where id = $1", uuid.UUID(exp_id))
        assert str(exp_db["head_revision_id"]) == str(r3)
        revs = await c.fetch(
            "select id, parent_id from experiment_revisions where experiment_id = $1 order by created_at",
            uuid.UUID(exp_id),
        )
        assert len(revs) == 3
        assert revs[0]["parent_id"] is None
        assert str(revs[1]["parent_id"]) == str(r1)
        assert str(revs[2]["parent_id"]) == str(r2)

        # 交付包登记的版本必须真的存在于版本表——旧路径的最后一公里会指向一个不存在的 id
        for cand in (build1.candidate_revision_id, build2.candidate_revision_id):
            assert await c.fetchval(
                "select 1 from experiment_revisions where id = $1", uuid.UUID(cand)
            ) == 1

        # job 终态：只有最后一次发布把 job 收成 succeeded
        job_status = await c.fetchval("select status from jobs where id = $1", job.job_id)
        assert job_status == "succeeded"

        # 准则 4：离线包保留改动后的字节
        pkg = build2.offline_package
        assert pkg is not None and pkg["index_present"] is True
        index_path = Path(pkg["index_file"])
        www_dir = index_path.parent
        saved_native = json.loads((www_dir / "scene" / "native.json").read_text(encoding="utf-8"))
        src_obj = next(o for o in saved_native["objs"] if o["type"] == "PointSource")
        lens_obj = next(o for o in saved_native["objs"] if o["type"] == "IdealLens")
        assert lens_obj["focalLength"] == 120
        assert src_obj["x"] == -200
        saved_views = json.loads((www_dir / "scene" / "teaching_views.json").read_text(encoding="utf-8"))
        assert "measurement_table" in saved_views
        assert len(saved_views["measurement_table"]["records"]) >= 2
        # manifest 必须逐条对上磁盘字节
        manifest = json.loads((Path(pkg["dir"]) / "manifest.json").read_text(encoding="utf-8"))
        for entry in manifest:
            f = Path(pkg["dir"]) / entry["path"]
            assert f.is_file(), f"manifest 里列出的文件不在盘上: {entry['path']}"
            assert hashlib.sha256(f.read_bytes()).hexdigest() == entry["sha256"]

        await c.close()

    asyncio.run(_run())


def test_concurrent_publish_revision_conflict(engine_url, uri, artifact_dir):
    """边缘用例 1：并发两个客户端同时对同一个实验发起修订（基于同一 base_revision）。
    第一个提交成功推进 head；第二个提交触发 RevisionConflict 并保持原子回滚。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        # 两个客户端各自持有服务端签发的 job 与租约，归属同一教师身份
        job1 = await _bind_job(c, owner="teacher-a")
        job2 = await _bind_job(c, owner="teacher-a")
        service1 = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job1)
        service2 = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job2)

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


def test_out_of_range_patch_is_refused_not_silently_substituted(engine_url, uri, artifact_dir):
    """教师要 60cm（模板上限 50cm）必须失败并如实上报。

    这里原来测的是相反的东西：`ExperimentToolAgent` 伪造一条 `expected=50.0` 的
    验证记录，再硬编码回填 clamp 后的值，最后报 `passed`——当着教师的面换了参数
    还宣称完成。伪造的自愈没有资格当验收准则，所以这条测试改写成守住「不许撒谎」。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        r1 = open_out.head_revision
        revs_before = await c.fetchval("select count(*) from experiment_revisions")

        with pytest.raises(Rejected):
            await service.apply_scene_patch(
                ApplyScenePatchInput(
                    experiment_id=exp_id,
                    edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 60.0}],
                )
            )

        # 拒绝之后：场景没被偷偷改动，head 没前进，也没有多出一个「已交付」的版本
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))
        assert insp.parameters["focal_length_cm"] != 60.0
        head = await c.fetchval("select head_revision_id from experiments where id = $1", uuid.UUID(exp_id))
        assert str(head) == str(r1)
        assert await c.fetchval("select count(*) from experiment_revisions") == revs_before

        await c.close()

    asyncio.run(_run())


def test_policy_refuses_unregistered_entity_and_view(engine_url, uri, artifact_dir):
    """工具层现在必须过策略清单：未登记的对象/参数/视图在碰到引擎之前就被拒。

    以前 8 项工具完全不 import `agent/policy.py`，等于给模型一把不经登记的写钥匙；
    正则代理不会主动试，真实模型一定会试。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id

        with pytest.raises(Rejected) as ent:
            await service.apply_scene_patch(
                ApplyScenePatchInput(
                    experiment_id=exp_id,
                    edits=[{"entity_id": "lens_99", "parameter": "focal_length_cm", "value": 15.0}],
                )
            )
        assert ent.value.code == "PARAMETER_NOT_REGISTERED"

        with pytest.raises(Rejected) as view:
            await service.configure_teaching_views(
                ConfigureTeachingViewsInput(experiment_id=exp_id, views={"ghost_view": True})
            )
        assert view.value.code == "VIEW_NOT_REGISTERED"

        # 两次拒绝都没有改动场景；登记过的视图仍能正常开启（拒的是越界，不是功能）
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))
        assert insp.parameters["focal_length_cm"] == 10.0
        ok_views = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=exp_id, views={"measurement_table": True})
        )
        assert ok_views.measurement_table is not None
        await c.close()

    asyncio.run(_run())


def test_stale_validation_triggers_revalidation_before_publish(engine_url, uri, artifact_dir):
    """验过之后再合法改动内容，发布前必须重新验证——旧绿灯不作数。

    旧实现只在「报告不存在」时补验，而报告从不失效，于是
    改内容 → 沿用旧绿灯 → 发布 能一路通过。现在报告绑定内容指纹。
    """

    async def _reports(c, job_id):
        return await c.fetchval("select count(*) from validation_reports where job_id = $1", job_id)

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        r1 = open_out.head_revision

        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}],
            )
        )
        val = await service.run_validation(RunValidationInput(experiment_id=exp_id))
        assert val.passed is True, "前置条件：这一步必须先真的验过"
        after_first = await _reports(c, job.job_id)
        assert after_first == 1, "run_validation 必须当场把结论落库"

        # 合法改动（清单内、量程内），但内容指纹变了
        await service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[{"entity_id": "object_1", "parameter": "object_distance_cm", "value": 25.0}],
            )
        )
        await service.publish_revision(PublishRevisionInput(experiment_id=exp_id, base_revision=r1))

        # 发布前重新验证过一次，而不是沿用了改动前的绿灯
        assert await _reports(c, job.job_id) == after_first + 1

        # 发布的必须是改动后的那份内容
        head = await c.fetchval("select head_revision_id from experiments where id = $1", uuid.UUID(exp_id))
        stored = json.loads(await c.fetchval(
            "select native_data::text from experiment_revisions where id = $1", head
        ))
        lens = next(o for o in stored["objs"] if o["type"] == "IdealLens")
        src = next(o for o in stored["objs"] if o["type"] == "PointSource")
        assert lens["focalLength"] == 150 and src["x"] == -250

        await c.close()

    asyncio.run(_run())


def test_publish_refuses_without_execution_context(engine_url, uri, artifact_dir):
    """没有服务端执行上下文、或没有库连接时，发布不得回报成功。

    旧代码在 `conn=None` 时整段事务被跳过，却仍返回 `status="published"`；
    数据库里什么都没发生，调用方以为发布完了。
    """

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)

        # 场景一：完全没有 JobContext
        naked = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir)
        with pytest.raises(ConflictError):
            await naked.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))

        # 场景二：有身份上下文但没有库连接——落不了库就不许说「已发布」
        offline_service = ExperimentToolService(engine_client=client, conn=None, artifact_dir=artifact_dir, job=job)
        open_out = await offline_service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        exp_id = open_out.experiment_id
        await offline_service.apply_scene_patch(
            ApplyScenePatchInput(
                experiment_id=exp_id,
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}],
            )
        )
        with pytest.raises(ConflictError):
            await offline_service.publish_revision(PublishRevisionInput(experiment_id=exp_id))
        assert await c.fetchval("select count(*) from experiment_revisions") == 0

        await c.close()

    asyncio.run(_run())


def test_physics_boundary_infinite_and_virtual_image(engine_url, uri, artifact_dir):
    """边缘用例 3：极限物理条件（u=f 无穷远像与 u<f 虚像）的数据表记录与科学验证闭环。"""

    async def _run():
        c = await asyncpg.connect(uri)
        await _reset(c)

        client = EngineClient(engine_url)
        job = await _bind_job(c)
        service = ExperimentToolService(engine_client=client, conn=c, artifact_dir=artifact_dir, job=job)

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

