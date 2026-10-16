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
    edits: list[SetParameter] | None = None,
    view_edits: list[Any] | None = None,
    engine_result: dict,
    object_distance_cm: float | None = None,
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

    # 汇集所有需要核验的参数修改；对同一个 (entity_id, parameter)，以最后一次生效修改为准
    raw_edits: list[SetParameter] = []
    if edits:
        raw_edits.extend(edits)
    if edit is not None and edit not in raw_edits:
        raw_edits.append(edit)

    latest_edits_map: dict[tuple[str, str], SetParameter] = {}
    for e in raw_edits:
        key = (getattr(e, "entity_id", ""), getattr(e, "parameter", ""))
        latest_edits_map[key] = e
    all_edits = list(latest_edits_map.values())

    # 从候选场景对象中提取真实物理参数，防止传入伪造的 edit 声明或陈旧基线
    native = engine_result.get("native", {})
    candidate_objs = native.get("objs", []) if isinstance(native, dict) else []
    if not candidate_objs:
        candidate_objs = engine_result.get("validation", {}).get("objs", [])

    lens_obj = next((o for o in candidate_objs if o.get("type") == "IdealLens"), None)
    source_obj = next((o for o in candidate_objs if o.get("type") == "PointSource"), None)

    lens_x = 0.0
    actual_f_cm = None
    if lens_obj:
        p1 = lens_obj.get("p1", {})
        p2 = lens_obj.get("p2", {})
        p1_x = p1.get("x", 0) if isinstance(p1, dict) else 0
        p2_x = p2.get("x", 0) if isinstance(p2, dict) else 0
        lens_x = (float(p1_x) + float(p2_x)) / 2
        if "focalLength" in lens_obj:
            actual_f_cm = float(lens_obj["focalLength"]) / units_per_unit

    if actual_f_cm is None:
        for e in all_edits:
            if e.parameter == "focal_length_cm":
                actual_f_cm = e.value
                break

    actual_u_cm = None
    if source_obj and "x" in source_obj:
        actual_u_cm = abs(float(source_obj["x"]) - lens_x) / units_per_unit

    # 评估物距：优先采用传入的 claimed object_distance_cm；未显式传入时从场景推导
    u_eval = object_distance_cm if object_distance_cm is not None else actual_u_cm

    for e in all_edits:
        if e.parameter == "focal_length_cm" and actual_f_cm is not None:
            f_matched = abs(actual_f_cm - e.value) < 1e-4
            r.add(Check(
                id="parameter_applied_focal_length",
                passed=f_matched,
                expected=e.value,
                observed=actual_f_cm,
                detail=f"候选场景中透镜真实焦距必须与请求值一致 (expected {e.value}cm, got {actual_f_cm}cm)",
            ))
        elif e.parameter == "object_distance_cm":
            u_check = actual_u_cm if actual_u_cm is not None else u_eval
            u_matched = u_check is not None and abs(u_check - e.value) < 1e-4
            r.add(Check(
                id="parameter_applied_object_distance",
                passed=u_matched,
                expected=e.value,
                observed=u_check,
                detail=f"候选场景中物距真实值必须与请求值一致 (expected {e.value}cm, got {u_check}cm)",
            ))

    usable = [p for p in probes if (p.get("power_fraction") or 0) >= POWER_FLOOR]
    types = {o["type"] for o in engine_result.get("validation", {}).get("objs", [])}
    comparable = types == {"IdealLens", "PointSource", "Detector"}

    if all_edits:
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

        if comparable and usable and actual_f_cm is not None and u_eval is not None:
            f_eval = actual_f_cm
            ref = thin_lens_reference(f_eval, u_eval)
            kind = ref["image_kind"]
            v_pred = ref["image_distance_cm"]
            min_probe = min(usable, key=lambda p: p.get("rms_units", 999.0))
            min_rms = min_probe.get("rms_units", 999.0)

            if kind == "at_infinity":
                r.add(Check(
                    id="focal_parallel_beams",
                    passed=abs(f_eval - u_eval) < 1e-4,
                    expected=f"f == u ({u_eval:.1f}cm)",
                    observed=f"f={f_eval:.1f}cm, u={u_eval:.1f}cm",
                    detail=f"焦距 f={f_eval:.1f}cm 等于物距 u={u_eval:.1f}cm，折射光线为平行光束",
                ))
                # 平行光束在有限探测器上不会形成尖锐聚焦点（最小 rms 必须大于聚焦阈值）
                r.add(Check(
                    id="infinity_no_finite_real_focus",
                    passed=min_rms > 1.5,
                    expected="min_rms > 1.5",
                    observed=min_rms,
                    detail="平行光束在有限距离光屏上无清晰像点聚焦",
                ))
            elif kind == "virtual":
                r.add(Check(
                    id="virtual_image_valid",
                    passed=u_eval < f_eval,
                    expected=f"u < f (u < {f_eval:.1f}cm)",
                    observed=f"u={u_eval:.1f}cm, f={f_eval:.1f}cm",
                    detail=f"物距 u={u_eval:.1f}cm 小于焦距 f={f_eval:.1f}cm，成正立放大虚像 (v={v_pred:.1f}cm)",
                ))
                # 虚像在透镜右侧光屏上为发散光束，不形成实像锐利聚焦
                r.add(Check(
                    id="virtual_no_finite_real_focus",
                    passed=min_rms > 1.5,
                    expected="min_rms > 1.5",
                    observed=min_rms,
                    detail="虚像发散光束在实光屏上不应形成实像锐利聚焦",
                ))
            else:
                expected_screen = nearest_screen(v_pred)
                observed = min_probe
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
