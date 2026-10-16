import math


def thin_lens_reference(focal_length_cm: float, object_distance_cm: float) -> dict:
    # 独立参考计算。观测值来自上游仿真（Detector 读数），两边不共用公式，否则是自我验证。
    # 适用条件：理想薄透镜。上游 SphericalLens（厚透镜、refIndex 1.5、含球差色散）不可对照。
    f = focal_length_cm
    u = object_distance_cm

    if not math.isfinite(f) or not math.isfinite(u):
        raise ValueError("inputs must be finite")

    if f <= 0 or u <= 0:
        raise ValueError("convex-lens inputs must be positive")

    if math.isclose(u, f, rel_tol=1e-9, abs_tol=1e-9):
        return {"image_distance_cm": None, "magnification": None, "image_kind": "at_infinity"}

    v = f * u / (u - f)

    return {
        "image_distance_cm": v,
        "magnification": -v / u,
        "image_kind": "real" if v > 0 else "virtual",
    }
