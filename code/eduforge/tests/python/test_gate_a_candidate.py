"""Gate A 的验收：模型改过的那份候选，就是验证、构建、发布与下载的那一份。

这些用例钉的是同一句话的不同侧面：

1. `experiment_candidates` 迁移在**旧库**上也能把新列/新表补出来；
2. 未发布工作态活在库里，换一个进程（新建 service）读得回来；
3. 先改 A 再改 B 只能交付 B，A 那份验证当场不作数；
4. 同一个 job 重试不产生第二个候选、不重复登记产物；
5. 跨实验/跨版本串写被拒，并发覆盖被 CAS 挡下；
6. 纯视图任务（只打开记录表）真实跑通，不被误判为基线被改；
7. 脚本模型走 Worker 全链，最终发布的字节 = 候选字节 = 下载字节。

假模型只证明**工程正确性**（链路、门禁、崩溃可恢复），不构成任何模型能力证据；
真实模型的自主能力仍由 `test_deepagents_real_model.py` 负责（无 key 时 SKIPPED）。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

import asyncpg
import pgserver
import pytest

from eduforge.application.candidate_service import (
    CandidateFrozen,
    content_fingerprint,
    native_bytes,
    views_bytes,
)
from eduforge.infrastructure.db.candidate_repository import (
    CandidateRepository,
    CandidateVersionConflict,
)
from eduforge.domain.contracts import EditProposal, SetParameter, SetView
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
)
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.catalog import load_native
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.migrations import apply_migrations, current_version
from eduforge.infrastructure.db.repositories import (
        candidate_id_for,
    revision_id_for,
)

TABLES = (
    "experiment_candidates", "artifacts", "validation_reports", "job_events",
    "jobs", "experiment_revisions", "experiments",
)

OWNER = "teacher-gate-a"


@pytest.fixture(scope="module")
def uri():
    server = pgserver.get_server(tempfile.mkdtemp(prefix="eduforge-gateA-"), cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture
def art_dir():
    return Path(tempfile.mkdtemp(prefix="eduforge-gateA-art-"))


async def _schema(c):
    await apply_migrations(c)
    for t in TABLES:
        await c.execute(f"delete from {t}")


async def _seed_experiment(c, *, owner: str = OWNER) -> tuple[uuid.UUID, uuid.UUID]:
    exp_id, rev_id = uuid.uuid4(), uuid.uuid4()
    await c.execute(
        "insert into experiments (id, owner_id, template_id, head_revision_id) values ($1,$2,'optics.convex_lens',$3)",
        exp_id, owner, rev_id,
    )
    await c.execute(
        "insert into experiment_revisions (id, experiment_id, engine_id, native_data) values ($1,$2,'ray_optics',$3::jsonb)",
        rev_id, exp_id, json.dumps(load_native("optics.convex_lens")),
    )
    return exp_id, rev_id


async def _seed_job(c, *, exp_id: uuid.UUID, base_rev: uuid.UUID, owner: str = OWNER,
                    lease_token: str | None = None) -> tuple[uuid.UUID, str]:
    job_id = uuid.uuid4()
    token = lease_token or uuid.uuid4().hex
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                             idempotency_key, request_hash, lease_token, lease_until)
           values ($1,$2,$3,$4,'把焦距改成 15cm 并打开记录表','running',$1,'h',$5, now() + interval '600 seconds')""",
        job_id, owner, exp_id, base_rev, token,
    )
    return job_id, token


def _service(c, job: JobContext, art_dir: Path, engine_url: str) -> ExperimentToolService:
    return ExperimentToolService(
        engine_client=EngineClient(engine_url), conn=c, artifact_dir=art_dir, job=job,
    )


