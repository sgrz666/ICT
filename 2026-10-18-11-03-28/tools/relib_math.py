# -*- coding: utf-8 -*-
"""relib_math.py —— 同步 frame/math.js 与 frame/vis.js 到生成输出目录。"""
import os, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    for name in ("vis.js", "math.js"):
        shutil.copy2(os.path.join(ROOT, "frame", name),
                     os.path.join(ROOT, "03_generator_agent", "output", name))
    print("已同步 vis.js, math.js")

if __name__ == "__main__":
    main()
