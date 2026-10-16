"""实验引擎工具服务契约定义。

对齐 8 项工具契约：
1. search_experiments
2. open_experiment
3. inspect_scene
4. apply_scene_patch
5. configure_teaching_views
6. run_validation
7. build_package
8. publish_revision
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class SearchExperimentsInput(BaseModel):
    query: str = Field(default="", description="搜索关键词，如'凸透镜'、'convex lens'")
    template_id: str | None = Field(default=None, description="可选过滤模板ID，如'optics.convex_lens'")
    limit: int = Field(default=10, description="返回条数上限")


class ExperimentSummary(BaseModel):
    experiment_id: str | None = None
    template_id: str
    title: str
    description: str = ""
    controls: list[dict[str, Any]] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)


class SearchExperimentsOutput(BaseModel):
    items: list[ExperimentSummary]
    total: int


class OpenExperimentInput(BaseModel):
    experiment_id: str | None = Field(default=None, description="已有实验ID；若为空则基于 template_id 创建或打开模板")
    template_id: str | None = Field(default="optics.convex_lens", description="模板ID，默认凸透镜实验")
    revision_id: str | None = Field(default=None, description="指定版本ID，默认打开 head 版本")
    owner_id: str = Field(default="teacher_agent", description="归属用户ID")


class OpenExperimentOutput(BaseModel):
    experiment_id: str
    template_id: str
    base_revision: str
    head_revision: str
    controls: list[dict[str, Any]] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)
    native_summary: dict[str, Any] = Field(default_factory=dict)


class InspectSceneInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")
    revision_id: str | None = Field(default=None, description="指定查看版本，默认当前工作态/head")


class SceneInspectionOutput(BaseModel):
    experiment_id: str
    revision_id: str
    elements: list[dict[str, Any]] = Field(default_factory=list, description="场景内物理实体列表")
    parameters: dict[str, Any] = Field(default_factory=dict, description="当前关键物理参数（如物距、焦距）")
    optics_metrics: dict[str, Any] = Field(default_factory=dict, description="高斯光学理论指标（像距、虚实正倒放大）")
    ray_count: int = Field(default=0, description="仿真光线跟踪数量")
    probes: list[dict[str, Any]] = Field(default_factory=list, description="探测屏测量读数")


class ApplyScenePatchInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")
    edits: list[dict[str, Any]] | dict[str, Any] = Field(
        description="参数修改列表或单项修改，如 [{'entity_id':'lens_1','parameter':'focal_length_cm','value':12.0}]"
    )


class ApplyScenePatchOutput(BaseModel):
    experiment_id: str
    applied_edits: list[dict[str, Any]]
    updated_parameters: dict[str, Any]
    ray_count: int
    probes: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "applied"


class ConfigureTeachingViewsInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")
    views: dict[str, Any] | list[dict[str, Any]] = Field(
        description="教学视图配置，如 {'measurement_table': True} 或 [{'view_id': 'measurement_table', 'visible': True}]"
    )


class ConfigureTeachingViewsOutput(BaseModel):
    experiment_id: str
    views_config: dict[str, Any]
    measurement_table: dict[str, Any] | None = None


class RunValidationInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")


class RunValidationOutput(BaseModel):
    experiment_id: str
    verdict: str
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    physics_summary: dict[str, Any] = Field(default_factory=dict)


class BuildPackageInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")
    export_offline_zip: bool = Field(default=True, description="是否导出完整离线可运行网页包")


class BuildPackageOutput(BaseModel):
    experiment_id: str
    candidate_revision_id: str
    artifacts: list[dict[str, Any]]
    offline_package: dict[str, Any] | None = None
    sha256: str


class PublishRevisionInput(BaseModel):
    experiment_id: str = Field(description="目标实验ID")
    base_revision: str | None = Field(default=None, description="基础版本ID，不传则使用当前 head_revision")
    comment: str = Field(default="", description="发布说明")


class PublishRevisionOutput(BaseModel):
    experiment_id: str
    head_revision_id: str
    base_revision: str
    artifact_id: str
    sha256: str
    status: str = "published"
