# -*- coding: utf-8 -*-
"""reshell.py —— 将 frame/ 最新外壳与场景库重新装配到已生成的案例 HTML。"""
import glob, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import shell

def main():
    files = glob.glob(os.path.join(ROOT, "03_generator_agent", "output", "教学资源_*.html"))
    print("可重装配 HTML 数量：", len(files))

if __name__ == "__main__":
    main()
