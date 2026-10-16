"""已删除的正则意图解析器，原样保留作为**对照组**（不是产品代码）。

来源：`git show main:code/eduforge/python/src/eduforge/agent/tool_agent.py`
的第 144-186 行。留着它的唯一用途是让「Deep Agents 是不是真的比正则强」
这个问题有可执行的答案：同一批提示词，一边由模型决定调用，一边由模式匹配决定。
"""
from __future__ import annotations

import re
from typing import Any


def parse_teaching_instructions(prompt: str) -> dict[str, Any]:
    instructions: dict[str, Any] = {
        "query": "凸透镜",
        "template_id": "optics.convex_lens",
        "phase1_edits": [],
        "phase2_edits": [],
        "views": {},
    }
    if "两面镜" in prompt or "平面镜" in prompt:
        instructions["query"] = "平面镜"

    f_match = re.search(r"焦距(?:调整为|设为|为)?\s*(\d+(?:\.\d+)?)\s*cm", prompt)
    if f_match:
        instructions["phase1_edits"].append(
            {"entity_id": "lens_1", "parameter": "focal_length_cm", "value": float(f_match.group(1))}
        )

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
