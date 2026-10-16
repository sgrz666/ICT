"""§6.3 AgentArts 与本地 Agent 入口测试。

验证 build_planner 组装的规划图与华为云 AgentArts 运行时契约、本地 HTTP 契约完全吻合。
"""
import uuid
import httpx
import pytest
from pydantic import ValidationError

from eduforge.agent.bootstrap import build_planner
from eduforge.agent.policy import Rejected
from eduforge.domain.contracts import EditProposal, PlannerRequest, WorkOrder
from eduforge.entrypoints import agentarts, agent_local


class MockPlanner:
    def __init__(self, proposal: EditProposal | None = None, raise_error: Exception | None = None):
        self.proposal = proposal or EditProposal(
            route="config",
            operations=[{
                "op": "set_parameter",
                "entity_id": "lens_1",
                "parameter": "focal_length_cm",
                "value": 15.0,
            }],
        )
        self.raise_error = raise_error

    async def ainvoke(self, inputs, config=None):
        if self.raise_error:
            raise self.raise_error
        req: PlannerRequest = inputs["request"]
        wo = WorkOrder(
            job_id=req.job_id,
            experiment_id=req.experiment_id,
            base_revision=req.base_revision,
            engine_id="ray_optics",
            proposal=self.proposal,
        )
        return {"work_order": wo, "proposal": self.proposal}


import asyncio


def test_agentarts_handler_success():
    async def body():
        mock_p = MockPlanner()
        agentarts.set_planner(mock_p)

        payload = {
            "job_id": str(uuid.uuid4()),
            "experiment_id": str(uuid.uuid4()),
            "base_revision": str(uuid.uuid4()),
            "template_id": "optics.convex_lens",
            "prompt": "将焦距改成 15 厘米",
        }
        out = await agentarts.handler(payload)
        assert out["engine_id"] == "ray_optics"
        assert out["proposal"]["route"] == "config"
        assert len(out["proposal"]["operations"]) == 1
        assert out["proposal"]["operations"][0]["value"] == 15.0

    asyncio.run(body())


def test_agentarts_handler_invalid_payload():
    async def body():
        with pytest.raises(ValidationError):
            await agentarts.handler({"prompt": "缺少必要身份字段"})

    asyncio.run(body())


def test_agent_local_endpoint_success():
    async def body():
        mock_p = MockPlanner()
        agent_local.set_planner(mock_p)

        transport = httpx.ASGITransport(app=agent_local.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            res = await c.post("/plan", json={
                "job_id": str(uuid.uuid4()),
                "experiment_id": str(uuid.uuid4()),
                "base_revision": str(uuid.uuid4()),
                "template_id": "optics.convex_lens",
                "prompt": "将焦距改成 15 厘米",
            })
            assert res.status_code == 200
            data = res.json()
            assert data["engine_id"] == "ray_optics"
            assert data["proposal"]["route"] == "config"
            assert data["proposal"]["operations"][0]["entity_id"] == "lens_1"

    asyncio.run(body())


def test_agent_local_endpoint_rejected():
    async def body():
        mock_p = MockPlanner(raise_error=Rejected("PARAMETER_OUT_OF_RANGE", "焦距超出量程"))
        agent_local.set_planner(mock_p)

        transport = httpx.ASGITransport(app=agent_local.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            res = await c.post("/plan", json={
                "job_id": str(uuid.uuid4()),
                "experiment_id": str(uuid.uuid4()),
                "base_revision": str(uuid.uuid4()),
                "template_id": "optics.convex_lens",
                "prompt": "将焦距改成 999 厘米",
            })
            assert res.status_code == 400
            data = res.json()
            assert data["detail"]["code"] == "PARAMETER_OUT_OF_RANGE"

    asyncio.run(body())