def test_migration_runs_on_old_database_and_is_idempotent(uri):
    """旧库（只有 JOBS_DDL）也能被推到最新版本；重复应用不重复执行。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await c.execute("drop table if exists schema_migrations")
            for t in TABLES:
                await c.execute(f"drop table if exists {t} cascade")
            await apply_migrations(c)  # 模拟 Gate A 之前的库
            await c.execute("drop table if exists schema_migrations")
            applied = await apply_migrations(c)
            assert 3 in applied, applied
            names = {r["tablename"] for r in await c.fetch(
                "select tablename from pg_tables where schemaname='public'")}
            assert "experiment_candidates" in names
            assert await current_version(c) == 3
            assert await apply_migrations(c) == [], "已应用的迁移被重复执行"
        finally:
            await c.close()

    asyncio.run(go())


def test_candidate_table_binds_one_row_per_job(uri, art_dir, engine_url):
    """候选主键就是 job：同一个任务永远只有一行工作态。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            service = _service(c, JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                                             experiment_id=exp_id, base_revision=base_rev), art_dir, engine_url)
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            rows = await c.fetch("select job_id, candidate_id from experiment_candidates")
            assert len(rows) == 1, rows
            assert rows[0]["candidate_id"] == candidate_id_for(job_id)
            assert await c.fetchval("select state_version from experiment_candidates") == 1
        finally:
            await c.close()

    asyncio.run(go())


def test_unpublished_candidate_is_readable_after_process_restart(uri, art_dir, engine_url):
    """换一个 service 实例（等价于进程重启）必须读回同一份未发布内容。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            job = JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                             experiment_id=exp_id, base_revision=base_rev)
            first = _service(c, job, art_dir, engine_url)
            await first.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await first.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))

            second = _service(c, job, art_dir, engine_url)  # 新实例 = 空缓存
            insp = await second.inspect_scene(InspectSceneInput(experiment_id=str(exp_id)))
            assert insp.parameters["focal_length_cm"] == 15.0, insp.parameters

            row = await c.fetchrow("select native_data, content_hash from experiment_candidates")
            assert content_fingerprint(json.loads(row["native_data"]), {}) == row["content_hash"]
        finally:
            await c.close()

    asyncio.run(go())


def test_edit_a_then_b_only_delivers_b(uri, art_dir, engine_url):
    """验过 A 之后又改成 B：A 的绿灯作废，构建与发布只能落在 B 的内容哈希上。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            service = _service(c, JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                                             experiment_id=exp_id, base_revision=base_rev), art_dir, engine_url)
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))

            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 12.0}]))
            val_a = await service.run_validation(RunValidationInput(experiment_id=str(exp_id)))
            assert val_a.passed is True, val_a.checks
            state_a = await c.fetchrow("select content_hash, validation_hash from experiment_candidates")
            assert state_a["validation_hash"] == state_a["content_hash"], "A 验过后报告应绑定"

            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))
            state_b = await c.fetchrow(
                "select content_hash, validation_hash, validation_id from experiment_candidates")
            assert state_b["validation_hash"] is None, "改成 B 之后 A 的绿灯必须清空"
            assert state_b["content_hash"] != state_a["content_hash"]

            built = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            published = await service.publish_revision(PublishRevisionInput(experiment_id=str(exp_id)))
            assert published.head_revision_id == built.candidate_revision_id
            assert built.candidate_revision_id == str(
                revision_id_for(job_id, state_b["content_hash"]))

            rev = await c.fetchrow("select native_data, lesson from experiment_revisions where id=$1",
                                   uuid.UUID(published.head_revision_id))
            scene = json.loads(rev["native_data"]) if isinstance(rev["native_data"], str) else rev["native_data"]
            lens = next(o for o in scene["objs"] if o.get("type") == "IdealLens")
            assert lens["focalLength"] == 150, "发布出去的必须是 B（15cm），不是 A"
            a_hash, b_hash = state_a["content_hash"], state_b["content_hash"]
            assert await c.fetchval(
                "select count(*) from experiment_revisions") == 2, "只有基线与 B 两个版本"
            assert a_hash != b_hash
        finally:
            await c.close()

    asyncio.run(go())


