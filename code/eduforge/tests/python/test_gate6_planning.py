"""GATE-6 的无密钥部分：规划图 + 策略校验链。

用桩模型替代 DeepSeek，验的是"模型越界时链条会不会挡住"，
不是"模型答得好不好"（那要有 Key 之后的对照评测）。
"""
import asyncio
import uuid

import pytest
from pydantic import ValidationError

from eduforge.agent.graph import build_planning_graph
from eduforge.agent.policy import Rejected, authorize, load_template
from eduforge.agent.services import PlanningServices
from eduforge.domain.contracts import EditProposal, PlannerRequest

TEMPLATE = "optics.convex_lens"


def make_request(prompt="把焦距改成 15 厘米") -> PlannerRequest:
    return PlannerRequest(
        job_id=uuid.uuid4(), experiment_id=uuid.uuid4(),
        base_revision=uuid.uuid4(), template_id=TEMPLATE, prompt=prompt,
    )


def run_graph(model_output):
    async def model(prompt, context, evidence):
        return model_output

    services = PlanningServices(model, template_of=lambda _r: TEMPLATE)
    graph = build_planning_graph(services)
    req = make_request()
    return asyncio.run(graph.ainvoke({"request": req}, config={"recursion_limit": 12})), req


def test_valid_config_edit_becomes_work_order_with_server_identity():
    out, req = run_graph({
        "route": "config",
        "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                        "parameter": "focal_length_cm", "value": 15.0}],
    })
    wo = out["work_order"]
    assert wo.engine_id == "ray_optics"
    # 身份与归属来自请求，不来自模型
    assert wo.job_id == req.job_id
    assert wo.experiment_id == req.experiment_id
    assert wo.base_revision == req.base_revision
    assert wo.proposal.operations[0].value == 15.0


def test_out_of_range_value_rejected():
    with pytest.raises(Rejected) as e:
        run_graph({
            "route": "config",
            "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                            "parameter": "focal_length_cm", "value": 999.0}],
        })
    assert e.value.code == "VALUE_OUT_OF_RANGE"


def test_unregistered_parameter_rejected():
    with pytest.raises(Rejected) as e:
        run_graph({
            "route": "config",
            "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                            "parameter": "refractive_index", "value": 1.5}],
        })
    assert e.value.code == "PARAMETER_NOT_REGISTERED"


def test_unregistered_view_rejected():
    with pytest.raises(Rejected) as e:
        run_graph({
            "route": "config",
            "operations": [{"op": "set_view", "view_id": "secret_panel", "visible": True}],
        })
    assert e.value.code == "VIEW_NOT_REGISTERED"


def test_template_mismatch_rejected():
    """量程判定与上下文装载必须同源。

    请求说 A、模板取来 B 就放行，等于"按 A 的量程判、往 B 上改"，
    登记表那道闸门形同虚设。
    """
    req = make_request()
    other = load_template(TEMPLATE)
    other.template_id = "optics.other_lens"
    proposal = EditProposal(route="config", operations=[
        {"op": "set_parameter", "entity_id": "lens_1",
         "parameter": "focal_length_cm", "value": 15.0}])
    with pytest.raises(Rejected) as exc:
        authorize(req, other, proposal)
    assert exc.value.code == "TEMPLATE_MISMATCH"


def test_registered_view_accepted():
    out, _ = run_graph({
        "route": "config",
        "operations": [{"op": "set_view", "view_id": "measurement_table", "visible": True}],
    })
    assert out["work_order"].proposal.operations[0].view_id == "measurement_table"


def test_model_extra_identity_field_rejected_by_protocol():
    """模型自作主张带上 owner_id / experiment_id 时，协议层就拒，进不到策略层。"""
    with pytest.raises(ValidationError):
        run_graph({
            "route": "config",
            "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                            "parameter": "focal_length_cm", "value": 15.0}],
            "owner_id": "someone-else",
        })


def test_mixed_route_rejected():
    with pytest.raises(ValidationError):
        run_graph({
            "route": "code",
            "code_task": "加一块屏",
            "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                            "parameter": "focal_length_cm", "value": 15.0}],
        })


def test_non_numeric_value_rejected():
    with pytest.raises(ValidationError):
        run_graph({
            "route": "config",
            "operations": [{"op": "set_parameter", "entity_id": "lens_1",
                            "parameter": "focal_length_cm", "value": "十五"}],
        })


def test_code_route_produces_work_order_without_operations():
    out, _ = run_graph({"route": "code", "code_task": "增加不同物距下的成像记录表"})
    wo = out["work_order"]
    assert wo.proposal.route == "code"
    assert wo.proposal.operations == []


def test_template_spec_single_source_of_truth():
    """量程只有清单一个出处，策略与适配器都从这里取。"""
    spec = load_template(TEMPLATE)
    assert spec.units_per_unit == 10
    lens = [c for c in spec.controls if c.entity_id == "lens_1"][0]
    assert (lens.min, lens.max) == (5.0, 50.0)
    assert "measurement_table" in spec.views
    with pytest.raises(Rejected) as e:
        load_template("no.such.template")
    assert e.value.code == "TEMPLATE_NOT_FOUND"
