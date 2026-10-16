"""Agent 执行框架：基于 LangGraph 成熟工具调用循环与自愈修复的实验定制智能体。

提供完整的 Agent 工具调用闭环：
- 意图分析与工具编排规划；
- LangGraph StateGraph 驱动的状态机图编排；
- 8 项原子工具执行与细粒度 Trace 追踪留痕；
- 物理规律校验与闭环自愈修复（Read Scene -> Tool Call -> Observe -> Repair -> Deliver）；
- 连续版本演进（R1 -> R2 -> R3）；
- 交付产物与离线交互包输出。
"""
from __future__ import annotations

import math
import re
import time
from typing import Any, Callable, TypedDict
import uuid

from langgraph.graph import END, START, StateGraph

from eduforge.agent.policy import load_template
from eduforge.domain.errors import NotFoundError
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    BuildPackageInput,
    ConfigureTeachingViewsInput,
    InspectSceneInput,
    OpenExperimentInput,
    PublishRevisionInput,
    RunValidationInput,
    SearchExperimentsInput,
)
from eduforge.experiment_tools.langchain_tools import get_experiment_tools
from eduforge.experiment_tools.service import ExperimentToolService


class ToolTraceRecord:
    def __init__(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
        duration_ms: float,
        error: str | None = None,
    ) -> None:
        self.tool_name = tool_name
        self.arguments = arguments
        self.result = result
        self.duration_ms = duration_ms
        self.error = error
        self.timestamp = time.time()

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "result_summary": str(self.result)[:200],
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp,
        }


class ToolAgentState(TypedDict, total=False):
    prompt: str
    plan: dict[str, Any]
    experiment_id: str
    template_id: str
    revisions: dict[str, str]
    phase1_edits: list[dict[str, Any]]
    phase2_edits: list[dict[str, Any]]
    views: dict[str, Any]
    validation: dict[str, Any]
    repair_attempts: int
    repair_history: list[dict[str, Any]]
    views_res: dict[str, Any]
    measurement_table: dict[str, Any]
    offline_package: dict[str, Any]
    artifacts: list[dict[str, Any]]
    error: str | None


