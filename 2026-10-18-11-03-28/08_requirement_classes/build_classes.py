# -*- coding: utf-8 -*-
"""build_classes.py —— 从 需求类型清单.json 生成 需求类型全景.md。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    data = json.load(open(os.path.join(HERE, "需求类型清单.json"), encoding="utf-8"))
    print("需求类型总数：", data["统计"]["类型总数"])

if __name__ == "__main__":
    main()
