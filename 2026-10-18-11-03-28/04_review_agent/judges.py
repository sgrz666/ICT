# -*- coding: utf-8 -*-
"""
judges.py —— J1–J8 学科判据的独立实现（《界面设计+审查判据》3.1–3.3）

三条原则写在最前面，改代码前请先读：

1. **独立性**（规范 3.2 注意事项 1）
   页面自己说"守恒成立"不算证据。凡是从页面读来的布尔值（__DATA__.checks），
   一律只标 review，不计入通过；必须由本文件用独立算法重算一遍才判 pass。

2. **容差按量纲走**（注意事项 2）
   体积、角度、电流的容差不同。统一用 JUDGE_TOL 里的相对/绝对误差，不搞"一律 5%"。

3. **不适用不等于通过**（注意事项 3、5）
   页面没有几何量、没有统计量时返回 skip，不计入分母，而不是白送分。
   没有可审核事实（J8）/没有注册场景（J6）时返回 review，交教师判断，不伪造结论。
"""

import math
import re

from registry import JUDGES, scene_of

# ---------------------------------------------------------------- 容差

JUDGE_TOL = {
    "角度": {"绝对": 0.6},
    "长度": {"相对": 0.02, "绝对": 0.01},
    "面积": {"相对": 0.02, "绝对": 0.001},
    "体积": {"相对": 0.02, "绝对": 0.002},
    "数值": {"相对": 0.02, "绝对": 0.01},
    "统计": {"相对": 0.03, "绝对": 0.01},
    "计数": {"绝对": 0},
}


def within(expect, actual, kind="数值"):
    """按量纲判断两个数是否一致。"""
    tol = JUDGE_TOL.get(kind, JUDGE_TOL["数值"])
    if actual is None or expect is None:
        return False
    if "绝对" in tol and "相对" not in tol:
        return abs(expect - actual) <= tol["绝对"]
    rel = tol.get("相对", 0.02)
    ab = tol.get("绝对", 0.0)
    return abs(expect - actual) <= max(ab, abs(expect) * rel)


def num_of(x):
    """从 '2.00 N'、'0.6A'、'55°' 这类文本里取出数字。"""
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?", str(x or ""))
    return float(m.group(0)) if m else None


def mk(judge, cid, name, status, expected, actual, message,
       evidence="", advice="", severity="major", weight=0):
    """统一的一条审查记录，字段对齐规范 3.4 的报告要求。"""
    return {
        "check_id": cid,
        "gate": "G3",
        "gate_name": "学科判据",
        "judge": judge,
        "judge_name": JUDGES.get(judge, {}).get("名称", ""),
        "name": name,
        "status": status,           # pass / fail / review / skip
        "severity": severity,
        "weight": weight,
        "expected": expected,
        "actual": actual,
        "message": message,
        "evidence": evidence,
        "advice": advice,
    }


# ================================================================ J1 数值复算

