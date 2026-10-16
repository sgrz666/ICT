r"""力学（单摆等）独立科学参考计算桩。

对齐方案 §1.2 和 §7.1：
- 规划排期在第 7～8 周切片 9 中落地；
- 保留单摆周期 \(T = 2\pi\sqrt{L/g}\) 与无阻尼机械能守恒计算预留位。
"""
from __future__ import annotations

import math


def calculate_pendulum_period(length_m: float, g: float = 9.8) -> float:
    """计算理想小角度单摆周期 (s)。"""
    if length_m <= 0 or g <= 0:
        raise ValueError("摆长和重力加速度必须为正数")
    return 2.0 * math.pi * math.sqrt(length_m / g)
