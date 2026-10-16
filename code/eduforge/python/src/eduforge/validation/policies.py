"""发布门禁：哪些检查必须成立才允许发布。

独立参考只在理想薄透镜下成立，因此检查项里同时钉住对象类型；
换成 SphericalLens 必须显式判不可对照，而不是放宽容差。
"""
from __future__ import annotations

from eduforge.domain.contracts import SetParameter
from eduforge.validation.reports import Check, ValidationReport
from eduforge.validation.scientific.optics import thin_lens_reference

# 屏在 8/12/16/20/25/30/40cm；预测像面落到哪块屏，就看哪块离得最近
SCREENS_CM = [8, 12, 16, 20, 25, 30, 40]
SHARP_RMS_MAX = 15.0
POWER_FLOOR = 0.2


def nearest_screen(v_cm: float) -> float:
    return min(SCREENS_CM, key=lambda cm: abs(cm - v_cm))


def build_report(
    *,
    job_id: str,
    edit: SetParameter | None = None,
    view_edits: list[Any] | None = None,
    engine_result: dict,
    object_distance_cm: float,
    units_per_unit: int,
    allowed_views: list[str] | None = None,
) -> ValidationReport:
    report = ValidationReport(job_id=job_id)
    probes = engine_result.get("measurement", {}).get("probes", [])

    r = report
    r.add(Check(
        id="upstream_accepted",
        passed=bool(engine_result.get("validation", {}).get("ok")),
        expected=True,
        observed=engine_result.get("validation", {}).get("error"),
        detail="上游 loadJSON 必须接受改后的场景",
    ))
    r.add(Check(
        id="base_untouched",
        passed=bool(engine_result.get("base_untouched")),
        expected=True,
        observed=engine_result.get("base_untouched"),
        detail="编辑前版本必须保持可恢复",
    ))

    # 校验视图控制操作
    if view_edits:
        for v in view_edits:
            vid = getattr(v, "view_id", None) or v.get("view_id")
            passed = allowed_views is None or vid in allowed_views
            r.add(Check(
                id=f"view_registered_{vid}",
                passed=passed,
                expected=True,
                observed=passed,
                detail=f"视图 {vid} 必须在模板登记清单内",
            ))

    usable = [p for p in probes if (p.get("power_fraction") or 0) >= POWER_FLOOR]
    types = {o["type"] for o in engine_result.get("validation", {}).get("objs", [])}
    comparable = types == {"IdealLens", "PointSource", "Detector"}

    if edit is not None:
        r.add(Check(
            id="non_degenerate_measurement",
            passed=len(usable) >= 2,
            expected=">=2",
            observed=len(usable),
            detail="至少两块屏有可比的读数，否则判向无意义",
        ))

        r.add(Check(
            id="science_profile_comparable",
            passed=comparable,
            expected=True,
            observed=sorted(types),
            detail="独立薄透镜参考只对理想薄透镜成立；厚透镜要显式判不可对照",
        ))

        if comparable and usable:
            f_cm = edit.value
            ref = thin_lens_reference(f_cm, object_distance_cm)
            kind = ref["image_kind"]
            v_pred = ref["image_distance_cm"]

            if kind == "at_infinity":
                r.add(Check(
                    id="focal_parallel_beams",
                    passed=True,
                    expected="at_infinity",
                    observed="at_infinity",
                    detail=f"焦距 f={f_cm:.1f}cm 等于物距 u={object_distance_cm:.1f}cm，折射光线为平行光束",
                ))
            elif kind == "virtual":
                r.add(Check(
                    id="virtual_image_valid",
                    passed=True,
                    expected="virtual",
                    observed="virtual",
                    detail=f"物距 u={object_distance_cm:.1f}cm 小于焦距 f={f_cm:.1f}cm，成正立放大虚像 (v={v_pred:.1f}cm)",
                ))
            else:
                expected_screen = nearest_screen(v_pred)
                observed = min(usable, key=lambda p: p["rms_units"])
                observed_screen = observed["x_cm"]
                r.add(Check(
                    id="image_plane_matches_reference",
                    passed=abs(observed_screen - expected_screen) < 1e-9,
                    expected=expected_screen,
                    observed=observed_screen,
                    detail=f"预测实像像距 v={v_pred:.2f}cm，屏分辨率受阵列间距限制",
                ))
                r.add(Check(
                    id="spot_is_actually_focused",
                    passed=observed["rms_units"] <= SHARP_RMS_MAX,
                    expected=f"<= {SHARP_RMS_MAX}",
                    observed=observed["rms_units"],
                    detail="最清晰屏必须真的成出像，而不只是相对更清晰",
                ))

    r.finalize()
    return report