def j1_numeric(ctx):
    out = []
    # 没有浏览器就没有代入式与滑块读数：这一判据整体不适用，不能判失败
    if ctx.get("br") is None:
        return [mk("J1", "J1-00", "J1 数值复算", "skip",
                   "由浏览器取回页面上的代入式与滑块范围后复算",
                   "未执行浏览器检查",
                   "静态条件下拿不到渲染后的数字，J1 无法判定", weight=8)]
    br = ctx.get("br") or {}
    formula = br.get("formula") or {}
    items = formula.get("checks") or []
    profile = ctx.get("profile") or {}
    text = ctx.get("text") or ""
    advice_formula = "把核心公式写成带数值的代入式：" + profile.get(
        "公式示例", "公式 = 数值代入 = 结果（每项带单位）")

    # J1-01 首屏代入式：算得对不对
    if not items:
        out.append(mk("J1", "J1-01", "J1 代入式可复算", "fail",
                      "页面可见「公式 = 数值 = 结果」的完整代入过程",
                      "页面上没有解析出可复算的代入式",
                      "拿不到可复算的数值，数值维度的正确性无法证明",
                      advice=advice_formula, severity="critical", weight=8))
    else:
        bad = [c for c in items if not c.get("ok")]
        sample = items[0]
        if bad:
            b = bad[0]
            out.append(mk("J1", "J1-01", "J1 代入式可复算", "fail",
                          "按公式独立重算后与显示值一致",
                          "「%s」显示 %s，独立重算应为 %s（共 %d 组不一致）"
                          % (b["text"], b["显示"], b["应为"], len(bad)),
                          "代入式的算术结果与显示值不符，学生会照着一个错数学习",
                          evidence="；".join("「%s」=%s≠%s" % (x["text"], x["显示"], x["应为"])
                                            for x in bad[:3]),
                          advice=advice_formula, severity="critical", weight=8))
        else:
            out.append(mk("J1", "J1-01", "J1 代入式可复算", "pass",
                          "按公式独立重算后与显示值一致",
                          "%d 组代入式全部复算通过" % len(items),
                          "页面数值与独立复算一致",
                          evidence=sample["text"], weight=8))

    # J1-02 极值下仍自洽（参数拉到端点后重算）
    extreme = [c for c in items if c.get("阶段") == "极值"]
    if not extreme:
        out.append(mk("J1", "J1-02", "J1 极值下仍自洽", "skip",
                      "参数取端点时代入式仍成立",
                      "页面没有可拖动参数，或极值状态未产生新的代入式",
                      "无参数可拖，本项不适用", weight=4))
    else:
        bad = [c for c in extreme if not c.get("ok")]
        if bad:
            b = bad[0]
            out.append(mk("J1", "J1-02", "J1 极值下仍自洽", "fail",
                          "参数取端点时代入式仍成立",
                          "极值处 %d 组不一致，例如「%s」显示 %s，应为 %s"
                          % (len(bad), b["text"], b["显示"], b["应为"]),
                          "参数变化后读数没有跟着重算，常见原因是只在初始化时算了一次",
                          advice="每次参数变化都走同一个 render()，读数、画布、代入式同源",
                          severity="major", weight=4))
        else:
            out.append(mk("J1", "J1-02", "J1 极值下仍自洽", "pass",
                          "参数取端点时代入式仍成立",
                          "%d 组极值状态复算通过" % len(extreme),
                          "极值端点的数值仍自洽", weight=4))

    # J1-03 单位标注完整
    groups = profile.get("单位组") or []
    if not groups:
        out.append(mk("J1", "J1-03", "J1 单位标注完整", "skip",
                      "关键读数带单位", "该主题未配置单位组",
                      "主题未识别，单位检查不适用", weight=3))
    else:
        miss = [label for label, aliases in groups if not any(a in text for a in aliases)]
        out.append(mk("J1", "J1-03", "J1 单位标注完整", "pass" if not miss else "fail",
                      "、".join(label for label, _ in groups) + " 均带单位",
                      "缺失单位：%s" % "、".join(miss) if miss else "单位齐全",
                      "读数缺单位，学生无法判断量纲" if miss else "关键读数均带单位",
                      advice="为每个读数和公式项补上单位，且与知识库中的器材规格一致",
                      severity="major", weight=3))

    # J1-04 值域与除零（规范 3.2 示例：R=0 须禁止除零）
    bounds = (br.get("ranges") or {}).get("bounds") or []
    problems = []
    for b in bounds:
        lo, hi, val = b.get("min"), b.get("max"), b.get("value")
        if lo is None or hi is None or lo >= hi:
            problems.append("滑块「%s」范围非法（%s–%s）" % (b.get("名称", ""), lo, hi))
        elif val is not None and not (lo <= val <= hi):
            problems.append("滑块「%s」初值 %s 不在 %s–%s 内" % (b.get("名称", ""), val, lo, hi))
    if re.search(r"[÷/]\s*0(?:\.0+)?(?![.\d])", text):
        problems.append("页面出现除数为 0 的代入式")
    if not bounds:
        out.append(mk("J1", "J1-04", "J1 值域与除零", "skip",
                      "参数上下限有效、不出现除零",
                      "页面没有滑块，参数值域不适用", "无参数控件，本项不适用", weight=3))
    else:
        out.append(mk("J1", "J1-04", "J1 值域与除零", "pass" if not problems else "fail",
                      "参数上下限有效、不出现除零",
                      "；".join(problems) if problems else "%d 个滑块范围与初值均合法" % len(bounds),
                      "参数越界或除零会让实验在边界处崩溃" if problems else "参数值域合法",
                      advice="在 setParams 里做上下界校验，除数为 0 时给出提示而不是直接计算",
                      severity="major", weight=3))
    return out


# ================================================================ J2 几何复算

def _geo(ctx):
    return ((ctx.get("machine") or {}).get("GEO")
            or (ctx.get("machine") or {}).get("DATA", {}).get("geometry") or {})


