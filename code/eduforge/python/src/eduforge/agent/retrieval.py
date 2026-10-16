"""实验能力与教学依据检索服务。

对齐方案 §1.2 和 §4.2：
- 从实验模板（manifest.yaml、native.json 等）检索可调参数、视图与物理约束；
- 从已登记的教学依据和领域规范中提取相关提示与错误规避规则；
- 确保输入给模型的证据只来自受控目录，避免幻觉。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class EvidenceRetriever:
    """可信教学实验依据检索器。"""

    def __init__(self, templates_root: Path | None = None):
        if templates_root is None:
            # 默认为 code/eduforge/catalog/templates
            templates_root = Path(__file__).resolve().parents[4] / "catalog" / "templates"
        self.templates_root = templates_root

    def retrieve_evidence(
        self,
        prompt: str,
        template_id: str,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """根据教师需求和模板上下文检索相关依据。"""
        evidence: list[dict[str, Any]] = []

        manifest_path = self.templates_root / template_id / "manifest.yaml"
        if manifest_path.exists():
            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
                controls = manifest.get("controls", [])
                views = manifest.get("views", [])
                
                # 注入受控参数清单
                if controls:
                    evidence.append({
                        "type": "allowed_parameters",
                        "controls": controls,
                        "description": "可调整参数与取值范围",
                    })

                # 注入受控视图清单
                if views:
                    evidence.append({
                        "type": "allowed_views",
                        "views": views,
                        "description": "受控开关视图列表",
                    })

                # 提取教学提示
                notes = manifest.get("pedagogical_notes", [])
                if notes:
                    evidence.append({
                        "type": "pedagogical_notes",
                        "notes": notes,
                        "description": "教学约束与科学依据",
                    })
            except Exception:
                pass

        # 针对常见提示词匹配特定教学说明
        lower = prompt.lower()
        if "焦距" in prompt or "focal" in lower:
            evidence.append({
                "type": "domain_rule",
                "topic": "focal_length",
                "rule": "凸透镜焦距必须大于0，理想范围通常在 5cm 到 50cm 之间。",
            })
        if "虚像" in prompt or "放大镜" in prompt:
            evidence.append({
                "type": "domain_rule",
                "topic": "virtual_image",
                "rule": "物距小于焦距 (u < f) 时成正立、放大的虚像。",
            })

        return evidence
