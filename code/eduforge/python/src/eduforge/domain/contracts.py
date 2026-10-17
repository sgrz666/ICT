from datetime import datetime
from typing import Any, Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    # extra=forbid 是刻意的：模型多吐一个身份字段就必须失败，
    # 不能让它自己决定实验归属或基础版本。
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SetParameter(Contract):
    op: Literal["set_parameter"] = "set_parameter"
    # entity_id 对应上游场景对象的 name 字段，不是数组下标。
    # 下标绑定已实测否决：Scene.reorderObj 会重排、Editor 拖动时 unshiftObj 插队首、
    # removeObj 让后续前移；且 knownKeys 白名单禁止注入自定义 id。
    entity_id: str = Field(min_length=1, max_length=80)
    parameter: str = Field(min_length=1, max_length=80)
    value: float


class SetView(Contract):
    op: Literal["set_view"] = "set_view"
    view_id: str = Field(min_length=1, max_length=80)
    visible: bool


Operation = Annotated[
    SetParameter | SetView,
    Field(discriminator="op"),
]


class EditProposal(Contract):
    route: Literal["config", "code"]
    operations: list[Operation] = Field(default_factory=list, max_length=32)
    code_task: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def check_route(self):
        if self.route == "config":
            if not self.operations or self.code_task is not None:
                raise ValueError("config requires operations only")
        elif self.operations or not self.code_task or not self.code_task.strip():
            raise ValueError("code requires a non-empty code_task only")
        return self


class PlannerRequest(Contract):
    job_id: UUID
    experiment_id: UUID
    base_revision: UUID
    # 服务端从 experiments 行取来，规划上下文按它装载；模型无权改它
    template_id: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=4000)
    feedback: list[str] = Field(default_factory=list, max_length=32)


EngineId = Literal["ray_optics", "myphysicslab", "circuitjs"]


class WorkOrder(Contract):
    job_id: UUID
    experiment_id: UUID
    base_revision: UUID
    engine_id: EngineId
    proposal: EditProposal


class CreateJobRequest(Contract):
    experiment_id: UUID
    base_revision: UUID
    prompt: str = Field(min_length=1, max_length=4000)


# 五个状态都有落库路径：queued=create_job，running=claim，succeeded=publish，
# cancelled=cancel，failed=Worker 的终态分支（worker/main.py 的 mark_failed）。
# 新增状态时必须同时改这里，否则响应校验会拒掉新状态而不是静默放过。
JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]


class JobAccepted(Contract):
    job_id: UUID
    # 首次提交恒为 queued；幂等重放返回已存在任务的当前状态，五种都可能。
    status: JobStatus


# ---- 响应契约（§6.1/§6.2）---------------------------------------------------
# 这些模型同时是 FastAPI 的 response_model 和 TS 类型的唯一来源。
# 不加 response_model 的话 OpenAPI 里只有 dict，前端只能手写第二套 DTO，
# "类型由后端生成"就变成空话。extra=forbid 在这里还多兼一层：
# 将来有人往响应里塞 owner_id 之类的身份字段，直接失败而不是泄漏出去。


class ControlSummary(Contract):
    """一个可调控件的教学元数据。量程来自清单，前端不复制第二份。"""

    entity_id: str
    parameter: str
    label: str
    unit: str
    min: float
    max: float
    initial: float | None


class TemplateSummary(Contract):
    template_id: str
    title: str
    engine_id: EngineId
    units_per_unit: int
    routes: list[str]
    views: list[str]
    controls: list[ControlSummary]
    native_file: str


class TemplateList(Contract):
    templates: list[TemplateSummary]


class ExperimentCreated(Contract):
    experiment_id: UUID
    base_revision: UUID
    template_id: str


class ExperimentDetail(Contract):
    experiment_id: UUID
    template_id: str
    head_revision: UUID | None
    revision_count: int
    revisions: list[UUID]


class RollbackRequest(Contract):
    target_revision_id: UUID


class RevisionSummary(Contract):
    revision_id: UUID
    parent_id: UUID | None
    engine_id: str
    created_at: datetime


class RevisionList(Contract):
    revisions: list[RevisionSummary]


class JobEvent(Contract):
    sequence: int
    stage: str | None
    event_type: str


class JobView(Contract):
    job_id: UUID
    status: JobStatus
    stage: str | None
    error_code: str | None
    candidate_revision_id: UUID | None
    events: list[JobEvent]


class ArtifactSummary(Contract):
    artifact_id: UUID
    media_type: str
    sha256: str
    storage_key: str


class RevisionArtifacts(Contract):
    """前端要先拿到产物才能下载与预览。

    sha256 一起给出去是有意的：客户端应当自己重算并比对，
    而不是只信服务端响应头里那一个数。
    """

    revision_id: UUID
    artifacts: list[ArtifactSummary]


class RevisionViews(Contract):
    """版本的教学视图配置：发布时写进 `experiment_revisions.lesson` 的那一份。

    §C.3 的出口。前端只有读到它，才知道教师勾了哪些视图、记录表该有哪些列和行——
    以前这些数据只存在于库和产物文件里，界面一个字都不显示。
    """

    revision_id: UUID
    views: dict[str, Any]


class JobCancelled(Contract):
    job_id: UUID
    # 202 分支只会返回 cancelled：succeeded 走 409，queued/running 被 CASE 改写。
    status: Literal["cancelled"]


class ApiErrorDetail(Contract):
    code: str


class ApiErrorResponse(Contract):
    """错误体统一为 {"detail": {"code": ...}}：状态语义由 HTTP 码承担，不重复编码。"""

    detail: ApiErrorDetail
