"""验证实施方案（§1.2、§4.1、§4.2、§4.6、§4.8、§5.5、§6.4）新增架构模块的完整性与自洽性。"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from eduforge.agent.model import create_model
from eduforge.agent.retrieval import EvidenceRetriever
from eduforge.agent.state import PlanningServices, PlanningState
from eduforge.coding.budget import ExecutionBudget
from eduforge.coding.sandbox_factory import SandboxFactory
from eduforge.coding.workspace import WorkspaceManager
from eduforge.domain import (
    ConflictError,
    EduForgeError,
    Experiment,
    ExperimentRevision,
    Job,
    JobEvent,
    LeaseExpiredError,
    NotFoundError,
    PolicyViolationError,
    ScientificValidationError,
    ValidationReport,
)
from eduforge.domain.contracts import PlannerRequest, WorkOrder
from eduforge.infrastructure.clients.agent_client import LocalAgentClient
from eduforge.infrastructure.db.models import TABLES
from eduforge.infrastructure.settings import settings
from eduforge.infrastructure.storage.local import LocalArtifactStorage
from eduforge.infrastructure.storage.obs import OBSArtifactStorage
from eduforge.research.rea_runner import REARunner
from eduforge.validation.scientific.circuits import calculate_ohms_law
from eduforge.validation.scientific.mechanics import calculate_pendulum_period
from eduforge.worker.lease import LeaseManager


def test_domain_models_and_errors():
    """验证纯核心领域模型和异常定义规范（§1.2）。"""
    err = PolicyViolationError("超界拒绝", code="POLICY_REJECTED")
    assert isinstance(err, EduForgeError)
    assert err.code == "POLICY_REJECTED"

    exp_id = uuid4()
    exp = Experiment(id=exp_id, owner_id="t1", template_id="optics.convex_lens")
    assert exp.id == exp_id
    assert exp.head_revision_id is None

    rev = ExperimentRevision(
        id=uuid4(),
        experiment_id=exp_id,
        parent_id=None,
        engine_id="ray_optics",
        native_data={"version": 5},
    )
    assert rev.engine_id == "ray_optics"

    # 验证全部表名
    assert "jobs" in TABLES
    assert "experiments" in TABLES
    assert "artifacts" in TABLES


def test_agent_retrieval_and_state():
    """验证检索服务能够从可信模板检索受控参数与教学依据（§4.2）。"""
    retriever = EvidenceRetriever()
    evidence = retriever.retrieve_evidence(
        prompt="请把凸透镜焦距改成 15cm，观察虚像",
        template_id="optics/convex-lens",
    )
    assert len(evidence) >= 2
    types = [e["type"] for e in evidence]
    assert "allowed_parameters" in types
    assert "domain_rule" in types

    # 检查状态机字典类型约束
    state: PlanningState = {
        "context": {"units_per_unit": 10},
        "evidence": evidence,
    }
    assert "evidence" in state


def test_coding_workspace_and_budget():
    """验证代码定制的受控导出白名单和执行预算（§4.6）。"""
    budget = ExecutionBudget()
    assert budget.max_duration_seconds == 300
    assert budget.max_turns == 30

    mgr = WorkspaceManager()
    downloaded = {
        "src/lesson.ts": b"export const lesson = {};",
        "src/controls.ts": b"export const controls = [];",
        "package.json": b"{\"malicious\": true}",  # 不在白名单
        "/etc/passwd": b"root:x:0:0",             # 不在白名单
    }
    valid = mgr.validate_exports(downloaded)
    assert "src/lesson.ts" in valid
    assert "src/controls.ts" in valid
    assert "package.json" not in valid
    assert "/etc/passwd" not in valid


def test_sandbox_factory_graceful_missing():
    """验证在缺少 Docker 或 OpenSandbox 时抛出清晰配置异常（§4.6）。"""
    factory = SandboxFactory()
    with pytest.raises(EduForgeError) as exc_info:
        factory.create_sandbox()
    assert exc_info.value.code in ("SANDBOX_DEPENDENCY_MISSING", "DOCKER_UNAVAILABLE")


def test_worker_lease_manager():
    """验证 Worker 租约管理器校验逻辑（§4.8）。"""
    class DummyRepo:
        async def heartbeat(self, *, job_id, lease_token, lease_seconds):
            return True

    mgr = LeaseManager(
        repository=DummyRepo(),
        job_id=uuid4(),
        lease_token="test-token",
    )
    # 正常状态不应抛异常
    mgr.check_active()

    # 模拟标记失效
    mgr._expired = True
    with pytest.raises(LeaseExpiredError) as exc_info:
        mgr.check_active()
    assert exc_info.value.code == "LEASE_LOST"


def test_rea_runner_sample_analysis():
    """验证 REA 逆向研究专用分析器（§6.4）。"""
    with tempfile.TemporaryDirectory() as td:
        sample_file = Path(td) / "sample_engine.js"
        sample_file.write_text("console.log('RayOptics engine mock');", encoding="utf-8")

        runner = REARunner(output_dir=td)
        res = runner.analyze_sample(sample_file, target_name="test_engine")
        assert res["target_name"] == "test_engine"
        assert res["file_count"] == 1
        assert len(res["sample_sha256"]) == 64
        assert Path(res["report_path"]).exists()


def test_scientific_reservations_and_storage():
    """验证力学与电路保留科学计算与存储实现（§5.1, §1.2）。"""
    T = calculate_pendulum_period(1.0, g=9.8)
    assert 2.0 < T < 2.1

    I = calculate_ohms_law(10.0, 5.0)
    assert I == 2.0

    async def run_storage():
        with tempfile.TemporaryDirectory() as td:
            store = LocalArtifactStorage(base_dir=td)
            await store.put("rev1/artifact.txt", b"hello eduforge", "text/plain")
            assert await store.exists("rev1/artifact.txt")
            data = await store.get("rev1/artifact.txt")
            assert data == b"hello eduforge"

    asyncio.run(run_storage())

    obs = OBSArtifactStorage()
    with pytest.raises(EduForgeError):
        obs._ensure_client()


def test_local_agent_client_invocation():
    """验证 LocalAgentClient 真实调用 LangGraph 规划图产出合法 WorkOrder（§1.2 / §6.3）。"""
    from eduforge.agent.bootstrap import build_planner

    async def dummy_model(prompt, context, evidence):
        return {
            "route": "config",
            "operations": [
                {"op": "set_parameter", "entity_id": "lens_1", "parameter": "focal_length_cm", "value": 15.0}
            ],
        }

    planner = build_planner(dummy_model)
    client = LocalAgentClient(planner=planner)

    async def run_plan():
        req = PlannerRequest(
            job_id=uuid4(),
            experiment_id=uuid4(),
            base_revision=uuid4(),
            template_id="optics.convex_lens",
            prompt="把焦距改成 15cm",
        )
        return await client.plan(req)

    wo = asyncio.run(run_plan())
    assert isinstance(wo, WorkOrder)
    assert wo.engine_id == "ray_optics"
    assert wo.proposal.route == "config"
    assert len(wo.proposal.operations) >= 1
    assert wo.proposal.operations[0].op == "set_parameter"
    assert wo.proposal.operations[0].value == 15.0
