"""策略校验：把模型给的 EditProposal 变成可信 WorkOrder，或拒掉。

§4.3 的七步顺序固定，且**顺序本身就是防线**：先确认对象与参数在清单里登记过，
再确认量程与单位，最后才由服务器补上身份字段。模型永远不能自己决定实验归属。
检索到的文档内容不得扩大工具权限（清单里没有就是没有）。
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from eduforge.infrastructure.catalog import (
    CatalogError,
    TemplateSpec,
    load_template as _load_template,
)
from eduforge.domain.contracts import (
    EditProposal,
    PlannerRequest,
    SetParameter,
    SetView,
    WorkOrder,
)

def load_template(template_id: str) -> TemplateSpec:
    """对策略层而言，清单读不到与模板不存在是同一类拒绝。"""
    try:
        return _load_template(template_id)
    except CatalogError as e:
        raise Rejected(e.code, e.detail) from e


class Rejected(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail



def authorize(
    request: PlannerRequest,
    template: TemplateSpec,
    proposal: EditProposal,
) -> WorkOrder:
    # 0) 请求声明的模板必须就是装载出来这份模板。
    # 不是形式检查：上下文装载与量程判定必须同源，否则"用 A 的量程放行、按 B 编辑"能绕过登记表。
    if request.template_id != template.template_id:
        raise Rejected("TEMPLATE_MISMATCH", f"{request.template_id} != {template.template_id}")
    # 1) route 必须是模板支持的路径
    if proposal.route == "config" and not template.supports_config:
        raise Rejected("ROUTE_NOT_SUPPORTED", "config")
    if proposal.route == "code" and not template.supports_code:
        raise Rejected("ROUTE_NOT_SUPPORTED", "code")

    for op in proposal.operations:
        if isinstance(op, SetParameter):
            # 2) 对象与参数必须登记过
            spec = next(
                (c for c in template.controls
                 if c.entity_id == op.entity_id and c.parameter == op.parameter),
                None,
            )
            if spec is None:
                raise Rejected("PARAMETER_NOT_REGISTERED", f"{op.entity_id}.{op.parameter}")
            # 3) 数值/单位/量程符合清单（NaN 与 Infinity 在协议层已被拦下）
            if not (spec.min <= op.value <= spec.max):
                raise Rejected("VALUE_OUT_OF_RANGE", f"{op.value} not in [{spec.min}, {spec.max}]")
        elif isinstance(op, SetView):
            # 4) 视图必须存在
            if op.view_id not in template.views:
                raise Rejected("VIEW_NOT_REGISTERED", op.view_id)

    # 5) 代码路径的范围只能由清单的能力决定，不由模型自述决定
    if proposal.route == "code" and proposal.code_task:
        if len(proposal.code_task) > 4000:
            raise Rejected("CODE_TASK_TOO_LONG")

    # 6) 身份字段由服务器补，模型给的任何身份都不作数（协议层已 forbid）
    return WorkOrder(
        job_id=request.job_id,
        experiment_id=request.experiment_id,
        base_revision=request.base_revision,
        engine_id=template.engine_id,  # type: ignore[arg-type]
        proposal=proposal,
    )