def j2_geometry(ctx):
    out = []
    geo = _geo(ctx) or {}
    text = ctx.get("text") or ""
    checked = 0
    fails = []

    # J2-01 三角形内角和 / 多边形外角和
    angles = geo.get("angles") or geo.get("内角")
    if isinstance(angles, list) and len(angles) >= 3:
        checked += 1
        s = sum(num_of(a) or 0 for a in angles)
        need = 180.0 if len(angles) == 3 else (len(angles) - 2) * 180.0
        if not within(need, s, "角度"):
            fails.append("内角和 %s°，应为 %s°" % (round(s, 2), need))

    # J2-02 反射角 = 入射角（文本级，适用于光学页）
    m_in = re.search(r"入射角\s*[为是=:：]?\s*(\d+(?:\.\d+)?)\s*°", text)
    m_out = re.search(r"反射角\s*[为是=:：]?\s*(\d+(?:\.\d+)?)\s*°", text)
    if m_in and m_out:
        checked += 1
        a, b = float(m_in.group(1)), float(m_out.group(1))
        if not within(a, b, "角度"):
            fails.append("入射角 %s° 与反射角 %s° 不相等" % (a, b))

    # J2-03 顶点坐标与显示长度一致
    pts = geo.get("points")
    lens = geo.get("lengths")
    if isinstance(pts, list) and len(pts) >= 2 and isinstance(lens, list) and lens:
        try:
            p0, p1 = pts[0], pts[1]
            d = math.dist([float(p0["x"]), float(p0["y"])], [float(p1["x"]), float(p1["y"])])
            checked += 1
            if not within(d, num_of(lens[0]), "长度"):
                fails.append("两点距离重算 %.3f，页面显示 %s" % (d, lens[0]))
        except (KeyError, TypeError, ValueError):
            pass

    # J2-04 太阳高度角：H = 90 - |纬度 - 直射纬度|
    lat, decl, alt = geo.get("lat"), geo.get("decl"), geo.get("altitude")
    if lat is not None and decl is not None and alt is not None:
        checked += 1
        need = 90 - abs(num_of(lat) - num_of(decl))
        if not within(need, num_of(alt), "角度"):
            fails.append("太阳高度角显示 %s°，按 90−|%s−%s| 应为 %.2f°"
                         % (alt, lat, decl, need))

    # J2-05 边界与数值合理性
    area = num_of(geo.get("area"))
    if area is not None:
        checked += 1
        if area <= 0:
            fails.append("面积重算为非正数（%s）" % area)

    # J2-06 勾股定理：直角三角形 a² + b² = c²
    data = (ctx.get("machine") or {}).get("DATA") or {}
    src_p = geo if (geo.get("c") is not None or geo.get("hyp") is not None) else data
    ga = num_of(src_p.get("leg_a") if src_p.get("leg_a") is not None else src_p.get("a"))
    gb = num_of(src_p.get("leg_b") if src_p.get("leg_b") is not None else src_p.get("b"))
    gc = num_of(src_p.get("hyp") if src_p.get("hyp") is not None else src_p.get("c"))
    is_pyth = ("勾股" in text or "直角三角形" in text or "弦图" in text
               or (ctx.get("scene") or {}).get("id") == "pythagoras_area"
               or src_p.get("hyp") is not None or src_p.get("leg_a") is not None)
    if is_pyth and ga is not None and gb is not None and gc is not None and ga > 0 and gb > 0 and gc > 0:
        checked += 1
        lhs = ga * ga + gb * gb
        rhs = gc * gc
        if abs(lhs - rhs) > max(0.05, 0.02 * rhs):
            fails.append("勾股关系不成立：a²+b²=%.3f，c²=%.3f（a=%s, b=%s, c=%s）"
                         % (lhs, rhs, ga, gb, gc))

    # J2-07 杠杆平衡力矩关系：F1·L1 = F2·L2（当处于平衡态或未显式标注失衡时）
    src_lv = geo if (geo.get("F1") is not None or geo.get("L1") is not None) else data
    if isinstance(src_lv.get("params"), dict) and src_lv.get("F1") is None:
        src_lv = dict(src_lv, **src_lv["params"], **(src_lv.get("result") or {}))
    f1 = num_of(src_lv.get("F1") if src_lv.get("F1") is not None else src_lv.get("f1"))
    l1 = num_of(src_lv.get("L1") if src_lv.get("L1") is not None else src_lv.get("l1"))
    f2 = num_of(src_lv.get("F2") if src_lv.get("F2") is not None else src_lv.get("f2"))
    l2 = num_of(src_lv.get("L2") if src_lv.get("L2") is not None else src_lv.get("l2"))
    if None not in (f1, l1, f2, l2):
        checked += 1
        m1, m2 = f1 * l1, f2 * l2
        rep_m1 = num_of(src_lv.get("M1") if src_lv.get("M1") is not None else src_lv.get("torque1"))
        rep_m2 = num_of(src_lv.get("M2") if src_lv.get("M2") is not None else src_lv.get("torque2"))
        if rep_m1 is not None and abs(rep_m1 - m1) > max(0.05, 0.02 * abs(m1)):
            fails.append("左端力矩 M1 显示 %s，按 F1·L1 重算应为 %.2f" % (rep_m1, m1))
        if rep_m2 is not None and abs(rep_m2 - m2) > max(0.05, 0.02 * abs(m2)):
            fails.append("右端力矩 M2 显示 %s，按 F2·L2 重算应为 %.2f" % (rep_m2, m2))
        bal = src_lv.get("balanced")
        if bal is True and abs(m1 - m2) > max(0.05, 0.02 * max(abs(m1), abs(m2), 1.0)):
            fails.append("页面标记杠杆平衡，但 F1·L1=%.2f ≠ F2·L2=%.2f" % (m1, m2))
        elif bal is False and abs(m1 - m2) <= 1e-4:
            fails.append("F1·L1=%.2f 等于 F2·L2=%.2f，页面却标记为不平衡" % (m1, m2))

    # J2-08 正午太阳高度与日影长：L = h / tan(H)
    sh_h = num_of(geo.get("pole_h") if geo.get("pole_h") is not None else data.get("pole_h"))
    sh_alt = num_of(geo.get("altitude") if geo.get("altitude") is not None else data.get("altitude"))
    sh_len = num_of(geo.get("shadow") if geo.get("shadow") is not None else data.get("shadow"))
    if None not in (sh_h, sh_alt, sh_len) and 1.0 <= sh_alt < 89.9 and sh_h > 0:
        checked += 1
        need_len = sh_h / math.tan(math.radians(sh_alt))
        if abs(need_len - sh_len) > max(0.08, 0.03 * need_len):
            fails.append("影长显示 %s，按 h/tan(H) 重算应为 %.2f" % (sh_len, need_len))

    if not checked:
        out.append(mk("J2", "J2-01", "J2 几何量可复算", "skip",
                      "页面暴露可复算的几何量（角度/坐标/长度）",
                      "未在 __GEO__ 或页面文本中找到几何约束",
                      "本页没有可复算的几何关系，J2 不适用", weight=6))
        return out

    out.append(mk("J2", "J2-01", "J2 几何复算", "pass" if not fails else "fail",
                  "几何约束（内角和/反射角/距离/高度角）独立重算成立",
                  "；".join(fails) if fails else "%d 项几何约束复算通过" % checked,
                  "几何关系与独立重算不符，画面看着对但数值是错的" if fails else "几何量自洽",
                  evidence="；".join(fails[:3]), severity="critical" if fails else "major",
                  advice="几何量必须由同一套坐标/角度计算得出，不要为画面好看单独写死数值",
                  weight=6))
    return out


# ================================================================ J3 计数与守恒