def test_retry_after_build_publishes_once_without_duplicate_candidate(uri, art_dir, engine_url):
    """同一 job 重复构建/发布：候选一行、版本一条、产物登记不翻倍（幂等重放）。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            service = _service(c, JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                                             experiment_id=exp_id, base_revision=base_rev), art_dir, engine_url)
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await service.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))
            first = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            # 重跑一次构建（等价于阶段崩溃后接管者重来）：必须落在同一个候选版本上
            again = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            assert again.candidate_revision_id == first.candidate_revision_id
            assert [a["id"] for a in again.artifacts] == [a["id"] for a in first.artifacts]
            await service.publish_revision(PublishRevisionInput(experiment_id=str(exp_id)))
            assert await c.fetchval("select count(*) from experiment_candidates") == 1
            assert await c.fetchval(
                "select count(*) from artifacts where revision_id=$1",
                uuid.UUID(first.candidate_revision_id)) == len(first.artifacts)
        finally:
            await c.close()

    asyncio.run(go())


def test_opening_another_experiment_for_the_same_job_is_refused(uri, art_dir, engine_url):
    """候选已经绑了实验与基线，就不能被换绑到别的实验或别的版本上。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            other_exp, _other_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            # 故意用未绑定实验的上下文：这样「换绑」只能由候选守卫来拒，
            # 不会被 service 更早的 SCOPE_MISMATCH 顺手挡掉（那条另有用例覆盖）。
            service = _service(c, JobContext(job_id=job_id, owner_id=OWNER, lease_token=token),
                               art_dir, engine_url)
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            with pytest.raises(ConflictError):
                await service.open_experiment(OpenExperimentInput(
                    experiment_id=str(other_exp), template_id="optics.convex_lens"))
            assert await c.fetchval(
                "select base_revision from experiment_candidates") == base_rev
        finally:
            await c.close()

    asyncio.run(go())


def test_stale_writer_is_rejected_by_cas(uri, art_dir, engine_url):
    """两个进程都读到了同一版候选：后写的那个必须失败，而不是静默覆盖。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            job = JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                             experiment_id=exp_id, base_revision=base_rev)
            a = _service(c, job, art_dir, engine_url)
            b = _service(c, job, art_dir, engine_url)
            await a.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await b.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await a.apply_scene_patch(ApplyScenePatchInput(
                experiment_id=str(exp_id),
                edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}]))
            with pytest.raises(ConflictError, match="state_version"):
                await b.apply_scene_patch(ApplyScenePatchInput(
                    experiment_id=str(exp_id),
                    edits=[{"entity_id": "lens_1", "parameter": "focal_length_cm", "value": 20.0}]))
            insp = await a.inspect_scene(InspectSceneInput(experiment_id=str(exp_id)))
            assert insp.parameters["focal_length_cm"] == 15.0
            assert await c.fetchval("select state_version from experiment_candidates") == 1
        finally:
            await c.close()

    asyncio.run(go())


def test_view_only_task_passes_base_untouched(uri, art_dir, engine_url):
    """只开记录表、不动参数：基线字节没变，这道闸门不能因为字段缺失而恒 False。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            job = JobContext(job_id=job_id, owner_id=OWNER, lease_token=token,
                             experiment_id=exp_id, base_revision=base_rev)
            service = _service(c, job, art_dir, engine_url)
            await service.open_experiment(OpenExperimentInput(
                experiment_id=str(exp_id), revision_id=str(base_rev), template_id="optics.convex_lens"))
            await service.configure_teaching_views(ConfigureTeachingViewsInput(
                experiment_id=str(exp_id), views={"measurement_table": True}))
            val = await service.run_validation(RunValidationInput(experiment_id=str(exp_id)))
            assert val.passed is True, val.checks
            built = await service.build_package(BuildPackageInput(
                experiment_id=str(exp_id), export_offline_zip=False))
            views_file = art_dir / "revisions" / built.candidate_revision_id / "teaching_views.json"
            assert views_file.is_file()
            row = await c.fetchrow("select native_data, teaching_views, content_hash from experiment_candidates")
            assert views_file.read_bytes() == views_bytes(json.loads(row["teaching_views"]))
            published = await service.publish_revision(PublishRevisionInput(experiment_id=str(exp_id)))
            assert await c.fetchval(
                "select lesson from experiment_revisions where id=$1",
                uuid.UUID(published.head_revision_id)
            ) is not None
        finally:
            await c.close()

    asyncio.run(go())


