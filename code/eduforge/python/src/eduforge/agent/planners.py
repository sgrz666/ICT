"""规划端口的两个实现：真模型（要 key）与固定提案（只驱动链路）。

`StaticPlanner` 在 `worker.steps` 里。这里只放模型侧：
DeepSeek 的传输层本机没有 key，所以能被验证的部分（提示词与响应解析的契约）
做成纯函数单测，剩下一次 HTTP 调用留给有 key 的环境。
没有 key 时**拒绝启动**，不静默退化成固定提案——否则 Demo 会把自己骗成"Agent 会规划"。
"""
from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

from eduforge.agent.graph import build_planning_graph
from eduforge.agent.services import PlanningServices
from eduforge.domain.contracts import PlannerRequest

MODEL_URL = "https://api.deepseek.com/chat/completions"
MODEL_NAME = os.environ.get("EDUFORGE_MODEL", "deepseek-chat")

ModelFn = Callable[[str, dict[str, Any], list[dict[str, Any]]], Awaitable[dict[str, Any]]]


class MissingApiKey(Exception):
    pass


def api_key() -> str:
    key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not key:
        raise MissingApiKey(
            "DEEPSEEK_API_KEY 未设置。规划需要真实模型；"
            "不想用模型就在启动 Worker 时显式传 --planner-static-focal，"
            "那条路只用于验证链路，不能当作 Agent 能力。"
        )
    return key


def evidence_text(evidence: list[dict[str, Any]]) -> str:
    """知识只陈述事实：可用的 entity_id/parameter/量程与视图清单。
    权限由 policy.authorize 判，模型说什么都不能扩大它。"""
    return json.dumps(evidence, ensure_ascii=False, sort_keys=True)


def chat_prompt(prompt: str, context: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    return (
        "你在为中学物理教师修改一个凸透镜成像实验场景。只能输出一个 JSON 对象，"
        "不要解释、不要代码围栏。\n"
        "形状：{\"route\":\"config\",\"operations\":[{\"op\":\"set_parameter\","
        "\"entity_id\":\"...\",\"parameter\":\"...\",\"value\":数字}]}\n"
        "或 {\"route\":\"code\",\"code_task\":\"...\"}。\n"
        f"模板：{context['template_id']}\n"
        f"允许的操作数（越界或未知一律会被服务端拒绝）：{evidence_text(evidence)}\n"
        f"教师原话：{prompt}\n"
        "只改教师要求的东西；拿不准就选最贴近的一条，不要一次改多处。"
    )


def chat_payload(prompt: str, context: dict[str, Any], evidence: list[dict[str, Any]]) -> dict:
    return {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": chat_prompt(prompt, context, evidence)}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }


def parse_proposal_json(text: str) -> dict[str, Any]:
    """模型可能裹代码围栏或前后带话；剥掉之后再交给结构校验。

    结构校验本身不在这里做——`PlanningServices.draft` 会用 EditProposal.model_validate，
    不接受"看起来像"的字典。
    """
    body = text.strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
        if body.startswith("json"):
            body = body[4:].strip()
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型输出里没有 JSON 对象")
    return json.loads(body[start: end + 1])


def deepseek_model() -> ModelFn:
    token = api_key()

    async def call(prompt: str, context: dict[str, Any], evidence: list[dict[str, Any]]) -> dict:
        import httpx

        payload = chat_payload(prompt, context, evidence)
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.post(
                MODEL_URL, json=payload, headers={"authorization": f"Bearer {token}"}
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
        return parse_proposal_json(content)

    return call


class GraphPlanner:
    """LangGraph 四节点图（load_context→retrieve→draft→authorize）包装成 PlannerPort。

    图内已经跑过一次 authorize；Worker 的 Chain 会再跑一次并以它构造 WorkOrder。
    两次输入相同、判定纯函数，所以结果一致——重复不是疏漏，是为了让"每个阶段只信持久化事实"
    这条要求成立：Chain 不能依赖图内部对象的存活。
    """

    def __init__(self, model: ModelFn, *, template_of: Callable[[PlannerRequest], str]) -> None:
        self.graph = build_planning_graph(
            PlanningServices(model, template_of=template_of)
        )

    async def plan(self, request: PlannerRequest):
        out = await self.graph.ainvoke({"request": request})
        return out["proposal"]


def planner_from_env(*, template_of: Callable[[PlannerRequest], str]) -> GraphPlanner:
    return GraphPlanner(deepseek_model(), template_of=template_of)
