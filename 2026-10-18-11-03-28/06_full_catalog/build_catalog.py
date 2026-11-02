# -*- coding: utf-8 -*-
"""build_catalog.py —— 从 全学段案例清单.json 渲染 全学段案例总清单.md 与 CSV。"""
import csv, json, os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    data = json.load(open(os.path.join(HERE, "全学段案例清单.json"), encoding="utf-8"))
    print("已加载全学段案例：", data["统计"]["总数"])

if __name__ == "__main__":
    main()
