"""LangGraph 规划图（§4.2）。

图只负责节点编排；业务都在 services 里，便于用桩模型替换 DeepSeek 做无密钥测试。
一次调用产出一个 WorkOrder 就返回——长任务的阶段、重试与恢复交给数据库任务，
不依赖进程内状态（这也是第 7～8 周迁 AgentArts 时不改图的唯一前提）。
"""
from __future__ import annotations

from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from eduforge.agent.state import PlanningServices, PlanningState
from eduforge.domain.contracts import EditProposal, PlannerRequest, WorkOrder

__all__ = ["PlanningState", "PlanningServices", "build_planning_graph"]


def build_planning_graph(services: PlanningServices):
    async def load_context(state: PlanningState):
        return {"context": await services.load_context(state["request"])}

    async def retrieve(state: PlanningState):
        return {"evidence": await services.retrieve(state["request"].prompt, state["context"])}

    async def draft(state: PlanningState):
        return {"proposal": await services.draft(
            state["request"], state["context"], state["evidence"]
        )}

    def authorize(state: PlanningState):
        return {"work_order": services.authorize(
            state["request"], state["context"], state["proposal"]
        )}

    graph = StateGraph(PlanningState)
    graph.add_node("load_context", load_context)
    graph.add_node("retrieve", retrieve)
    graph.add_node("draft", draft)
    graph.add_node("authorize", authorize)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "retrieve")
    graph.add_edge("retrieve", "draft")
    graph.add_edge("draft", "authorize")
    graph.add_edge("authorize", END)
    return graph.compile()