def test_agent_candidate_bytes_are_exactly_what_gets_downloaded(uri, art_dir, engine_url):
    """Gate A 的正面结论：脚本模型改出的候选，逐字节等于 API 下载到的那份。

    走的是生产组合根（`make_worker` + `Chain` 五阶段），不是测试里另拼一套。
    """
    from eduforge.agent.deepagents_runner import DeepAgentRunner
    from eduforge.agent.fake_model import ScriptedToolModel
    from eduforge.worker.steps import artifact_path, make_worker

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            # Worker 领取要求任务可领：把种子行改成 queued、租约清空
            await c.execute("update jobs set status='queued', lease_token=NULL, lease_until=NULL")
            runner = DeepAgentRunner(
                conn=c, engine=EngineClient(engine_url), artifact_dir=art_dir,
                model_factory=lambda **kw: ScriptedToolModel(
                    goal={"focal_length_cm": 15.0, "object_distance_cm": 30.0,
                          "view": "measurement_table"}),
                profile="deepagents_scripted",
            )
            worker = make_worker(c, engine_url=engine_url, artifact_dir=art_dir,
                                 planner=runner, lease_seconds=600)
            result = await worker.run_once()
            assert result is not None and "failed" not in result, result

            state = await c.fetchrow(
                "select native_data, teaching_views, content_hash, status from experiment_candidates")
            native = json.loads(state["native_data"])
            views = json.loads(state["teaching_views"])
            assert state["status"] == "published"
            assert content_fingerprint(native, views) == state["content_hash"]

            head = await c.fetchval("select head_revision_id from experiments where id=$1", exp_id)
            assert str(head) == str(revision_id_for(job_id, state["content_hash"]))
            # planning 事件里的候选哈希就是发布出去的候选哈希：同一条 job、同一行候选
            planning = await c.fetchrow(
                "select payload from job_events where job_id=$1 and stage='planning' and event_type='stage_done'",
                job_id)
            assert json.loads(planning["payload"])["content_hash"] == state["content_hash"]
            # 交付字节 = 候选字节（逐字节，而不是「大概是同一份」）
            delivered = artifact_path(art_dir, head).read_bytes()
            assert delivered == native_bytes(native)
            downloaded = await c.fetchval(
                "select sha256 from artifacts where revision_id=$1 order by storage_key", head)
            import hashlib
            assert hashlib.sha256(delivered).hexdigest() == downloaded
            rev_native = await c.fetchval(
                "select native_data::text from experiment_revisions where id=$1", head)
            scene = json.loads(rev_native)
            lens = next(o for o in scene["objs"] if o.get("type") == "IdealLens")
            source = next(o for o in scene["objs"] if o.get("type") == "PointSource")
            lens_x = (float(lens["p1"]["x"]) + float(lens["p2"]["x"])) / 2
            assert float(lens["focalLength"]) / 10 == 15.0, "发布的必须是教师要的 15cm 焦距"
            assert abs(float(source["x"]) - lens_x) / 10 == 30.0, "发布的必须是 30cm 物距"
            lesson = await c.fetchval(
                "select lesson::text from experiment_revisions where id=$1", head)
            views = json.loads(lesson)["views"]
            assert views.get("measurement_table", {}).get("visible") is True, views
            assert content_fingerprint(scene, views) == state["content_hash"], (
                "发布版本的内容必须与候选同一指纹——否则「验证 A 发布 B」又回来了"
            )
        finally:
            await c.close()

    asyncio.run(go())


