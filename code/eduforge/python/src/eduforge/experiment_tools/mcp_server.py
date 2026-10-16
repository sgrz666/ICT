"""Model Context Protocol (MCP) 服务器实现。

将 8 项实验引擎工具通过标准 MCP JSON-RPC 协议暴露，使任意支持 MCP 的 Agent
（如 Claude Desktop, Cursor, Deep Agents 等）可直接挂载调用。
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

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
from eduforge.experiment_tools.service import ExperimentToolService

TOOL_DEFINITIONS = [
    {
        "name": "search_experiments",
        "description": "检索可用的物理实验模板或已有实验实例。",
        "inputSchema": SearchExperimentsInput.model_json_schema(),
    },
    {
        "name": "open_experiment",
        "description": "打开已有实验或基于模板（如 optics.convex_lens）创建并载入工作区。",
        "inputSchema": OpenExperimentInput.model_json_schema(),
    },
    {
        "name": "inspect_scene",
        "description": "探查场景当前的光学元件（透镜、光源、光屏）、当前物理参数（焦距、物距）与测量读数。",
        "inputSchema": InspectSceneInput.model_json_schema(),
    },
    {
        "name": "apply_scene_patch",
        "description": "修改场景元件的物理参数（如 lens_1 的 focal_length_cm 或 object_1 的 object_distance_cm）并运行上游光线仿真。",
        "inputSchema": ApplyScenePatchInput.model_json_schema(),
    },
    {
        "name": "configure_teaching_views",
        "description": "配置教学与实验视图（例如开启 measurement_table 记录实验数据）。",
        "inputSchema": ConfigureTeachingViewsInput.model_json_schema(),
    },
    {
        "name": "run_validation",
        "description": "对当前修改执行物理规律与场景规约验证，返回各项检验指标与判定结论。",
        "inputSchema": RunValidationInput.model_json_schema(),
    },
    {
        "name": "build_package",
        "description": "构建候选版本文件与离线可交互网页运行包（含 index.html 与静态资源）。",
        "inputSchema": BuildPackageInput.model_json_schema(),
    },
    {
        "name": "publish_revision",
        "description": "将检验合格的候选版本原子发布，推进实验版本到新 head，支持后续连续编辑。",
        "inputSchema": PublishRevisionInput.model_json_schema(),
    },
]


async def dispatch_tool_call(service: ExperimentToolService, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "search_experiments":
        res = await service.search_experiments(SearchExperimentsInput.model_validate(arguments))
        return res.model_dump()
    elif name == "open_experiment":
        res = await service.open_experiment(OpenExperimentInput.model_validate(arguments))
        return res.model_dump()
    elif name == "inspect_scene":
        res = await service.inspect_scene(InspectSceneInput.model_validate(arguments))
        return res.model_dump()
    elif name == "apply_scene_patch":
        res = await service.apply_scene_patch(ApplyScenePatchInput.model_validate(arguments))
        return res.model_dump()
    elif name == "configure_teaching_views":
        res = await service.configure_teaching_views(ConfigureTeachingViewsInput.model_validate(arguments))
        return res.model_dump()
    elif name == "run_validation":
        res = await service.run_validation(RunValidationInput.model_validate(arguments))
        return res.model_dump()
    elif name == "build_package":
        res = await service.build_package(BuildPackageInput.model_validate(arguments))
        return res.model_dump()
    elif name == "publish_revision":
        res = await service.publish_revision(PublishRevisionInput.model_validate(arguments))
        return res.model_dump()
    else:
        raise ValueError(f"未知工具: {name}")


async def handle_mcp_message(msg: dict[str, Any], service: ExperimentToolService) -> dict[str, Any]:
    """处理 MCP JSON-RPC 请求。"""
    msg_id = msg.get("id")
    method = msg.get("method")
    params = msg.get("params", {})

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": TOOL_DEFINITIONS},
        }
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            result = await dispatch_tool_call(service, tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {exc}"}],
                    "isError": True,
                },
            }
    elif method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "eduforge-mcp-server", "version": "0.1.0"},
            },
        }
    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


async def run_mcp_stdio(service: ExperimentToolService) -> None:
    """运行 MCP stdio 监听循环。"""
    while True:
        line = await asyncio.to_thread(sys.stdin.readline)
        if not line:
            break
        try:
            req = json.loads(line)
            resp = await handle_mcp_message(req, service)
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as exc:
            sys.stderr.write(f"MCP loop error: {exc}\n")
            sys.stderr.flush()
