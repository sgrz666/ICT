# -*- coding: utf-8 -*-
"""relib.py —— 批量同步 frame/*.js 学科场景库到产出目录与交付目录。"""
import os, shutil
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    src = os.path.join(ROOT, "frame")
    dst = os.path.join(ROOT, "03_generator_agent", "output")
    for f in os.listdir(src):
        if f.endswith((".js", ".css", ".png")):
            shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
    print("已同步 frame/ 静态资产到", dst)

if __name__ == "__main__":
    main()
