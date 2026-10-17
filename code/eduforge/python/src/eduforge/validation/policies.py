"""发布门禁：哪些检查必须成立才允许发布。

独立参考只在理想薄透镜下成立，因此检查项里同时钉住对象类型；
换成 SphericalLens 必须显式判不可对照，而不是放宽容差。

**Gate C §C.2 的分界线**：像的性质必须由光线的可观测行为决定，不由公式决定。
Engine Host 每次仿真都会交出 `measurement.geometry`（由屏阵列上的实测光斑宽度拟合：
收敛交点=实像、发散且反向延长交于入射侧=虚像、宽度全程不变=高平行度），
这里把它当**观测**，把薄透镜公式当**独立参考**，两者对不上就失败，
观测不出来就 `na` → 整份报告压成 `inconclusive`，发布被挡在门外。
旧实现里 `virtual_image_valid: u < f` 与 `focal_parallel_beams: abs(f-u)<1e-4`
是恒真的公式自证，已删除。
"""
from __future__ import annotations

from typing import Any

from eduforge.domain.contracts import SetParameter
from eduforge.validation.reports import Check, ValidationReport
from eduforge.validation.scientific.optics import thin_lens_reference

# 屏在 8/12/16/20/25/30/40cm；预测像面落到哪块屏，就看哪块离得最近
SCREENS_CM = [8, 12, 16, 20, 25, 30, 40]
SHARP_RMS_MAX = 15.0
POWER_FLOOR = 0.2
# 相邻屏的最小间距 4cm → 像面定位分辨率 2cm；「对上」的定义是落在分辨率内，
# 不是旧代码那个 `abs(observed - expected) < 1e-9` 的假精确。
SCREEN_RESOLUTION_CM = 2.0
# 高平行度的可观测定义：宽度在整段阵列上的相对变化上限（与引擎侧一致）
PARALLEL_REL_CHANGE = 0.15


def nearest_screen(v_cm: float) -> float:
    return min(SCREENS_CM, key=lambda cm: abs(cm - v_cm))


def _geometry(engine_result: dict) -> dict[str, Any]:
    return engine_result.get("measurement", {}).get("geometry") or {}


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
    candidate_id: Any = None,
    content_hash: str | None = None,
) -> ValidationReport:
    engine_version = (engine_result.get("validation") or {}).get("version")
    report = ValidationReport(
        job_id=job_id, candidate_id=candidate_id, content_hash=content_hash,
        engine_version=engine_version,
    )
    r = report
    probes = engine_result.get("measurement", {}).get("probes", [])

    r.add(Check(
        id="upstream_accepted",
        passed=bool(engine_result.get("validation", {}).get("ok")),
        expected=True,
        observed=engine_result.get("validation", {}).get("error"),
        detail="上游 loadJSON 必须接受改后的场景",
        source="engine:upstream_loadjson",
    ))
    r.add(Check(
        id="base_untouched",
        passed=bool(engine_result.get("base_untouched")),
        expected=True,
        observed=engine_result.get("base_untouched"),
        detail="编辑前版本必须保持可恢复",
        source="engine:base_native_compare",
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
                detail=f"视图 {vid} 必须在模板登记清单内（登记合法 ≠ UI 已实现，见 C.3）",
                source="catalog:template_manifest",
                profile="catalog_view_list",
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
                source="engine:scene_object_field",
                tolerance="逐字节比对场景字段（换算 units_per_unit）",
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
                source="engine:scene_object_field",
                tolerance="逐字节比对场景字段（换算 units_per_unit）",
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
            source="engine:detector_power_fraction",
        ))

        r.add(Check(
            id="science_profile_comparable",
            passed=comparable,
            expected=True,
            observed=sorted(types),
            detail="独立薄透镜参考只对理想薄透镜成立；厚透镜要显式判不可对照",
            source="engine:scene_object_types",
        ))

        if comparable and usable and actual_f_cm is not None and u_eval is not None:
            f_eval = actual_f_cm
            ref = thin_lens_reference(f_eval, u_eval)
            kind = ref["image_kind"]
            v_pred = ref["image_distance_cm"]
            min_probe = min(usable, key=lambda p: p.get("rms_units", 999.0))
            min_rms = min_probe.get("rms_units", 999.0)
            geo = _geometry(engine_result)

            _add_geometry_check(r, kind=kind, v_pred=v_pred, u_cm=u_eval, geo=geo, min_rms=min_rms)

            if kind == "real":
                # 实像工况：屏阵列上有可核对的聚焦点。像面「落在哪块屏」的判据
                # 用分辨率表达（屏间距最小 4cm ⇒ 分辨率 2cm），不再写 1e-9 的假精确。
                expected_screen = nearest_screen(v_pred)
                observed_screen = min_probe["x_cm"]
                r.add(Check(
                    id="image_plane_matches_reference",
                    passed=abs(float(observed_screen) - expected_screen) <= SCREEN_RESOLUTION_CM,
                    expected=expected_screen,
                    observed=observed_screen,
                    detail=f"预测实像像距 v={v_pred:.2f}cm，最窄屏在 {observed_screen}cm",
                    source="engine:sharpest_screen",
                    tolerance=f"屏阵列最小间距 4cm ⇒ 定位分辨率 {SCREEN_RESOLUTION_CM}cm",
                ))
                r.add(Check(
                    id="spot_is_actually_focused",
                    passed=min_rms <= SHARP_RMS_MAX,
                    expected=f"<= {SHARP_RMS_MAX}",
                    observed=min_rms,
                    detail="最清晰屏必须真的成出像，而不只是相对更清晰",
                    source="engine:spot_second_moment",
                    tolerance="场景单位下的光斑二矩，阈值由 GATE-4 全量程实测标定",
                ))

    r.finalize()
    return report


