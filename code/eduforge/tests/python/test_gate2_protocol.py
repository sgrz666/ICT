import math

import pytest
from pydantic import ValidationError

from eduforge.domain.contracts import EditProposal
from eduforge.validation.scientific.optics import thin_lens_reference


# --- 协议：route 互斥与数值健壮性（GATE-2 协议部分） ---

def test_normal_config_route():
    p = EditProposal.model_validate({
        "route": "config",
        "operations": [{
            "op": "set_parameter",
            "entity_id": "lens_1",
            "parameter": "focal_length_cm",
            "value": 15.0,
        }],
    })
    assert p.operations[0].entity_id == "lens_1"


def test_reject_nan_parameter():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({
            "route": "config",
            "operations": [{
                "op": "set_parameter",
                "entity_id": "lens_1",
                "parameter": "focal_length_cm",
                "value": float("nan"),
            }],
        })


def test_reject_infinite_parameter():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({
            "route": "config",
            "operations": [{
                "op": "set_parameter",
                "entity_id": "lens_1",
                "parameter": "focal_length_cm",
                "value": float("inf"),
            }],
        })


def test_reject_code_and_config_mixed():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({
            "route": "code",
            "code_task": "增加记录表",
            "operations": [{
                "op": "set_view",
                "view_id": "measurement_table",
                "visible": True,
            }],
        })


def test_reject_empty_config_operations():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({"route": "config", "operations": []})


def test_reject_model_supplied_identity_field():
    # 身份与归属由服务器构造，模型不得自带
    with pytest.raises(ValidationError):
        EditProposal.model_validate({
            "route": "config",
            "operations": [{
                "op": "set_parameter",
                "entity_id": "lens_1",
                "parameter": "focal_length_cm",
                "value": 15.0,
            }],
            "owner_id": "someone-else",
        })


def test_reject_unknown_operation_discriminator():
    with pytest.raises(ValidationError):
        EditProposal.model_validate({
            "route": "config",
            "operations": [{
                "op": "add_entity",
                "entity_id": "lens_2",
            }],
        })


# --- 独立参考：五档物距分层（GATE-2 分层部分） ---

@pytest.mark.parametrize("f,u,expected_v,kind", [
    (10, 5, -10.0, "virtual"),      # u < f
    (10, 15, 30.0, "real"),         # f < u < 2f
    (10, 20, 20.0, "real"),         # u = 2f
    (10, 60, 12.0, "real"),         # u > 2f
])
def test_reference_strata(f, u, expected_v, kind):
    r = thin_lens_reference(f, u)
    assert r["image_kind"] == kind
    assert math.isclose(r["image_distance_cm"], expected_v)


def test_reference_at_infinity():
    r = thin_lens_reference(10, 10)
    assert r["image_kind"] == "at_infinity"
    assert r["image_distance_cm"] is None
    assert r["magnification"] is None


def test_reference_rejects_nonpositive_focal_length():
    # 凹透镜（负焦距）不属于本模板；探针实测适配器侧同样拒绝
    with pytest.raises(ValueError):
        thin_lens_reference(-10, 30)
    with pytest.raises(ValueError):
        thin_lens_reference(0, 30)


def test_reference_rejects_nonfinite():
    with pytest.raises(ValueError):
        thin_lens_reference(float("nan"), 30)
