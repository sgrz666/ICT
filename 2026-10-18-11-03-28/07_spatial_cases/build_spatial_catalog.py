# -*- coding: utf-8 -*-
"""build_spatial_catalog.py —— 从 spatial_cases.json 生成空间与过程类需求清单。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    data = json.load(open(os.path.join(HERE, "spatial_cases.json"), encoding="utf-8"))
    print("空间与过程类案例数：", data.get("总计", len(data.get("案例", []))))

if __name__ == "__main__":
    main()