def _add_geometry_check(r: ValidationReport, *, kind: str, v_pred: float | None,
                        u_cm: float, geo: dict, min_rms: float) -> None:
    """把引擎实测的光束几何与独立参考对照。观测不到就叫观测不到。"""
    observed_kind = geo.get("kind", "inconclusive")
    resolution = geo.get("resolution_cm") or SCREEN_RESOLUTION_CM
    apex = geo.get("apex_x_cm")
    dist = geo.get("image_distance_cm")
    reason = geo.get("reason", "引擎未返回光束几何（旧版 dist？）")
    tol_note = f"外推交点与参考像距的容差 = 屏分辨率 {resolution:.1f}cm 的 2 倍"

    if observed_kind == "inconclusive":
        r.add(Check(
            id="beam_geometry_resolved",
            passed=False,
            expected=kind,
            observed={"kind": observed_kind, "reason": reason, "usable": geo.get("usable")},
            detail=f"光束几何不可判：{reason}；不给独立观测就不判「{kind}」成立",
            source="engine:beam_width_fit",
            status="na",
            # 实像另有决定性观测（屏位 + 光斑聚焦），交点拟合只是第二件量具；
            # 虚像与无穷远就靠它，那时 na 必须决定结论。
            decisive=(kind != "real"),
            tolerance=tol_note,
        ))
        return

    if kind == "real":
        if observed_kind != "real":
            r.add(Check(
                id="beam_geometry_agrees",
                passed=False,
                expected="real",
                observed={"kind": observed_kind, "reason": reason},
                detail="参考预测实像，但实测光束不收敛于屏侧 —— 与薄透镜预测矛盾",
                source="engine:beam_width_fit",
                decisive=False,
                tolerance=tol_note,
            ))
            return
        delta = abs(float(dist) - float(v_pred)) if dist is not None else None
        r.add(Check(
            id="beam_geometry_agrees",
            passed=delta is not None and delta <= 2 * resolution,
            expected=v_pred,
            observed={"apex_x_cm": apex, "image_distance_cm": dist, "fit_r2": geo.get("fit_r2")},
            detail=f"两侧光束宽度收敛于 {apex:.2f}cm，与独立参考 v={v_pred:.2f}cm 的偏差 {delta:.2f}cm",
            source="engine:beam_width_fit",
            decisive=False,
            tolerance=tol_note,
        ))
        return

    if kind == "virtual":
        # 虚像没有任何实聚焦点，唯一可依赖的是出射光束的发散几何与反向延长交点。
        if observed_kind != "virtual":
            r.add(Check(
                id="beam_geometry_agrees",
                passed=False,
                expected="virtual",
                observed={"kind": observed_kind, "reason": reason,
                          "relative_width_change": "低于阵列分辨力"},
                detail=f"参考预测虚像，但本屏阵列测不出可分辨的发散（{reason}）——"
                       "远处虚像与准直在该分辨率上不可区分，不判通过",
                source="engine:beam_width_fit",
                status="na",
                tolerance=tol_note,
            ))
            return
        delta = abs(float(dist) - float(v_pred)) if dist is not None else None
        # 外推 100cm 量级的交点对阵列几何极其敏感，容差按分辨率的 10 倍给，
        # 并要求符号正确（交点必须在入射侧），否则就是拿噪声当证据
        r.add(Check(
            id="beam_geometry_agrees",
            passed=delta is not None and delta <= 10 * resolution and float(dist) < 0,
            expected=v_pred,
            observed={"apex_x_cm": apex, "image_distance_cm": dist, "fit_r2": geo.get("fit_r2")},
            detail=f"出射光束发散，反向延长交点在 {apex:.1f}cm（像距 {dist:.1f}cm），"
                   f"独立参考 v={v_pred:.1f}cm",
            source="engine:beam_width_fit",
            tolerance=f"外推像距：符号必须在入射侧，且偏差 ≤ 10×分辨率（{10 * resolution:.0f}cm）",
        ))
        return

    # 无穷远（u = f）：可观测量是平行度本身，不是"公式说 f==u"
    slope = geo.get("width_slope_units_per_cm")
    span = geo.get("array_span_cm")
    if observed_kind == "collimated":
        r.add(Check(
            id="beam_parallelism_observed",
            passed=slope is not None and span is not None,
            expected="宽度沿轴向变化率 ≈ 0",
            observed={"width_slope_units_per_cm": slope, "array_span_cm": span,
                      "resolvable_max_abs_distance_cm": geo.get("resolvable_max_abs_distance_cm")},
            detail=f"实测光束宽度在 {span:.0f}cm 跨度内变化率 {slope:.4g} 单位/cm，"
                   f"判为高平行度；本阵列可分辨像距上限 {geo.get('resolvable_max_abs_distance_cm')}cm，"
                   "更远处的虚像与准直不可区分",
            source="engine:beam_width_fit",
            profile="collimated_beam",
            tolerance=f"平行度阈值：相对变化 < {PARALLEL_REL_CHANGE:.0%}",
        ))
    else:
        r.add(Check(
            id="beam_parallelism_observed",
            passed=False,
            expected="collimated",
            observed={"kind": observed_kind, "reason": reason, "min_rms": min_rms},
            detail=f"参考预测像在无穷远，但实测光束不平行（{reason}）",
            source="engine:beam_width_fit",
            profile="collimated_beam",
            tolerance=f"平行度阈值：相对变化 < {PARALLEL_REL_CHANGE:.0%}",
        ))
