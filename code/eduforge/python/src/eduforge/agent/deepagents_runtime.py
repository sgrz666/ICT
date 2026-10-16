"""Deep Agents 执行核心：把真实模型接进 `ExperimentToolService`。

与旧 `ExperimentToolAgent`（已删）的区别不是「节点更多」，而是**决策权在模型**：
每一步调用哪个工具、传什么参数、看到失败后怎么改，都由模型的 tool_calls 决定，
Python 侧不再有任何 if/elif 分发或正则解析教师的话。

装配上刻意选择 `StateBackend`：Deep Agents 的脚手架中间件
（`FilesystemMiddleware` / `SubAgentMiddleware`）是必需的、拆不掉，模型总会看到
`ls`/`read_file`/`write_file`/`execute` 这类工具。用非沙箱 backend 时这些工具只作用于
会话状态、`execute` 直接返回错误，因此它们拿不到真实磁盘与命令行——
这是选它而不是 `LocalShellBackend`/`FilesystemBackend` 的唯一理由。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from eduforge.agent.prompts import load_experiment_prompt
from eduforge.agent.tool_registry import AGENT_VISIBLE_TOOLS, BACKEND_ONLY_TOOLS, agent_tools
from eduforge.experiment_tools.service import ExperimentToolService

# SKILL.md 是本仓库唯一成文的实验纪律，此前零代码读取它。
# 不注入模型，那 27 行就只是给人看的文档。
SKILL_PATH = Path(__file__).resolve().parents[4] / "skills" / "ray-optics-customization" / "SKILL.md"


def load_skill_text() -> str:
    try:
        return SKILL_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""


def build_system_prompt(extra_facts: str = "") -> str:
    parts = [load_experiment_prompt(), "\n\n## 实验清单纪律（来自 skills/ray-optics-customization/SKILL.md）\n", load_skill_text()]
    if extra_facts:
        parts.append("\n\n## 本次任务的已知事实\n" + extra_facts)
    return "".join(parts)


def build_experiment_agent(
    *,
    model: Any,
    service: ExperimentToolService,
    checkpointer: Any | None = None,
    extra_facts: str = "",
):
    """装配主 Agent。`model` 可以是真实 ChatModel，也可以是脚本化假模型。"""
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend

    return create_deep_agent(
        model=model,
        tools=agent_tools(service),
        backend=StateBackend(),
        checkpointer=checkpointer,
        system_prompt=build_system_prompt(extra_facts),
        name="eduforge-experiment-agent",
    )


def extract_trace(messages: list[Any]) -> list[dict[str, Any]]:
    """把一轮执行摊成可核对的台账：谁调了什么、参数是什么、观察到什么。"""
    trace: list[dict[str, Any]] = []
    seen: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if isinstance(msg, AIMessage) and getattr(msg, "tool_calls", None):
            for call in msg.tool_calls:
                entry = {
                    "tool_name": call.get("name"),
                    "args": call.get("args"),
                    "call_id": call.get("id"),
                    "observation": None,
                }
                trace.append(entry)
                if entry["call_id"]:
                    seen[entry["call_id"]] = entry
        elif isinstance(msg, ToolMessage):
            target = seen.get(msg.tool_call_id) if getattr(msg, "tool_call_id", None) else None
            content = msg.content
            if isinstance(content, str):
                try:
                    content = json.loads(content)
                except json.JSONDecodeError:
                    pass
            if target is not None:
                target["observation"] = content
                target["is_error"] = bool(isinstance(content, dict) and content.get("isError"))
            else:
                trace.append({"tool_name": msg.name, "args": None, "observation": content})
    return trace


def summarise(messages: list[Any]) -> dict[str, Any]:
    """从消息里算出「模型实际做过什么」，全部来自观察，不做任何美化。"""
    trace = extract_trace(messages)
    names = [t["tool_name"] for t in trace]
    validations = [
        t["observation"]
        for t in trace
        if t["tool_name"] == "run_validation" and isinstance(t["observation"], dict)
    ]
    last_validation = validations[-1] if validations else None
    return {
        "trace": trace,
        "tool_calls_total": len(trace),
        "distinct_tools": sorted(set(n for n in names if n)),
        "validation_rounds": len(validations),
        "final_validation": last_validation,
        "final_text": next(
            (m.content for m in reversed(messages) if isinstance(m, AIMessage) and isinstance(m.content, str) and m.content.strip()),
            "",
        ),
    }


async def run_experiment_agent(
    *,
    model: Any,
    service: ExperimentToolService,
    prompt: str,
    job_id: str,
    max_turns: int = 24,
    checkpointer: Any | None = None,
    extra_facts: str = "",
) -> dict[str, Any]:
    """让模型自己驱动工具循环完成一项实验制作任务。

    返回里没有「published」这种字段：构建与发布是后端的决定，调用方拿到的是
    观察台账与最后一次验证的真实结论，自己判断能不能发布。
    """
    agent = build_experiment_agent(model=model, service=service, checkpointer=checkpointer, extra_facts=extra_facts)
    result = await agent.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"recursion_limit": max_turns, "configurable": {"thread_id": job_id}},
    )
    out = summarise(result.get("messages", []))
    out["experiment_state"] = {
        "visible_tools": list(AGENT_VISIBLE_TOOLS),
        "backend_only_tools": list(BACKEND_ONLY_TOOLS),
    }
    return out
