# -*- coding: utf-8 -*-
"""patch_lib_standdown.py —— 检查 frame/*.js 的 auto() 是否包含 isBlank(cv) 退让判断。"""
import glob, os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def main():
    for p in sorted(glob.glob(os.path.join(ROOT, "frame", "*.js"))):
        txt = open(p, encoding="utf-8").read()
        print(os.path.basename(p), "isBlank:", "isBlank" in txt)

if __name__ == "__main__":
    main()
