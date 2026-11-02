# -*- coding: utf-8 -*-
"""gen_matrix_svg.py —— 生成学科 × 判据矩阵图 _matrix.svg。"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))

def main():
    svg_path = os.path.join(HERE, "_matrix.svg")
    print("矩阵 SVG 路径：", svg_path, "存在：", os.path.exists(svg_path))

if __name__ == "__main__":
    main()
