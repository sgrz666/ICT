"""LangChain / LangGraph 兼容的实验引擎工具集封装。"""
from __future__ import annotations

from typing import Any
from langchain_core.tools import StructuredTool

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


def get_experiment_tools(service: ExperimentToolService) -> list[StructuredTool]:
    """获取所有 8 项实验引擎结构化工具。"""

    async def search_experiments_tool(query: str = "", template_id: str | None = None, limit: int = 10) -> dict[str, Any]:
        """检索可用的实验模板或已创建实验。"""
        out = await service.search_experiments(SearchExperimentsInput(query=query, template_id=template_id, limit=limit))
        return out.model_dump()

    async def open_experiment_tool(
        experiment_id: str | None = None,
        template_id: str | None = "optics.convex_lens",
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        """打开已有实验工作区或由模板初始化新实验。

        这里刻意没有 owner_id：归属来自服务端签发的 JobContext，
        模型能填身份就等于能把自己的实验写成别人的。
        """
        out = await service.open_experiment(
            OpenExperimentInput(
                experiment_id=experiment_id,
                template_id=template_id,
                revision_id=revision_id,
            )
        )
        return out.model_dump()

    async def inspect_scene_tool(experiment_id: str, revision_id: str | None = None) -> dict[str, Any]:
        """探查实验场景中的光学元件、物距像距物理参数与测量光路。"""
        out = await service.inspect_scene(InspectSceneInput(experiment_id=experiment_id, revision_id=revision_id))
        return out.model_dump()

    async def apply_scene_patch_tool(experiment_id: str, edits: list[dict[str, Any]] | dict[str, Any]) -> dict[str, Any]:
        """应用参数修改（如焦距 focal_length_cm, 物距 object_distance_cm）并执行真实光线追踪仿真。"""
        out = await service.apply_scene_patch(ApplyScenePatchInput(experiment_id=experiment_id, edits=edits))
        return out.model_dump()

    async def configure_teaching_views_tool(
        experiment_id: str, views: dict[str, Any] | list[dict[str, Any]]
    ) -> dict[str, Any]:
        """配置教学视图（如启用实验数据记录表格 measurement_table、光线追踪视图等）。"""
        out = await service.configure_teaching_views(
            ConfigureTeachingViewsInput(experiment_id=experiment_id, views=views)
        )
        return out.model_dump()

    async def run_validation_tool(experiment_id: str) -> dict[str, Any]:
        """执行科学规律检验与光学成像独立参考验证，检查是否满足物理规约。"""
        out = await service.run_validation(RunValidationInput(experiment_id=experiment_id))
        return out.model_dump()

    async def build_package_tool(experiment_id: str, export_offline_zip: bool = True) -> dict[str, Any]:
        """将验证合格的实验场景组装为独立可运行的离线网页包与版本产物。"""
        out = await service.build_package(
            BuildPackageInput(experiment_id=experiment_id, export_offline_zip=export_offline_zip)
        )
        return out.model_dump()

    async def publish_revision_tool(
        experiment_id: str, base_revision: str | None = None, comment: str = ""
    ) -> dict[str, Any]:
        """将候选版本原子发布为实验的最新修订版（更新 head_revision 指针）。"""
        out = await service.publish_revision(
            PublishRevisionInput(experiment_id=experiment_id, base_revision=base_revision, comment=comment)
        )
        return out.model_dump()

    return [
        StructuredTool.from_function(
            coroutine=search_experiments_tool,
            name="search_experiments",
            description="检索可用的物理实验模板或已有实验实例。",
            args_schema=SearchExperimentsInput,
        ),
        StructuredTool.from_function(
            coroutine=open_experiment_tool,
            name="open_experiment",
            description="打开已有实验或基于模板（如 optics.convex_lens）创建并载入工作区。",
            args_schema=OpenExperimentInput,
        ),
        StructuredTool.from_function(
            coroutine=inspect_scene_tool,
            name="inspect_scene",
            description="探查场景当前的光学元件（透镜、光源、光屏）、当前物理参数（焦距、物距）与测量读数。",
            args_schema=InspectSceneInput,
        ),
        StructuredTool.from_function(
            coroutine=apply_scene_patch_tool,
            name="apply_scene_patch",
            description="修改场景元件的物理参数（如 lens_1 的 focal_length_cm 或 object_1 的 object_distance_cm）并运行上游光线仿真。",
            args_schema=ApplyScenePatchInput,
        ),
        StructuredTool.from_function(
            coroutine=configure_teaching_views_tool,
            name="configure_teaching_views",
            description="配置教学与实验视图（例如开启 measurement_table 记录实验数据）。",
            args_schema=ConfigureTeachingViewsInput,
        ),
        StructuredTool.from_function(
            coroutine=run_validation_tool,
            name="run_validation",
            description="对当前修改执行物理规律与场景规约验证，返回各项检验指标与判定结论。",
            args_schema=RunValidationInput,
        ),
        StructuredTool.from_function(
            coroutine=build_package_tool,
            name="build_package",
            description="构建候选版本文件与离线可交互网页运行包（含 index.html 与静态资源）。",
            args_schema=BuildPackageInput,
        ),
        StructuredTool.from_function(
            coroutine=publish_revision_tool,
            name="publish_revision",
            description="将检验合格的候选版本原子发布，推进实验版本到新 head，支持后续连续编辑。",
            args_schema=PublishRevisionInput,
        ),
    ]