def test_view_only_task_runs_through_the_worker_chain(uri, art_dir, engine_url):
    """纯视图任务（只打开记录表、不动参数）必须能走完五阶段并发布。

    外部审查文档特别提醒过这一点：以前只用「改参数 + 开表」验证，纯视图那条
    分支会构造一个不含 `base_untouched` 的伪结果，`bool(result.get(...))` 恒 False，
    于是任务被误判为「基线被暗改」。用例因此直接打 Worker 组合根，而不是只打工具层。
    """
    from eduforge.worker.steps import make_worker

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            await c.execute("update jobs set status='queued', lease_token=NULL, lease_until=NULL")
            proposal = EditProposal(
                route="config", operations=[SetView(view_id="measurement_table", visible=True)]
            )
            from eduforge.worker.steps import StaticPlanner

            worker = make_worker(c, engine_url=engine_url, artifact_dir=art_dir,
                                 planner=StaticPlanner(proposal), lease_seconds=600)
            result = await worker.run_once()
            assert "failed" not in result, result
            assert result["last_stage"] == "packaging", result

            editing = await c.fetchrow(
                "select payload from job_events where job_id=$1 and stage='editing' and event_type='stage_done'",
                job_id)
            payload = json.loads(editing["payload"])
            assert payload["base_untouched"] is True, payload
            state = await c.fetchrow("select native_data, teaching_views from experiment_candidates")
            assert json.loads(state["teaching_views"])["measurement_table"]["visible"] is True
            assert json.loads(state["native_data"]) == json.loads(
                await c.fetchval("select native_data::text from experiment_revisions where id=$1", base_rev)
            ), "只开视图不该动场景一个字节"
            assert await c.fetchval("select count(*) from experiment_revisions") == 2
        finally:
            await c.close()

    asyncio.run(go())


def test_two_connections_freeze_and_write_race_rejected(uri):
    """Gate C.0: 双独立连接交错测试。
    Writer 已读到版本 0，另一个事务完成 freeze 后，旧 Writer 再写必须失败，
    且候选状态在库中保持 frozen，绝不可被重新写回 editing 或静默覆盖。
    """

    async def go():
        c1 = await asyncpg.connect(uri)
        c2 = await asyncpg.connect(uri)
        try:
            await _schema(c1)
            exp_id, base_rev = await _seed_experiment(c1)
            job_id, token = await _seed_job(c1, exp_id=exp_id, base_rev=base_rev)

            repo1 = CandidateRepository(c1)
            repo2 = CandidateRepository(c2)

            native = load_native("optics.convex_lens")
            views = {}
            content_hash = content_fingerprint(native, views)

            # 1. 初始化候选（version=0, status='editing'）
            cand = await repo1.initialize(
                job_id=job_id,
                experiment_id=exp_id,
                base_revision=base_rev,
                owner_id=OWNER,
                template_id="optics.convex_lens",
                native_data=native,
                teaching_views=views,
                content_hash=content_hash,
            )
            assert cand["status"] == "editing"
            assert cand["state_version"] == 0

            # 2. Connection 1 (Writer) 已经读到 expected_version = 0
            expected_ver = cand["state_version"]

            # 3. Connection 2 (Worker / Build 阶段) 冻结候选
            frozen = await repo2.freeze(job_id, content_hash=content_hash)
            assert frozen["status"] == "frozen"

            in_db_after_freeze = await repo2.load(job_id)
            assert in_db_after_freeze["status"] == "frozen"

            # 4. Connection 1 (旧 Writer) 执行迟滞的写入 (expected_version = 0)
            new_native = dict(native)
            new_native["title"] = "tampered_by_stale_writer"
            new_hash = content_fingerprint(new_native, views)

            # 这里必须抛出 CandidateFrozen，绝不能让已冻结候选被重新写开！
            with pytest.raises(CandidateFrozen):
                await repo1.write(
                    job_id,
                    native_data=new_native,
                    teaching_views=views,
                    content_hash=new_hash,
                    expected_version=expected_ver,
                )

            # 5. 校验库中候选仍为 frozen，内容未被篡改
            final_cand = await repo2.load(job_id)
            assert final_cand["status"] == "frozen"
            assert final_cand["content_hash"] == content_hash
            assert final_cand["native_data"].get("title") != "tampered_by_stale_writer"
        finally:
            await c1.close()
            await c2.close()

    asyncio.run(go())


