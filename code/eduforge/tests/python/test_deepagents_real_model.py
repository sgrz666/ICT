"""真实模型的自主执行证据（需要 DeepSeek key；无 key 时如实 SKIPPED）。

这条测试要证明的不是工程正确性（那由 `test_deepagents_runtime.py` 负责），
而是外部方案文档 §11 里最难的一条：**是模型在选工具、看观察、决定要不要修**，
不是我们的代码在替它决定。因此判据都落在「模型自己产生的轨迹」上：

- 提示词只用教师的自然语言，不给脚本目标；
- 场景里的最终值必须等于教师要求的值（不许换值交付）；
- 轨迹里必须出现多次工具往返，且验证结论来自引擎观察。

凭据只从环境变量读取（`infrastructure/settings.get_deepseek_api_key()`），
绝不写进任何仓库文件；报告里也只落模型名与用量，不落 key。
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import tempfile
import uuid

import asyncpg
import pgserver
import pytest

from eduforge.agent.deepagents_runtime import run_experiment_agent
from eduforge.agent.model import create_model, resolve_model_name
from eduforge.experiment_tools.contracts import InspectSceneInput, JobContext
from eduforge.experiment_tools.service import ExperimentToolService
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.repositories import JOBS_DDL
from eduforge.infrastructure.settings import get_deepseek_api_key

# tests/python/x.py 的 parents：0=python 1=tests 2=eduforge 3=code 4=仓库根
REPORT_PATH = (
    Path(__file__).resolve().parents[4] / "output" / "eduforge" / "reports" / "agent-deepagents-real.json"
)

TEACHER_PROMPT = (
    "找到凸透镜成像实验，把焦距调成 15cm、物距调成 30cm，加入实验数据记录表，"
    "然后用验证确认这个组合是对的。完成后说明你实际改成了什么。"
)


@pytest.fixture(scope="module")
def uri():
    tmp_pg = tempfile.mkdtemp(prefix="eduforge-real-pg-")
    server = pgserver.get_server(tmp_pg, cleanup_mode=None)
    try:
        yield server.get_uri()
    finally:
        stop = getattr(server, "stop", None)
        if callable(stop):
            stop()


@pytest.fixture
def artifact_dir():
    yield Path(tempfile.mkdtemp(prefix="eduforge-real-art-"))


@pytest.mark.skipif(
    get_deepseek_api_key() is None,
    reason="requires DEEPSEEK key (deepseek / DEEPSEEK / DEEPSEEK_API_KEY); 真实模型验收未做不等于已做",
)
def test_real_model_autonomously_completes_combination_task(engine_url, uri, artifact_dir):
    async def _go():
        c = await asyncpg.connect(uri)
        await c.execute(JOBS_DDL)
        for t in ("artifacts", "validation_reports", "job_events", "jobs", "experiment_revisions", "experiments"):
            await c.execute(f"delete from {t}")
        job_id = uuid.uuid4()
        lease = uuid.uuid4().hex
        await c.execute(
            """insert into jobs (id, owner_id, experiment_id, base_revision, prompt, status,
                                 idempotency_key, request_hash, lease_token, lease_until)
               values ($1,$2,$3,$4,$5,'running',$1,'h',$6, now() + interval '600 seconds')""",
            job_id, "teacher-real", uuid.uuid4(), uuid.uuid4(), TEACHER_PROMPT, lease,
        )
        service = ExperimentToolService(
            engine_client=EngineClient(engine_url), conn=c, artifact_dir=artifact_dir,
            job=JobContext(job_id=job_id, owner_id="teacher-real", lease_token=lease),
        )

        model = create_model(temperature=0)
        out = await run_experiment_agent(
            model=model, service=service, prompt=TEACHER_PROMPT, job_id=str(job_id), max_turns=30
        )

        exp_id = next(
            str(s["observation"]["experiment_id"])
            for s in out["trace"]
            if s["tool_name"] == "open_experiment" and isinstance(s["observation"], dict)
        )
        insp = await service.inspect_scene(InspectSceneInput(experiment_id=exp_id))

        report = {
            "profile": "deepagents_real",
            "model": resolve_model_name(),
            "ran_at": "见 git 提交时间",
            "prompt": TEACHER_PROMPT,
            "tool_calls_total": out["tool_calls_total"],
            "distinct_tools": out["distinct_tools"],
            "validation_rounds": out["validation_rounds"],
            "final_validation": out["final_validation"],
            "scene_parameters": insp.parameters,
            "trace": out["trace"],
        }
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        assert out["tool_calls_total"] >= 3, "没有多轮往返就说明没走模型循环"
        assert {"inspect_scene", "apply_scene_patch"} <= set(out["distinct_tools"])
        # 教师要求的值必须原样落在场景里，不许被换成「更合适」的值
        assert insp.parameters["focal_length_cm"] == 15.0
        assert insp.parameters["object_distance_cm"] == 30.0
        assert out["final_validation"] is not None and out["final_validation"]["passed"] is True
        # 模型没有发布权
        assert await c.fetchval("select count(*) from experiment_revisions") == 1
        await c.close()

    asyncio.run(_go())
