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

身份与执行权不在这里：`owner_id`/`job_id`/`lease_token` 由服务端签发的
`JobContext` 注入（见 service.py）。工具入参一律继承 `Contract`
（`extra="forbid"`），模型多吐一个身份字段就应当失败，和 `domain/contracts.py`
同一条纪律。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import Field

from eduforge.domain.contracts import Contract


@dataclass(frozen=True)
class JobContext:
    """服务端签发的执行上下文。

    工具层没有任何一条路径可以让模型改写它：归属、job、租约三者都来自
    API 中间件与 Worker 领取到的 lease_token。
    `experiment_id`/`base_revision` 一旦绑定，就是这个 job 的作用域边界——
    智能体不能顺手去开别的实验，也不能拿别的版本当基础。
    """

    job_id: UUID
    owner_id: str
    lease_token: str
    experiment_id: UUID | None = None
    base_revision: UUID | None = None


class SearchExperimentsInput(Contract):
    query: str = Field(default="", description="搜索关键词，如'凸透镜'、'convex lens'")
    template_id: str | None = Field(default=None, description="可选过滤模板ID，如'optics.convex_lens'")
    limit: int = Field(default=10, description="返回条数上限")


class ExperimentSummary(Contract):
    experiment_id: str | None = None
    template_id: str
    title: str
    description: str = ""
    controls: list[dict[str, Any]] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)


class SearchExperimentsOutput(Contract):
    items: list[ExperimentSummary]
    total: int


class OpenExperimentInput(Contract):
    experiment_id: str | None = Field(default=None, description="已有实验ID；若为空则基于 template_id 创建或打开模板")
    template_id: str | None = Field(default="optics.convex_lens", description="模板ID，默认凸透镜实验")
    revision_id: str | None = Field(default=None, description="指定版本ID，默认打开 head 版本")


class OpenExperimentOutput(Contract):
    experiment_id: str
    template_id: str
    base_revision: str
    head_revision: str
    controls: list[dict[str, Any]] = Field(default_factory=list)
    views: list[str] = Field(default_factory=list)
    native_summary: dict[str, Any] = Field(default_factory=dict)


class InspectSceneInput(Contract):
    experiment_id: str = Field(description="目标实验ID")
    revision_id: str | None = Field(default=None, description="指定查看版本，默认当前工作态/head")


class SceneInspectionOutput(Contract):
    experiment_id: str
    revision_id: str
    elements: list[dict[str, Any]] = Field(default_factory=list, description="场景内物理实体列表")
    parameters: dict[str, Any] = Field(default_factory=dict, description="当前关键物理参数（如物距、焦距）")
    optics_metrics: dict[str, Any] = Field(default_factory=dict, description="高斯光学理论指标（像距、虚实正倒放大）")
    ray_count: int = Field(default=0, description="仿真光线跟踪数量")
    probes: list[dict[str, Any]] = Field(default_factory=list, description="探测屏测量读数")


class ApplyScenePatchInput(Contract):
    experiment_id: str = Field(description="目标实验ID")
    edits: list[dict[str, Any]] | dict[str, Any] = Field(
        description="参数修改列表或单项修改，如 [{'entity_id':'lens_1','parameter':'focal_length_cm','value':12.0}]"
    )


class ApplyScenePatchOutput(Contract):
    experiment_id: str
    applied_edits: list[dict[str, Any]]
    updated_parameters: dict[str, Any]
    ray_count: int
    probes: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "applied"


class ConfigureTeachingViewsInput(Contract):
    experiment_id: str = Field(description="目标实验ID")
    views: dict[str, Any] | list[dict[str, Any]] = Field(
        description="教学视图配置，如 {'measurement_table': True} 或 [{'view_id': 'measurement_table', 'visible': True}]"
    )


class ConfigureTeachingViewsOutput(Contract):
    experiment_id: str
    views_config: dict[str, Any]
    measurement_table: dict[str, Any] | None = None


class RunValidationInput(Contract):
    experiment_id: str = Field(description="目标实验ID")


class RunValidationOutput(Contract):
    experiment_id: str
    verdict: str
    passed: bool
    checks: list[dict[str, Any]] = Field(default_factory=list)
    physics_summary: dict[str, Any] = Field(default_factory=dict)


class BuildPackageInput(Contract):
    experiment_id: str = Field(description="目标实验ID")
    export_offline_zip: bool = Field(default=True, description="是否导出完整离线可运行网页包")


class BuildPackageOutput(Contract):
    experiment_id: str
    candidate_revision_id: str
    artifacts: list[dict[str, Any]]
    offline_package: dict[str, Any] | None = None
    sha256: str


class PublishRevisionInput(Contract):
    experiment_id: str = Field(description="目标实验ID")
    base_revision: str | None = Field(
        default=None, description="期望的基础版本ID（乐观并发前置条件），不传则用会话当前 head"
    )
    comment: str = Field(default="", description="发布说明")


class PublishRevisionOutput(Contract):
    experiment_id: str
    head_revision_id: str
    base_revision: str
    artifact_id: str
    sha256: str
    status: str = "published"
