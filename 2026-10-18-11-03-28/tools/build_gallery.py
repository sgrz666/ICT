# -*- coding: utf-8 -*-
"""build_gallery.py —— 扫描已生成的教学资源 HTML，汇总生成预览索引。"""
import glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    pages = sorted(glob.glob(os.path.join(ROOT, "03_generator_agent", "output", "教学资源_*.html")))
    print("已收录教学资源页数：", len(pages))

if __name__ == "__main__":
    main()
