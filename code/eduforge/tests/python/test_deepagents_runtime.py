"""Deep Agents 执行核心的循环与门禁测试（脚本化假模型，不触网、不花钱）。

这组测试证明的是**工程正确性**：多轮循环真的存在、失败真的会被观察并驱动下一步、
模型拿不到发布权、超范围请求不会被偷偷换值。真实模型的自主能力由
`test_deepagents_real_model.py` 单独证明（需要 key，无 key 时 SKIPPED）。

假模型与真模型走同一条装配路径（`build_experiment_agent`），只差 `model` 实例。
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

from _regex_baseline import parse_teaching_instructions
from eduforge.agent.deepagents_runtime import run_experiment_agent
from eduforge.agent.fake_model import ScriptedToolModel
from eduforge.agent.tool_registry import AGENT_VISIBLE_TOOLS, BACKEND_ONLY_TOOLS, agent_tools
from eduforge.experiment_tools.contracts import (
    InspectSceneInput,
    JobContext,
    OpenExperimentInput,
)
from eduforge.experiment_tools.langchain_tools import get_experiment_tools
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.migrations import apply_migrations


@pytest.fixture(scope="module")
def uri():
    tmp_pg = tempfile.mkdtemp(prefix="eduforge-deep-pg-")
    server = pgserver.get_server(tmp_pg, cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture
def artifact_dir():
    yield Path(tempfile.mkdtemp(prefix="eduforge-deep-art-"))


async def _fresh_service(c, artifact_dir: Path, engine_url: str) -> ExperimentToolService:
    await apply_migrations(c)
    for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
        await c.execute(f"delete from {t}")
    job_id = uuid.uuid4()
    lease_token = uuid.uuid4().hex
    await c.execute(
        """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                             idempotency_key, request_hash, lease_token, lease_until)
           values ($1,$2,$3,$4,'组合任务','running',$1,'h',$5, now() + interval '300 seconds')""",
        job_id, "teacher-deep", uuid.uuid4(), uuid.uuid4(), lease_token,
    )
    return ExperimentToolService(
        engine_client=EngineClient(engine_url),
        conn=c,
        artifact_dir=artifact_dir,
        job=JobContext(job_id=job_id, owner_id="teacher-deep", lease_token=lease_token),
    )


def _exp_id(out: dict) -> str:
    for step in out["trace"]:
        if step["tool_name"] == "open_experiment" and isinstance(step["observation"], dict):
            return str(step["observation"]["experiment_id"])
    raise AssertionError("循环没有打开实验")


def _applied_edits(out: dict) -> list[dict]:
    edits: list[dict] = []
    for step in out["trace"]:
        if step["tool_name"] == "apply_scene_patch":
            edits.extend((step["args"] or {}).get("edits", []))
    return edits


COMBINATION_TASK = "找到凸透镜成像实验，把焦距调成 15cm、物距调成 30cm，加入实验数据记录表，验证正确后准备交付。"


def test_skill_and_prompt_reach_the_model():
    """SKILL.md 与行为规范必须真的进到系统提示词里。

    `skills/ray-optics-customization/SKILL.md` 那 27 行纪律此前零代码读取——
    不注入模型，它就只是给人看的文档。这条断言让「已启用」这件事有凭据。
    """
    from eduforge.agent.deepagents_runtime import SKILL_PATH, build_system_prompt

    prompt = build_system_prompt(extra_facts="目标实验 exp-1，模板 optics.convex_lens。")
    assert SKILL_PATH.is_file()
    # 来自 SKILL.md 的领域纪律
    assert "对象身份绑定必须使用 `name` 字段" in prompt
    assert "units_per_unit" in prompt
    assert "严禁篡改验证用例" in prompt
    # 来自 prompts/experiment_agent.md 的行为纪律
    assert "不得伪造或修饰实验结果" in prompt
    assert "不允许" in prompt
    # 本次任务事实
    assert "optics.convex_lens" in prompt


def test_loop_drives_tools_and_completes_combination_task(engine_url, uri, artifact_dir):
    """组合任务由循环自主完成：开→查→改→配表→验，且场景真实值就是 15/30。"""

    async def _go():
        c = await asyncpg.connect(uri)
        service = await _fresh_service(c, artifact_dir, engine_url)
        model = ScriptedToolModel(
            goal={"focal_length_cm": 15.0, "object_distance_cm": 30.0, "view": "measurement_table"}
        )
        out = await run_experiment_agent(
            model=model, service=service, prompt=COMBINATION_TASK, job_id=str(service.job.job_id)
        )

        required = {
            "open_experiment", "inspect_scene", "apply_scene_patch",
            "configure_teaching_views", "run_validation",
        }
        assert required <= set(out["distinct_tools"]), out["distinct_tools"]
        assert out["tool_calls_total"] >= 5, "多轮循环必须真的发生，而不是单次调用"
        assert out["final_validation"]["passed"] is True
        assert out["validation_rounds"] >= 1

        insp = await service.inspect_scene(InspectSceneInput(experiment_id=_exp_id(out)))
        assert insp.parameters["focal_length_cm"] == 15.0
        assert insp.parameters["object_distance_cm"] == 30.0

        # 循环没有发布权：库里只有 open_experiment 建的那一条基线版本，job 仍在 running
        assert await c.fetchval("select count(*) from experiment_revisions") == 1
        assert await c.fetchval("select status from jobs where id = $1", service.job.job_id) == "running"
        await c.close()

    asyncio.run(_go())


def test_publish_and_build_are_not_model_visible(engine_url, uri, artifact_dir):
    """构建与发布不进模型可见工具表——这是「后端判定发布」的结构保证。"""

    async def _go():
        c = await asyncpg.connect(uri)
        service = await _fresh_service(c, artifact_dir, engine_url)
        visible = [t.name for t in agent_tools(service)]
        assert set(visible) == set(AGENT_VISIBLE_TOOLS)
        for forbidden in BACKEND_ONLY_TOOLS:
            assert forbidden not in visible

        # 完整 8 项仍然存在于服务面（后端自己要用），只是不给模型
        all_tools = {t.name for t in get_experiment_tools(service)}
        assert {"build_package", "publish_revision"} <= all_tools

        # 模型可见的 schema 里不得出现身份/租约字段
        for tool in agent_tools(service):
            schema = json.dumps(tool.args_schema.model_json_schema())
            for leak in ("owner_id", "lease_token", "job_id"):
                assert leak not in schema, f"{tool.name} 的模型可见 schema 泄露了 {leak}"
        await c.close()

    asyncio.run(_go())


def test_regex_control_group_is_wording_brittle():
    """对照组事实：旧的正则解析只在它自己见过的那几种措辞上成立。

    比预想更脆——连外部文档给的里程碑任务原话「把焦距调成 15cm」都拿不到意图
    （旧模式只认 `调整为|设为|为`，不认 `调成`），而且**漏掉是静默的**：
    它会带着一个「什么都没改」的场景继续往下走并报 passed。
    真正的措辞不变性由真模型测试负责（`test_deepagents_real_model.py`，无 key 时 SKIPPED）。
    """
    def intent(text: str):
        plan = parse_teaching_instructions(text)
        return {(e["entity_id"], e["parameter"], e["value"]) for e in plan["phase1_edits"]}

    expected = {
        ("lens_1", "focal_length_cm", 15.0),
        ("object_1", "object_distance_cm", 30.0),
    }

    # 旧实现自己的措辞：能拿全
    assert intent("将焦距调整为15cm，物距调整为30cm") == expected
    # 换措辞：全部落空，且落空表现为空列表而不是报错
    for text in [
        "把焦距调成 15cm、物距调成 30cm",
        "透镜会聚能力换成 15 厘米，光源到透镜的距离改成 30 厘米",
        "帮我把 f 设成 15cm；u 我要 30cm",
    ]:
        assert intent(text) == set(), f"正则不该在这条措辞上拿全: {text}"


def test_observation_drives_the_value_written(engine_url, uri, artifact_dir):
    """目标值由 inspect_scene 的真实读数算出——证明决策读的是观察，不是常量。"""

    async def _go():
        c = await asyncpg.connect(uri)
        service = await _fresh_service(c, artifact_dir, engine_url)
        # 先把场景读出来，再要求「比当前焦距小 5cm」
        open_out = await service.open_experiment(OpenExperimentInput(template_id="optics.convex_lens"))
        base = await service.inspect_scene(InspectSceneInput(experiment_id=open_out.experiment_id))
        f0 = base.parameters["focal_length_cm"]

        model = ScriptedToolModel(goal={}, goal_from_observation={"focal_length_cm": -5.0})
        # 脚本模型需要自己走一遍 inspect，才能拿到 observation
        out = await run_experiment_agent(
            model=model, service=service,
            prompt="在这份凸透镜实验上，把焦距调成比现在小 5 厘米，然后验证。",
            job_id=str(service.job.job_id),
        )
        applied = _applied_edits(out)
        focal = [e["value"] for e in applied if e["parameter"] == "focal_length_cm"]
        assert focal, "没有焦距修改动作，说明观察没有驱动决策"
        assert focal[0] == round(float(f0) - 5.0, 4), f"应写入 {f0 - 5}，实际 {focal[0]}"
        await c.close()

    asyncio.run(_go())


def test_refused_request_is_reported_not_substituted(engine_url, uri, artifact_dir):
    """超量程请求（60cm > 上限 50cm）必须作为失败被报告，绝不被换成别的值交付。"""

    async def _go():
        c = await asyncpg.connect(uri)
        service = await _fresh_service(c, artifact_dir, engine_url)
        model = ScriptedToolModel(goal={"focal_length_cm": 60.0})
        out = await run_experiment_agent(
            model=model, service=service,
            prompt="把凸透镜的焦距改成 60cm，然后验证并准备交付。",
            job_id=str(service.job.job_id),
        )
        # 没有任何一次成功的写入把场景改成 60，也没有伪造的 passed
        assert all(e["value"] == 60.0 for e in _applied_edits(out))
        refused = [s for s in out["trace"] if s["tool_name"] == "apply_scene_patch"]
        assert refused and all(s.get("is_error") for s in refused), "越界写入必须以失败被观察到"
        assert out["final_validation"] is None or out["final_validation"].get("passed") is not True

        insp = await service.inspect_scene(InspectSceneInput(experiment_id=_exp_id(out)))
        assert insp.parameters["focal_length_cm"] != 60.0
        assert await c.fetchval("select count(*) from experiment_revisions") == 1
        await c.close()

    asyncio.run(_go())