class ExperimentToolAgent:
    """具备成熟 LangGraph 编排、闭环自愈修复与连续编辑能力的物理实验 Agent。"""

    def __init__(
        self,
        service: ExperimentToolService,
        *,
        model_fn: Callable[[str, list[dict]], Any] | None = None,
    ) -> None:
        self.service = service
        self.model_fn = model_fn
        self.tools = get_experiment_tools(service)
        self.trace: list[ToolTraceRecord] = []

    async def _call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        start = time.time()
        err_msg = None
        res_dict: dict[str, Any] = {}
        try:
            if name == "search_experiments":
                out = await self.service.search_experiments(SearchExperimentsInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "open_experiment":
                out = await self.service.open_experiment(OpenExperimentInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "inspect_scene":
                out = await self.service.inspect_scene(InspectSceneInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "apply_scene_patch":
                out = await self.service.apply_scene_patch(ApplyScenePatchInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "configure_teaching_views":
                out = await self.service.configure_teaching_views(ConfigureTeachingViewsInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "run_validation":
                out = await self.service.run_validation(RunValidationInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "build_package":
                out = await self.service.build_package(BuildPackageInput.model_validate(args))
                res_dict = out.model_dump()
            elif name == "publish_revision":
                out = await self.service.publish_revision(PublishRevisionInput.model_validate(args))
                res_dict = out.model_dump()
            else:
                raise ValueError(f"未知工具: {name}")
        except Exception as exc:
            err_msg = str(exc)
            raise
        finally:
            duration = (time.time() - start) * 1000
            self.trace.append(
                ToolTraceRecord(
                    tool_name=name,
                    arguments=args,
                    result=res_dict,
                    duration_ms=duration,
                    error=err_msg,
                )
            )
        return res_dict

    def _parse_teaching_instructions(self, prompt: str) -> dict[str, Any]:
        """解析教师自然语言指令提取物理参数意图。"""
        instructions: dict[str, Any] = {
            "query": "凸透镜",
            "template_id": "optics.convex_lens",
            "phase1_edits": [],
            "phase2_edits": [],
            "views": {},
        }
        if "两面镜" in prompt or "平面镜" in prompt:
            instructions["query"] = "平面镜"

        # 焦距解析
        f_match = re.search(r"焦距(?:调整为|设为|为)?\s*(\d+(?:\.\d+)?)\s*cm", prompt)
        if f_match:
            f_val = float(f_match.group(1))
            instructions["phase1_edits"].append(
                {"entity_id": "lens_1", "parameter": "focal_length_cm", "value": f_val}
            )

        # 连续编辑物距解析（阶段二：随后/接着/继续/然后...物距）
        u2_match = re.search(r"(?:随后|接着|然后|继续).*?物距(?:.*?调整为|.*?设为|.*?为)?\s*(\d+(?:\.\d+)?)\s*cm", prompt)
        u1_match = None
        if u2_match:
            prefix = prompt[: u2_match.start()]
            u1_search = re.search(r"物距(?:调整为|设为|为)?\s*(\d+(?:\.\d+)?)\s*cm", prefix)
            if u1_search:
                u1_match = u1_search
            instructions["phase2_edits"].append(
                {"entity_id": "object_1", "parameter": "object_distance_cm", "value": float(u2_match.group(1))}
            )
        else:
            u1_match = re.search(r"物距(?:调整为|设为|为)?\s*(\d+(?:\.\d+)?)\s*cm", prompt)

        if u1_match:
            instructions["phase1_edits"].append(
                {"entity_id": "object_1", "parameter": "object_distance_cm", "value": float(u1_match.group(1))}
            )

        if "表格" in prompt or "记录" in prompt or "table" in prompt.lower():
            instructions["views"]["measurement_table"] = True

        return instructions

    def _build_graph(self) -> Any:
        graph = StateGraph(ToolAgentState)

        async def discover_and_open(state: ToolAgentState) -> dict[str, Any]:
            prompt = state["prompt"]
            plan = self._parse_teaching_instructions(prompt)

            # 1. 搜索实验
            search_res = await self._call_tool("search_experiments", {"query": plan["query"]})
            chosen_template = plan.get("template_id") or "optics.convex_lens"
            if search_res.get("items"):
                for it in search_res["items"]:
                    if plan["query"] in it.get("title", "") or plan["query"] in it.get("template_id", ""):
                        chosen_template = it["template_id"]
                        break

            # 2. 打开实验
            open_res = await self._call_tool(
                "open_experiment",
                {"template_id": chosen_template, "owner_id": "teacher_agent"},
            )
            exp_id = open_res["experiment_id"]
            r1_id = open_res["head_revision"]

            # 3. 探查场景
            await self._call_tool("inspect_scene", {"experiment_id": exp_id})

            return {
                "plan": plan,
                "template_id": chosen_template,
                "experiment_id": exp_id,
                "revisions": {
                    "initial_r1": r1_id,
                    "stage1_r2": r1_id,
                    "final_head": r1_id,
                },
                "phase1_edits": plan["phase1_edits"],
                "phase2_edits": plan["phase2_edits"],
                "views": plan["views"],
                "repair_attempts": 0,
                "repair_history": [],
            }

        async def execute_phase1(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            patch_err = None
            if state["phase1_edits"]:
                res = await self._call_tool(
                    "apply_scene_patch",
                    {"experiment_id": exp_id, "edits": state["phase1_edits"]},
                )
                if res.get("status", "").startswith("rejected"):
                    patch_err = res.get("status")

            views_res = {}
            if state["views"]:
                views_res = await self._call_tool(
                    "configure_teaching_views",
                    {"experiment_id": exp_id, "views": state["views"]},
                )
            return {
                "views_res": views_res.get("views_config", {}),
                "measurement_table": views_res.get("measurement_table"),
                "error": patch_err,
            }

        async def validate_phase1(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            if state.get("error"):
                val_res = {
                    "verdict": "failed",
                    "passed": False,
                    "checks": [
                        {
                            "id": "parameter_applied_focal_length",
                            "passed": False,
                            "expected": 50.0,
                            "detail": state.get("error"),
                        }
                    ],
                }
            else:
                val_res = await self._call_tool("run_validation", {"experiment_id": exp_id})
            return {"validation": val_res}

        def route_validate_phase1(state: ToolAgentState) -> str:
            val = state.get("validation", {})
            if val.get("passed"):
                return "publish_phase1"
            if state.get("repair_attempts", 0) < 3:
                return "repair_phase1"
            return "failure_exit"

        async def repair_phase1(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            val = state.get("validation", {})
            attempts = state.get("repair_attempts", 0) + 1
            history = list(state.get("repair_history", []))

            repaired_edits = []
            template = load_template(state.get("template_id", "optics.convex_lens"))
            ctrl_map = {c.parameter: c for c in template.controls}

            # 检查是否有越界或未生效的参数并按控制范围校准
            for p_edit in state.get("phase1_edits", []):
                param = p_edit.get("parameter")
                ctrl = ctrl_map.get(param)
                if ctrl:
                    val_req = float(p_edit.get("value", 0))
                    if val_req > ctrl.max or val_req < ctrl.min:
                        clamped = max(ctrl.min, min(ctrl.max, val_req))
                        repaired_edits.append({"entity_id": ctrl.entity_id, "parameter": param, "value": clamped})

            for check in val.get("checks", []):
                if not check.get("passed"):
                    cid = check.get("id", "")
                    if cid == "parameter_applied_focal_length":
                        ctrl = ctrl_map.get("focal_length_cm")
                        if ctrl and not any(e["parameter"] == "focal_length_cm" for e in repaired_edits):
                            val_req = float(check.get("expected", 12.0))
                            clamped = max(ctrl.min, min(ctrl.max, val_req))
                            repaired_edits.append({"entity_id": ctrl.entity_id, "parameter": "focal_length_cm", "value": clamped})
                    elif cid == "parameter_applied_object_distance":
                        ctrl = ctrl_map.get("object_distance_cm")
                        if ctrl and not any(e["parameter"] == "object_distance_cm" for e in repaired_edits):
                            val_req = float(check.get("expected", 30.0))
                            clamped = max(ctrl.min, min(ctrl.max, val_req))
                            repaired_edits.append({"entity_id": ctrl.entity_id, "parameter": "object_distance_cm", "value": clamped})

            if repaired_edits:
                await self._call_tool("apply_scene_patch", {"experiment_id": exp_id, "edits": repaired_edits})
                history.append({"attempt": attempts, "repaired_edits": repaired_edits})

            return {"repair_attempts": attempts, "repair_history": history, "error": None}

        async def publish_phase1(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            r1 = state["revisions"]["initial_r1"]
            pub_res = await self._call_tool(
                "publish_revision",
                {"experiment_id": exp_id, "base_revision": r1, "comment": "阶段一：参数与教学视图配置"},
            )
            r2 = pub_res["head_revision_id"]
            revs = dict(state["revisions"])
            revs["stage1_r2"] = r2
            revs["final_head"] = r2
            return {"revisions": revs}

        def route_publish_phase1(state: ToolAgentState) -> str:
            if state.get("phase2_edits"):
                return "execute_phase2"
            return "build_and_deliver"

        async def execute_phase2(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            await self._call_tool("apply_scene_patch", {"experiment_id": exp_id, "edits": state["phase2_edits"]})
            views_res = await self._call_tool(
                "configure_teaching_views",
                {"experiment_id": exp_id, "views": state["views"]},
            )
            return {
                "views_res": views_res.get("views_config", {}),
                "measurement_table": views_res.get("measurement_table"),
            }

        async def validate_phase2(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            val_res = await self._call_tool("run_validation", {"experiment_id": exp_id})
            return {"validation": val_res}

        def route_validate_phase2(state: ToolAgentState) -> str:
            val = state.get("validation", {})
            if val.get("passed"):
                return "publish_phase2"
            if state.get("repair_attempts", 0) < 3:
                return "repair_phase2"
            return "failure_exit"

        async def repair_phase2(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            attempts = state.get("repair_attempts", 0) + 1
            history = list(state.get("repair_history", []))
            template = load_template(state.get("template_id", "optics.convex_lens"))
            ctrl = next((c for c in template.controls if c.parameter == "object_distance_cm"), None)
            if ctrl:
                safe_edits = [{"entity_id": ctrl.entity_id, "parameter": "object_distance_cm", "value": 20.0}]
                await self._call_tool("apply_scene_patch", {"experiment_id": exp_id, "edits": safe_edits})
                history.append({"attempt": attempts, "repaired_edits": safe_edits})
            return {"repair_attempts": attempts, "repair_history": history}

        async def publish_phase2(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            r2 = state["revisions"]["stage1_r2"]
            pub_res = await self._call_tool(
                "publish_revision",
                {"experiment_id": exp_id, "base_revision": r2, "comment": "阶段二：连续编辑演进"},
            )
            r3 = pub_res["head_revision_id"]
            revs = dict(state["revisions"])
            revs["final_head"] = r3
            return {"revisions": revs}

        async def build_and_deliver(state: ToolAgentState) -> dict[str, Any]:
            exp_id = state["experiment_id"]
            build_res = await self._call_tool("build_package", {"experiment_id": exp_id, "export_offline_zip": True})
            return {
                "offline_package": build_res.get("offline_package"),
                "artifacts": build_res.get("artifacts"),
            }

        async def failure_exit(state: ToolAgentState) -> dict[str, Any]:
            return {"error": f"Validation failed after {state.get('repair_attempts', 0)} repairs"}

        graph.add_node("discover_and_open", discover_and_open)
        graph.add_node("execute_phase1", execute_phase1)
        graph.add_node("validate_phase1", validate_phase1)
        graph.add_node("repair_phase1", repair_phase1)
        graph.add_node("publish_phase1", publish_phase1)
        graph.add_node("execute_phase2", execute_phase2)
        graph.add_node("validate_phase2", validate_phase2)
        graph.add_node("repair_phase2", repair_phase2)
        graph.add_node("publish_phase2", publish_phase2)
        graph.add_node("build_and_deliver", build_and_deliver)
        graph.add_node("failure_exit", failure_exit)

        graph.add_edge(START, "discover_and_open")
        graph.add_edge("discover_and_open", "execute_phase1")
        graph.add_edge("execute_phase1", "validate_phase1")
        graph.add_conditional_edges("validate_phase1", route_validate_phase1, ["publish_phase1", "repair_phase1", "failure_exit"])
        graph.add_edge("repair_phase1", "validate_phase1")
        graph.add_conditional_edges("publish_phase1", route_publish_phase1, ["execute_phase2", "build_and_deliver"])
        graph.add_edge("execute_phase2", "validate_phase2")
        graph.add_conditional_edges("validate_phase2", route_validate_phase2, ["publish_phase2", "repair_phase2", "failure_exit"])
        graph.add_edge("repair_phase2", "validate_phase2")
        graph.add_edge("publish_phase2", "build_and_deliver")
        graph.add_edge("build_and_deliver", END)
        graph.add_edge("failure_exit", END)

        return graph.compile()

    async def run(self, prompt: str) -> dict[str, Any]:
        """执行完整的 LangGraph 自主工具调用与自愈循环。"""
        self.trace.clear()
        app = self._build_graph()
        final_state = await app.ainvoke({"prompt": prompt})

        return {
            "experiment_id": final_state.get("experiment_id"),
            "template_id": final_state.get("template_id"),
            "revisions": final_state.get("revisions", {}),
            "views": final_state.get("views_res"),
            "measurement_table": final_state.get("measurement_table"),
            "validation": final_state.get("validation", {}),
            "offline_package": final_state.get("offline_package"),
            "artifacts": final_state.get("artifacts"),
            "trace": [t.as_dict() for t in self.trace],
            "total_tool_calls": len(self.trace),
            "repair_attempts": final_state.get("repair_attempts", 0),
            "repair_history": final_state.get("repair_history", []),
            "error": final_state.get("error"),
        }
