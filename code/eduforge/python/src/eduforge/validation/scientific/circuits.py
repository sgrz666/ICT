r"""电路（欧姆定律、串并联）独立科学参考计算桩。

对齐方案 §1.2 和 §7.1：
- 规划排期在第 7～8 周切片 9 中落地；
- 保留欧姆定律 \(I = U / R\) 与串并联等效电阻参考计算预留位。
"""
from __future__ import annotations


def calculate_ohms_law(voltage_v: float, resistance_ohm: float) -> float:
    """计算理想电阻电流 (A)。"""
    if resistance_ohm <= 0:
        raise ValueError("电阻值必须大于 0")
    return voltage_v / resistance_ohm