def test_freeze_is_idempotent_and_rejects_content_tampering(uri):
    """Gate C.0: freeze 幂等性与内容哈希校验。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            repo = CandidateRepository(c)

            native = load_native("optics.convex_lens")
            views = {}
            content_hash = content_fingerprint(native, views)

            await repo.initialize(
                job_id=job_id, experiment_id=exp_id, base_revision=base_rev,
                owner_id=OWNER, template_id="optics.convex_lens",
                native_data=native, teaching_views=views, content_hash=content_hash,
            )

            # 第一次 freeze 成功
            f1 = await repo.freeze(job_id, content_hash=content_hash)
            assert f1["status"] == "frozen"

            # 相同 hash 重复 freeze 必须幂等成功
            f2 = await repo.freeze(job_id, content_hash=content_hash)
            assert f2["status"] == "frozen"

            # 错误 hash 试图 freeze 必须被拒
            with pytest.raises(CandidateVersionConflict):
                await repo.freeze(job_id, content_hash="bad_hash_hex")
        finally:
            await c.close()

    asyncio.run(go())


def test_bind_validation_respects_status_and_content_hash(uri):
    """Gate C.0: bind_validation 仅允许在 editing/frozen 态且内容哈希匹配时绑定。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            repo = CandidateRepository(c)

            native = load_native("optics.convex_lens")
            views = {}
            content_hash = content_fingerprint(native, views)

            await repo.initialize(
                job_id=job_id, experiment_id=exp_id, base_revision=base_rev,
                owner_id=OWNER, template_id="optics.convex_lens",
                native_data=native, teaching_views=views, content_hash=content_hash,
            )

            # editing 态绑定相同 hash: 成功
            v_id1 = uuid.uuid4()
            b1 = await repo.bind_validation(job_id, validation_id=v_id1, content_hash=content_hash)
            assert b1["validation_id"] == v_id1

            # 冻结后绑定相同 hash: 成功（支持 run_validation final=True 的先冻结再绑报告）
            await repo.freeze(job_id, content_hash=content_hash)
            v_id2 = uuid.uuid4()
            b2 = await repo.bind_validation(job_id, validation_id=v_id2, content_hash=content_hash)
            assert b2["validation_id"] == v_id2

            # 篡改 hash 试图绑定: 拒绝
            with pytest.raises(CandidateVersionConflict):
                await repo.bind_validation(job_id, validation_id=uuid.uuid4(), content_hash="mismatched_hash")

            # 已发布状态拒绝篡改绑定
            await repo.set_status(job_id, status="published")
            with pytest.raises(CandidateFrozen):
                await repo.bind_validation(job_id, validation_id=uuid.uuid4(), content_hash=content_hash)
        finally:
            await c.close()

    asyncio.run(go())


def test_rebase_requires_frozen_or_published_status(uri):
    """Gate C.0: rebase 必须在已冻结或已发布状态下才允许执行，未冻结的编辑态禁止 rebase。"""

    async def go():
        c = await asyncpg.connect(uri)
        try:
            await _schema(c)
            exp_id, base_rev = await _seed_experiment(c)
            job_id, token = await _seed_job(c, exp_id=exp_id, base_rev=base_rev)
            repo = CandidateRepository(c)

            native = load_native("optics.convex_lens")
            views = {}
            content_hash = content_fingerprint(native, views)

            await repo.initialize(
                job_id=job_id, experiment_id=exp_id, base_revision=base_rev,
                owner_id=OWNER, template_id="optics.convex_lens",
                native_data=native, teaching_views=views, content_hash=content_hash,
            )

            new_rev = uuid.uuid4()
            # 此时 status 为 'editing'，禁止 rebase
            with pytest.raises(CandidateVersionConflict):
                await repo.rebase(job_id, revision_id=new_rev)

            # 冻结后 rebase 成功，并将状态重置为 editing
            await repo.freeze(job_id, content_hash=content_hash)
            await repo.rebase(job_id, revision_id=new_rev)
            row = await repo.load(job_id)
            assert row["base_revision"] == new_rev
            assert row["status"] == "editing"
        finally:
            await c.close()

    asyncio.run(go())