def j3_conservation(ctx):
    out = []
    data = (ctx.get("machine") or {}).get("DATA") or {}
    text = ctx.get("text") or ""
    checked, fails, reviews = 0, [], []

    # J3-01 原子/元素计数守恒（化学）
    atoms = data.get("atoms") or data.get("原子数")
    if isinstance(atoms, dict) and atoms.get("left") and atoms.get("right"):
        checked += 1
        for el in set(atoms["left"]) | set(atoms["right"]):
            l, r = atoms["left"].get(el, 0), atoms["right"].get(el, 0)
            if l != r:
                fails.append("%s 原子不守恒（左 %s / 右 %s）" % (el, l, r))

    # J3-02 前后数量相等（颗粒、细胞数、样本数）
    counts = data.get("counts") or {}
    if isinstance(counts, dict) and "before" in counts and "after" in counts:
        checked += 1
        if counts["before"] != counts["after"]:
            fails.append("前后计数不等（%s → %s）" % (counts["before"], counts["after"]))

    # J3-03 概率/比例之和为 1（遗传棋盘、分布）
    probs = data.get("probabilities") or data.get("概率")
    if isinstance(probs, list) and probs:
        checked += 1
        s = sum(num_of(p) or 0 for p in probs)
        if not within(1.0, s, "统计"):
            fails.append("概率之和为 %.4f，应为 1" % s)

    # J3-04 遗传比例（1:2:1 / 3:1）
    ratio = data.get("ratio") or data.get("比例")
    if isinstance(ratio, (list, str)):
        checked += 1
        nums = [num_of(x) for x in (ratio if isinstance(ratio, list) else re.split(r"[:：]", ratio))]
        nums = [n for n in nums if n is not None]
        if len(nums) == 3:
            if not (within(1, nums[0], "计数") and within(2, nums[1], "计数") and within(1, nums[2], "计数")):
                fails.append("基因型比 %s 不是 1:2:1" % ratio)
        elif len(nums) == 2:
            if not (within(3, nums[0], "计数") and within(1, nums[1], "计数")):
                fails.append("表现型比 %s 不是 3:1" % ratio)

    # J3-05 页面自报的守恒布尔：独立性不足，只能转人工
    page_checks = data.get("checks") or {}
    if isinstance(page_checks, dict):
        self_reported = {k: v for k, v in page_checks.items() if "守恒" in str(k) or "相等" in str(k)}
        if self_reported:
            reviews.append("页面自报 %s；按规范 3.2，模型自报不作为独立校验证据"
                           % "、".join("%s=%s" % (k, v) for k, v in self_reported.items()))
            if any(v is False for v in self_reported.values()):
                fails.append("页面自报守恒不成立：%s"
                             % "、".join(k for k, v in self_reported.items() if v is False))

    if not checked and not reviews:
        out.append(mk("J3", "J3-01", "J3 计数与守恒", "skip",
                      "原子数/计数/概率前后一致", "未在 __DATA__ 中找到可计数的量",
                      "本页无计数类可复算量，J3 不适用", weight=6))
        return out

    if fails:
        out.append(mk("J3", "J3-01", "J3 计数与守恒", "fail",
                      "原子数/计数/概率前后一致", "；".join(fails),
                      "守恒关系不成立，或页面自报不成立",
                      evidence="；".join(fails[:3]), severity="critical",
                      advice="把反应物与产物的元素计数同时写出并逐元素比对，不要只显示总量",
                      weight=6))
    elif checked:
        out.append(mk("J3", "J3-01", "J3 计数与守恒", "pass",
                      "原子数/计数/概率前后一致", "%d 项守恒独立复算通过" % checked,
                      "守恒关系成立", weight=6))
    if reviews:
        out.append(mk("J3", "J3-02", "J3 自报结果需人工确认", "review",
                      "守恒结论应由外部独立复算，而非页面自报",
                      "；".join(reviews),
                      "页面自报的校验结果不能作为通过依据", weight=0))
    return out


# ================================================================ J4 空间拓扑

