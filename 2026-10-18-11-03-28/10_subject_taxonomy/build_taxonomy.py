# -*- coding: utf-8 -*-
"""build_taxonomy.py —— 从 学科需求分类.json 生成 学科需求分类.md 与 CSV。"""
import json, os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    data = json.load(open(os.path.join(HERE, "学科需求分类.json"), encoding="utf-8"))
    print("学科数：%d，需求类型数：%d" % (data["统计"]["学科数"], data["统计"]["需求类型数"]))

if __name__ == "__main__":
    main()
