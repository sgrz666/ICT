# -*- coding: utf-8 -*-
"""gen_svg.py —— 生成六学科 30 案例展示矩阵 SVG（展示矩阵.svg）。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    svg_path = os.path.join(HERE, "展示矩阵.svg")
    print("展示矩阵 SVG 路径：", svg_path, "存在：", os.path.exists(svg_path))

if __name__ == "__main__":
    main()