def j4_topology(ctx):
    out = []
    geo = _geo(ctx) or {}
    text = ctx.get("text") or ""
    checked, fails = 0, []

    # J4-01 体积可加（截面把体分成两块）
    v_up, v_down = num_of(geo.get("v_up")), num_of(geo.get("v_down"))
    total = num_of(geo.get("v_total") or geo.get("volume"))
    if v_up is not None and v_down is not None:
        checked += 1
        target = total if total is not None else 1.0
        if not within(target, v_up + v_down, "体积"):
            fails.append("两段体积之和 %.4f，应为 %.4f" % (v_up + v_down, target))
        if v_up < -1e-6 or v_down < -1e-6:
            fails.append("出现负体积（%.4f / %.4f）" % (v_up, v_down))

    # J4-02 截面边数合法性（正方体最多 6 边）
    #
    # 只有本页确实是「三维截面」页才校验 sides。函数页也常往 __GEO__ 里写
    # sides —— 二次函数页把它当成「与 x 轴交点个数」，合法值是 0/1/2，
    # 拿 3–6 去卡必然误杀，还会被判成 critical 直接禁止发布。
    # 所以这里要求 __GEO__ 里有真正的三维量才认 sides。
    sec_v = geo.get("section_vertices") or geo.get("vertices")
    is3d = bool(
        (isinstance(sec_v, list) and len(sec_v) >= 3)
        or (num_of(geo.get("v_up")) is not None
            and num_of(geo.get("v_down")) is not None)
        or None not in (geo.get("V"), geo.get("E"), geo.get("F"))
    )
    sides = geo.get("sides")
    if sides is not None and is3d:
        checked += 1
        n = int(num_of(sides) or 0)
        if not (3 <= n <= 6):
            fails.append("截面边数 %d 超出 3–6 的合法范围" % n)

    # J4-03 欧拉公式 V−E+F=2（仅连通、闭合、亏格 0 的多面体适用）
    V, E, F = geo.get("V"), geo.get("E"), geo.get("F")
    if None not in (V, E, F):
        checked += 1
        if int(V) - int(E) + int(F) != 2:
            fails.append("V−E+F=%d，不等于 2（曲面非凸或不闭合）" % (int(V) - int(E) + int(F)))

    # J4-04 截面顶点共面
    verts = geo.get("section_vertices") or geo.get("vertices")
    if isinstance(verts, list) and len(verts) >= 3:
        try:
            p = [[float(v["x"]), float(v["y"]), float(v["z"])] for v in verts[:6]]
            p0, p1, p2 = p[0], p[1], p[2]
            u = [p1[i] - p0[i] for i in range(3)]
            w = [p2[i] - p0[i] for i in range(3)]
            n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]]
            norm = math.sqrt(sum(x * x for x in n)) or 1
            checked += 1
            off = max(abs(sum(n[i] * (q[i] - p0[i]) for i in range(3))) / norm for q in p)
            if off > 1e-3:
                fails.append("截面顶点不共面（最大偏移 %.4f）" % off)
        except (KeyError, TypeError, ValueError):
            pass

    # J4-05 六边形截面的面积关系（a/√2 边长正六边形）
    area = num_of(geo.get("area"))
    if sides is not None and is3d and int(num_of(sides) or 0) == 6 and area is not None:
        checked += 1
        if not (0.5 < area < 2.0):
            fails.append("六边形截面面积 %.3f 超出单位立方体的合理范围" % area)

    # J4-06 正方体展开与折叠拓扑不变量（6 个正方形面、5 条公共折叠边、3 组互不重叠的相对面）
    data = (ctx.get("machine") or {}).get("DATA") or {}
    net_src = geo if (geo.get("opposite_pairs") is not None or geo.get("shared_edges") is not None
                      or geo.get("net_faces") is not None) else data
    opp = net_src.get("opposite_pairs") or net_src.get("opposites")
    sh_edges = num_of(net_src.get("shared_edges"))
    cut_edges = num_of(net_src.get("cut_edges"))
    net_faces = num_of(net_src.get("net_faces") if net_src.get("net_faces") is not None else net_src.get("faces"))
    if isinstance(opp, list) and opp:
        checked += 1
        if len(opp) != 3:
            fails.append("正方体相对面组数为 %d，应为 3 组" % len(opp))
        else:
            flat = [x for pair in opp if isinstance(pair, (list, tuple)) and len(pair) == 2 for x in pair]
            if len(flat) != 6 or len(set(flat)) != 6:
                fails.append("3 组相对面未覆盖 6 个互异面：%s" % (opp,))
    if sh_edges is not None:
        checked += 1
        if int(sh_edges) != 5:
            fails.append("正方体展开图公共折叠边数为 %d，连通 6 面树结构应为 5 条" % int(sh_edges))
    if cut_edges is not None:
        checked += 1
        if int(cut_edges) != 7:
            fails.append("正方体剪开棱数为 %d，12−5 应为 7 条" % int(cut_edges))
    if net_faces is not None and ("展开" in text or opp is not None or sh_edges is not None):
        checked += 1
        if int(net_faces) != 6:
            fails.append("正方体展开图面数为 %d，应为 6 个面" % int(net_faces))

    if not checked:
        out.append(mk("J4", "J4-01", "J4 空间拓扑", "skip",
                      "三维面/边/顶点、截面、体积关系成立",
                      "未在 __GEO__ 中找到三维拓扑量",
                      "本页不是三维几何页，J4 不适用", weight=6))
        return out

    out.append(mk("J4", "J4-01", "J4 空间拓扑", "pass" if not fails else "fail",
                  "截点共面、截面闭合、体积可加、展开图拓扑自洽",
                  "；".join(fails) if fails else "%d 项拓扑不变量成立" % checked,
                  "三维结构自相矛盾，画面可能看着正常但拓扑是错的" if fails else "拓扑关系自洽",
                  evidence="；".join(fails[:3]), severity="critical" if fails else "major",
                  advice="把截面顶点坐标与体积分量或展开图相对面暴露到 __GEO__，不要硬编码图形",
                  weight=6))
    return out


# ================================================================ J5 序列与状态

def _bubble_ref(arr):
    """独立的参考实现：冒泡排序每一步的数组快照。"""
    a = list(arr)
    steps = [list(a)]
    n = len(a)
    for i in range(n):
        for j in range(n - 1 - i):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                steps.append(list(a))
    return steps


def _bsearch_ref(arr, target):
    """独立的参考实现：二分查找每一步的 (left, right, mid) 区间收缩序列。"""
    a = [num_of(v) for v in arr]
    t = num_of(target)
    lo, hi = 0, len(a) - 1
    trace = []
    while lo <= hi:
        mid = (lo + hi) // 2
        trace.append((lo, hi, mid))
        if a[mid] == t:
            break
        elif a[mid] < t:
            lo = mid + 1
        else:
            hi = mid - 1
    return trace


def _hanoi_ref(n, src="A", aux="B", dst="C"):
    """独立的参考实现：n 阶汉诺塔每一步移动 (disk, from_peg, to_peg)。"""
    moves = []

    def _move(k, a, b, c):
        if k <= 0:
            return
        _move(k - 1, a, c, b)
        moves.append((k, a, c))
        _move(k - 1, b, a, c)

    _move(int(n), src, aux, dst)
    return moves


