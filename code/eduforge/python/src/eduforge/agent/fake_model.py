"""脚本化假模型：只为验证循环、门禁与失败修复通路，不代表任何模型能力。

它和真实模型走**同一条代码路径**（同一个 `create_deep_agent`、同一套工具、
同一套判定），只差 `model` 实例。任何「循环跑通」的证据都必须在这里成立，
否则真模型跑通也说明不了工程正确性。

它刻意**不解析自然语言**：目标由 `goal` / `goal_from_observation` 给定，
所以「换了措辞还能不能做对」这个问题在这里根本不会出现——
那正是它和已删除的正则实现的分界线，也是测试要拿去对照的地方。
"""
from __future__ import annotations

import json
from typing import Any, Optional, Sequence

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult


def _last(messages: Sequence[BaseMessage], name: str) -> Optional[dict[str, Any]]:
    for msg in reversed(list(messages)):
        if isinstance(msg, ToolMessage) and msg.name == name:
            content = msg.content
            if isinstance(content, str):
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return None
            return content if isinstance(content, dict) else None
    return None


def _called(messages: Sequence[BaseMessage], name: str) -> int:
    return sum(
        1
        for msg in messages
        if isinstance(msg, AIMessage)
        for call in (getattr(msg, "tool_calls", None) or [])
        if call.get("name") == name
    )


def _is_error(obs: Optional[dict[str, Any]]) -> bool:
    return bool(isinstance(obs, dict) and obs.get("isError"))


def _latest_index(messages: Sequence[BaseMessage], name: str) -> int:
    """该工具最近一次观察在对话里的位置；没发生过就是 -1。"""
    idx = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, ToolMessage) and msg.name == name:
            idx = i
    return idx


class ScriptedToolModel(BaseChatModel):
    """按观察推进的工具调用模型。

    `goal` 是固定目标值；`goal_from_observation` 让目标值由 `inspect_scene`
    的真实读数算出来（用来证明「是观察在驱动决策」，不是脚本里的常量）。
    """

    goal: dict[str, Any] = {}
    goal_from_observation: dict[str, Any] = {}
    max_repairs: int = 2

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-model"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedToolModel":
        # 真实模型在这里拿到工具 schema；脚本模型只需要知道工具存在。
        return self

    def _plan(self, messages: Sequence[BaseMessage]) -> tuple[str, dict[str, Any]] | None:
        exp = self._exp_id(messages)
        opened = _called(messages, "open_experiment") > 0
        inspected = _called(messages, "inspect_scene") > 0
        patched = _called(messages, "apply_scene_patch")
        views_done = _called(messages, "configure_teaching_views") > 0
        validations = _called(messages, "run_validation")

        # 任何一次写操作被拒绝，就如实停下：绝不换一个值蒙过去
        for name in ("apply_scene_patch", "configure_teaching_views", "open_experiment"):
            if _is_error(_last(messages, name)):
                return None

        if not opened:
            return ("open_experiment", {"template_id": "optics.convex_lens"})
        if not inspected:
            return ("inspect_scene", {"experiment_id": exp})

        params = self._target_params(messages)
        view = self.goal.get("view")
        last_val = _last(messages, "run_validation")

        if params and patched == 0:
            return ("apply_scene_patch", {
                "experiment_id": exp,
                "edits": [
                    {"entity_id": eid, "parameter": p, "value": float(v)}
                    for (eid, p), v in params.items()
                ],
            })
        if view and not views_done:
            return ("configure_teaching_views", {"experiment_id": exp, "views": {view: True}})
        if validations == 0:
            return ("run_validation", {"experiment_id": exp})

        # 上一次验证之后又改过内容，旧结论即刻不作数——先重验，再谈修不修
        if validations > 0 and _latest_index(messages, "apply_scene_patch") > _latest_index(messages, "run_validation"):
            return ("run_validation", {"experiment_id": exp})

        # 有失败判据且还有修复额度：按观察到的 expected 重下那一条，再验一次
        if isinstance(last_val, dict) and last_val.get("passed") is False and validations <= self.max_repairs:
            fix = self._repair_edit(messages, last_val)
            if fix is not None:
                return ("apply_scene_patch", {"experiment_id": exp, "edits": [fix]})
            return ("run_validation", {"experiment_id": exp})
        return None

    @staticmethod
    def _exp_id(messages: Sequence[BaseMessage]) -> str:
        obs = _last(messages, "open_experiment") or {}
        return str(obs.get("experiment_id", ""))

    def _target_params(self, messages: Sequence[BaseMessage]) -> dict[tuple[str, str], float]:
        entity = {"focal_length_cm": "lens_1", "object_distance_cm": "object_1"}
        out: dict[tuple[str, str], float] = {}
        for param, value in (self.goal or {}).items():
            if param in entity:
                out[(entity[param], param)] = float(value)
        obs = _last(messages, "inspect_scene") or {}
        current = obs.get("parameters") or {}
        for param, delta in (self.goal_from_observation or {}).items():
            if param in current and current[param] is not None:
                out[(entity[param], param)] = round(float(current[param]) + float(delta), 4)
        return out

    def _repair_edit(self, messages: Sequence[BaseMessage], validation: dict[str, Any]) -> dict[str, Any] | None:
        """依据失败判据里的 expected 重下这一条——修的是观察，不是硬编码值。"""
        for check in validation.get("checks", []) or []:
            if check.get("passed"):
                continue
            cid = str(check.get("id", ""))
            param = "focal_length_cm" if "focal" in cid else ("object_distance_cm" if "object" in cid else None)
            if param is None or check.get("expected") is None:
                continue
            entity = {"focal_length_cm": "lens_1", "object_distance_cm": "object_1"}[param]
            return {"entity_id": entity, "parameter": param, "value": float(check["expected"])}
        return None

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        step = self._plan(messages)
        if step is None:
            done = _last(messages, "run_validation") or {}
            text = (
                f"停止推进。最后一次验证结论：{done.get('verdict', '无')}；"
                "被拒绝或超范围的请求不会被换成别的值交付。"
            )
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
        name, args = step
        call = {"name": name, "args": args, "id": f"call_{len(messages)}_{name}"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[call]))])