def j5_sequence(ctx):
    out = []
    br = ctx.get("br") or {}
    data = (ctx.get("machine") or {}).get("DATA") or {}
    steps = br.get("steps") or {}
    checked, fails = 0, []

    # J5-01 单步不卡死：每次「下一步」后状态都应变化
    if steps.get("found"):
        checked += 1
        cnt, stuck = steps.get("count", 0), steps.get("stuck", 0)
        uniq = steps.get("unique", cnt)
        if stuck > 0:
            fails.append("连续 %d 次单步后状态没有变化（共 %d 步）" % (stuck, cnt))
        elif uniq < 2:
            fails.append("单步 %d 次只出现 1 个状态，过程没有真正推进" % cnt)

    # J5-02 与参考实现对拍（冒泡排序：二维数组历史快照）
    seq = data.get("steps") or data.get("history")
    if isinstance(seq, list) and len(seq) >= 2 and all(isinstance(x, list) for x in seq[:3]):
        checked += 1
        ref = _bubble_ref(seq[0])
        ok = len(seq) <= len(ref) and all(
            [num_of(v) for v in s] == [num_of(v) for v in ref[i]]
            for i, s in enumerate(seq) if i < len(ref)
        )
        final = [num_of(v) for v in seq[-1]]
        if not ok:
            fails.append("执行序列与参考冒泡排序不一致（第 %d 步起偏离）"
                         % next((i + 1 for i, s in enumerate(seq)
                                 if i < len(ref) and [num_of(v) for v in s] != [num_of(v) for v in ref[i]]), 0))
        if final != sorted(final):
            fails.append("终态未有序：%s" % final)

    # J5-02b 与参考实现对拍（二分查找：区间 [left, right, mid] 序列）
    bs_steps = data.get("bsearch_steps") or (
        seq if isinstance(seq, list) and seq and isinstance(seq[0], dict)
        and any(k in seq[0] for k in ("mid", "left", "low", "l")) else None
    )
    if isinstance(bs_steps, list) and bs_steps:
        checked += 1
        arr = data.get("arr") or data.get("array") or (data.get("params") or {}).get("arr")
        target = (data.get("target") if data.get("target") is not None
                  else (data.get("params") or {}).get("target"))
        if isinstance(arr, list) and arr:
            nums = [num_of(x) for x in arr]
            if nums != sorted(nums):
                fails.append("二分查找前置条件不成立：输入序列 %s 未按升序排列" % nums)
            elif target is not None:
                ref_bs = _bsearch_ref(nums, target)
                for idx, st in enumerate(bs_steps):
                    lo = int(num_of(st.get("left", st.get("low", st.get("l")))))
                    hi = int(num_of(st.get("right", st.get("high", st.get("r")))))
                    mid = int(num_of(st.get("mid", st.get("m"))))
                    if idx >= len(ref_bs) or (lo, hi, mid) != ref_bs[idx]:
                        exp = ref_bs[idx] if idx < len(ref_bs) else "已结束"
                        fails.append("二分查找第 %d 步区间 (%d,%d,mid=%d) 与参考实现 %s 不一致"
                                     % (idx + 1, lo, hi, mid, exp))
                        break
        else:
            prev_span = None
            for idx, st in enumerate(bs_steps):
                lo = int(num_of(st.get("left", st.get("low", st.get("l")))))
                hi = int(num_of(st.get("right", st.get("high", st.get("r")))))
                mid = int(num_of(st.get("mid", st.get("m"))))
                if not (lo <= mid <= hi):
                    fails.append("二分查找第 %d 步越界：left=%d, mid=%d, right=%d" % (idx + 1, lo, mid, hi))
                    break
                if mid != (lo + hi) // 2:
                    fails.append("二分查找第 %d 步 mid=%d 不等于 ⌊(%d+%d)/2⌋=%d"
                                 % (idx + 1, mid, lo, hi, (lo + hi) // 2))
                    break
                span = hi - lo
                if prev_span is not None and span >= prev_span:
                    fails.append("二分查找第 %d 步区间宽度 %d 未严格收缩（上一步 %d）"
                                 % (idx + 1, span, prev_span))
                    break
                prev_span = span

    # J5-02c 与参考实现对拍（汉诺塔：步数 2^n - 1 与圆盘移动序列/大小盘约束）
    hanoi_moves = data.get("hanoi_moves") or data.get("moves") or (
        seq if isinstance(seq, list) and seq and isinstance(seq[0], dict)
        and ("from" in seq[0] or "A" in seq[0]) else None
    )
    hanoi_n = num_of(data.get("disks") if data.get("disks") is not None else data.get("n_disks"))
    if hanoi_n is None and ("汉诺塔" in (ctx.get("text") or "") or hanoi_moves):
        hanoi_n = num_of((data.get("params") or {}).get("n") or data.get("n"))
    if hanoi_n is not None and int(hanoi_n) >= 1:
        n_int = int(hanoi_n)
        rep_total = num_of(data.get("total_moves") if data.get("total_moves") is not None
                           else (data.get("result") or {}).get("total_moves"))
        if rep_total is not None:
            checked += 1
            if int(rep_total) != (2 ** n_int - 1):
                fails.append("%d 阶汉诺塔最少步数显示 %d，应为 2^%d−1=%d"
                             % (n_int, int(rep_total), n_int, 2 ** n_int - 1))
    if isinstance(hanoi_moves, list) and hanoi_moves:
        checked += 1
        if isinstance(hanoi_moves[0], dict) and "from" in hanoi_moves[0] and "to" in hanoi_moves[0]:
            n_use = int(hanoi_n) if hanoi_n else max(int(num_of(m.get("disk", 1)) or 1) for m in hanoi_moves)
            ref_h = _hanoi_ref(n_use)
            for idx, m in enumerate(hanoi_moves):
                dk = int(num_of(m.get("disk", ref_h[idx][0] if idx < len(ref_h) else 0)) or 0)
                fr, to = str(m.get("from")), str(m.get("to"))
                if idx >= len(ref_h) or (dk, fr, to) != ref_h[idx]:
                    exp = ref_h[idx] if idx < len(ref_h) else "已完成"
                    fails.append("汉诺塔第 %d 步 (%s:%s→%s) 与参考递归序列 %s 不一致"
                                 % (idx + 1, dk, fr, to, exp))
                    break
        elif isinstance(hanoi_moves[0], dict) and all(k in hanoi_moves[0] for k in ("A", "B", "C")):
            for idx, st in enumerate(hanoi_moves):
                for peg in ("A", "B", "C"):
                    pile = [num_of(x) for x in (st.get(peg) or [])]
                    # 规定栈底到栈顶递减（大盘在下）或栈顶到栈底递增，但绝不能大小交错
                    if len(pile) >= 2 and pile != sorted(pile) and pile != sorted(pile, reverse=True):
                        fails.append("汉诺塔第 %d 步 %s 柱出现大盘压小盘：%s" % (idx + 1, peg, pile))
                        break

    # J5-03 阶段序号单调（细胞分裂、地理过程）
    stage = data.get("stage") or data.get("阶段")
    if isinstance(stage, (int, float)):
        checked += 1
        total = num_of(data.get("stageTotal") or data.get("总阶段"))
        if total and not (1 <= stage <= total):
            fails.append("当前阶段 %s 超出 1–%s" % (stage, total))

    if not checked:
        out.append(mk("J5", "J5-01", "J5 序列与状态", "skip",
                      "单步执行的状态序列与参考过程一致",
                      "页面没有单步按钮，也未暴露状态序列",
                      "本页无过程/序列类内容，J5 不适用", weight=6))
        return out

    out.append(mk("J5", "J5-01", "J5 序列与状态", "pass" if not fails else "fail",
                  "每一步只发生合法的状态迁移，末态正确",
                  "；".join(fails) if fails else "状态序列与参考过程一致",
                  "过程顺序或状态迁移有误，学生看到的是错误的过程" if fails else "过程可逐步复现",
                  evidence="；".join(fails[:3]), severity="critical" if fails else "major",
                  advice="用单一 state + 单步函数实现过程，每步只允许相邻阶段迁移，并把历史快照写进 __DATA__.steps",
                  weight=6))
    return out


# ================================================================ J6 结构要素齐备

def j6_structure(ctx):
    out = []
    text = ctx.get("text") or ""
    scene = ctx.get("scene") or {}
    required = scene.get("required") or []

    if scene:
        miss = [x for x in required if x not in text]
        out.append(mk("J6", "J6-01", "J6 强制要素齐备", "pass" if not miss else "fail",
                      "场景「%s」必须具备：%s" % (scene.get("name", ""), "、".join(required)),
                      "缺失：%s" % "、".join(miss) if miss else "要素齐全",
                      "装置/器材/标注缺失，实验无法成立" if miss else "强制要素完整",
                      evidence=scene.get("name", ""),
                      advice="按场景注册表的 required 清单补齐器材与标注，并确保名称与教材一致",
                      severity="major", weight=5))
    else:
        # 没有注册场景就没有"强制清单"，不能凭空判合格
        hits = [w for w in ("单位", "图例", "刻度", "标注", "坐标轴") if w in text]
        out.append(mk("J6", "J6-01", "J6 强制要素齐备", "review",
                      "按已审核场景注册表核对器材/标注/图例",
                      "场景未注册，仅命中通用标注 %d 项（%s）" % (len(hits), "、".join(hits) or "无"),
                      "缺少场景注册表就无法确定「该有哪些器材」，此项交教师确认",
                      advice="在 registry.SCENES 里登记该场景及 required 清单，或先在知识库完成场景审核",
                      weight=5))
    return out


# ================================================================ J7 统计复算

def _table_series(tables):
    """从表格里抽数值列，返回 {列名: [值...]}。"""
    series = {}
    for tb in tables or []:
        if len(tb) < 3:
            continue
        header = tb[0]
        for ci in range(len(header)):
            vals = []
            for row in tb[1:]:
                if ci < len(row):
                    v = num_of(row[ci])
                    if v is not None:
                        vals.append(v)
            if len(vals) >= 3:
                series[header[ci] or ("列%d" % (ci + 1))] = vals
    return series


def j7_statistics(ctx):
    out = []
    br = ctx.get("br") or {}
    data = (ctx.get("machine") or {}).get("DATA") or {}
    text = ctx.get("text") or ""
    checked, fails, notes = 0, [], []

    series = _table_series(br.get("tables"))
    # J7-01 表格均值核对：必须"列名 + 平均"对得上，不能拿电压列去比电流的均值
    wants_mean = any(k in text for k in ("平均", "均值"))
    if series and wants_mean:
        for name, vals in list(series.items())[:3]:
            mean = sum(vals) / len(vals)
            core = re.sub(r"[（(].*?[)）]", "", str(name))
            core = re.sub(r"[A-Za-zμΩ°%³²·/\s]", "", core)   # 去掉单位与字母，只留中文列名
            shown = []
            if core:
                shown += re.findall(r"平均[^0-9]{0,10}%s[^0-9]{0,6}(\d+(?:\.\d+)?)" % re.escape(core), text)
                shown += re.findall(r"%s[^0-9]{0,10}平均[^0-9]{0,6}(\d+(?:\.\d+)?)" % re.escape(core), text)
            if not shown:
                notes.append("表格「%s」有 %d 个数据，未见对应的平均值" % (name, len(vals)))
                continue
            checked += 1
            if not any(within(mean, float(s), "统计") for s in shown):
                fails.append("「%s」均值应为 %.3f，页面显示 %s" % (name, mean, "、".join(shown[:2])))

    # J7-02 页面自报的统计量与样本复算
    result = data.get("result") or {}
    sample = data.get("samples") or data.get("series")
    if isinstance(sample, list) and len(sample) >= 3:
        vals = [num_of(v) for v in sample if num_of(v) is not None]
        if vals:
            mean = sum(vals) / len(vals)
            var = sum((v - mean) ** 2 for v in vals) / len(vals)
            for key, expect in (("均值", mean), ("平均", mean), ("方差", var)):
                if key in result:
                    checked += 1
                    if not within(expect, num_of(result[key]), "统计"):
                        fails.append("%s 显示 %s，独立复算 %.3f" % (key, result[key], expect))

    if not checked:
        out.append(mk("J7", "J7-01", "J7 统计复算", "skip",
                      "均值/方差/斜率等统计量可由样本独立复算",
                      "页面没有统计量或样本少于 3 组",
                      "本页无统计内容，J7 不适用", weight=5))
        return out

    if fails:
        out.append(mk("J7", "J7-01", "J7 统计复算", "fail",
                      "统计量与样本独立复算一致", "；".join(fails),
                      "统计结果与数据不符，图表和数字会互相矛盾",
                      evidence="；".join(fails[:3]), severity="major",
                      advice="所有统计量在同一处由样本数组算出，图表与表格共用同一份数据",
                      weight=5))
    else:
        msg = "%d 项统计量复算通过" % checked
        if notes:
            msg += "；" + "；".join(notes[:2])
        out.append(mk("J7", "J7-01", "J7 统计复算", "pass",
                      "统计量与样本独立复算一致", msg, "统计量自洽", weight=5))
    return out


# ================================================================ J8 答案表比对

def _match_facts(facts, subject, text):
    matched = []
    for f in facts:
        if subject and f.get("学科") != subject:
            continue
        keys = [k for k in (f.get("主题") or []) if k in text]
        if len(keys) >= 2:
            matched.append((f, keys))
    return matched


def j8_facts(ctx):
    out = []
    text = ctx.get("text") or ""
    subject = ctx.get("subject") or ""
    facts = ctx.get("facts") or []
    scene = ctx.get("scene") or {}

    matched = _match_facts(facts, subject, text)
    # 场景绑定的事实优先
    if scene.get("facts"):
        ids = set(scene["facts"])
        matched = [(f, k) for f, k in matched if f.get("id") in ids] or matched

    if not matched:
        out.append(mk("J8", "J8-01", "J8 答案表比对", "review",
                      "与教师审核过的事实表比对现象与结论",
                      "本页主题未命中事实表（现有 %d 条已审核事实）" % len(facts),
                      "缺少可比对的事实条目，不能断定科学结论正确",
                      advice="在 facts.json 中补充该主题的事实条目（现象、必须出现、禁止出现的错误表述）",
                      weight=6))
        return out

    fails, passes, reviews = [], [], []
    for f, keys in matched:
        fid = f.get("id", "")
        reviewed = f.get("审核状态") == "教研复核通过"
        for bad in f.get("禁止出现") or []:
            if bad in text:
                fails.append("[%s] 出现错误表述「%s」（事实：%s）" % (fid, bad, f.get("事实", "")))
        for must in f.get("必须出现") or []:
            if must not in text:
                fails.append("[%s] 缺少必要表述「%s」" % (fid, must))
        any_of = f.get("至少出现") or []
        if any_of and not any(x in text for x in any_of):
            fails.append("[%s] 未出现关键现象/结论（应含其一：%s）" % (fid, "、".join(any_of)))
        if not reviewed:
            reviews.append("[%s] 事实表条目尚未通过教研复核" % fid)
        elif not fails:
            passes.append("[%s] 命中：%s" % (fid, "、".join(keys)))

    if fails:
        out.append(mk("J8", "J8-01", "J8 答案表比对", "fail",
                      "页面表述与已审核事实表一致",
                      "；".join(fails[:3]),
                      "页面出现与教材事实相反的表述，属于科学性错误",
                      evidence="；".join(fails[:3]), severity="critical",
                      advice="对照 facts.json 的『禁止出现』逐条改写；不确定的现象宁可不写，也不要编造",
                      weight=6))
    elif passes:
        out.append(mk("J8", "J8-01", "J8 答案表比对", "pass",
                      "页面表述与已审核事实表一致",
                      "；".join(passes[:3]),
                      "关键现象与结论与审核事实一致", weight=6))
    if reviews:
        out.append(mk("J8", "J8-02", "J8 事实条目待复核", "review",
                      "所引用事实条目应已通过教研复核",
                      "；".join(reviews), "事实条目未复核，暂不计入通过", weight=0))
    return out


# ================================================================ 调度

JUDGE_FUNCS = {
    "J1": j1_numeric,
    "J2": j2_geometry,
    "J3": j3_conservation,
    "J4": j4_topology,
    "J5": j5_sequence,
    "J6": j6_structure,
    "J7": j7_statistics,
    "J8": j8_facts,
}


def run(judges, ctx):
    """按学科配置的判据顺序执行。J0 的开放任务直接转人工。"""
    out = []
    for j in judges:
        fn = JUDGE_FUNCS.get(j)
        if fn:
            out.extend(fn(ctx))
        elif j == "J0":
            out.append(mk("J0", "J0-01", "J0 开放任务", "review",
                          "有客观可复算标准的任务才进入自动判分",
                          "本任务无客观标准", "开放任务需教师判断，不伪造机器判分", weight=0))
    return out
