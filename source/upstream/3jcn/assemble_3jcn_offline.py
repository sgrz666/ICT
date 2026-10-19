#!/usr/bin/env python3
"""把 3JCN 的本地镜像整树做成**真离线**包：跨域脚本落到本地，页面里改指过去。

为什么要这一步：镜像树 `site/` 已经能在本机伺服跑起来，但页面里的
jQuery 3.2.1 与 bootstrap 3.3.7 仍指向 ajax.googleapis.com / maxcdn.bootstrapcdn.com
（`audit_offline_gaps.mjs` 每页都记到 6 个跨域请求）——只要断网或对方 CDN 挂掉，
这一族就「跑不起来」，谈不上交付。所以这里做的是**派生副本**，不改镜像树本身：
`site/` 原样保留（那是上游事实），`offline/` 才是可交付形态（与 EJSS 那条
`assemble_ejss_offline.py` 同一个套路）。

做法：整树复制 `site/ → offline/`，把跨域脚本下载进 `offline/_vendor/`，
再把 HTML 里的这几个 URL 换成本地相对路径；同时数一遍改了几处、还剩几个跨域引用
（图标、字体一类不影响运行的仍会留着，照实报，不装作 0）。

跑法：python source/upstream/3jcn/assemble_3jcn_offline.py
"""
import io
import os
import re
import shutil
import sys
import json
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
OUT = os.path.join(HERE, "offline")
VENDOR = "_vendor"
# 只代理会影响运行的脚本与样式；ico/字体一类的跨域引用留着，照实报数
CDN = [
    "https://ajax.googleapis.com/ajax/libs/jquery/3.2.1/jquery.min.js",
    "https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/js/bootstrap.min.js",
    "https://maxcdn.bootstrapcdn.com/bootstrap/3.3.7/css/bootstrap.min.css",
    # 这一条是被 A/B 逼出来的：断网复跑时页面 canvas 直接 0，才发现页面用**绝对 URL 的 ES module import**
    # 从 threejs.org 取 three.js（`from "https://threejs.org/build/three.module.js"`），
    # 而不是本地 jsm/。上一轮「本地与真站逐哈希一致」的结论只在**有网**前提下成立，这里补上才算真离线。
    "https://threejs.org/build/three.module.js",
]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "eduforge-resource-audit/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read()


def main():
    if not os.path.isdir(SITE):
        print("缺 site/：先跑 mirror_3jcn_site.py 与 audit_offline_gaps.mjs")
        return 1
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)
    os.makedirs(os.path.join(OUT, VENDOR), exist_ok=True)
    vendored = {}
    for u in CDN:
        name = u.rsplit("/", 1)[-1]
        if u in vendored:
            continue
        dst = os.path.join(OUT, VENDOR, name)
        if not os.path.exists(dst):
            try:
                io.open(dst, "wb").write(fetch(u))
                time.sleep(0.3)
            except Exception as e:                                    # noqa: BLE001
                print("下载失败，跳过该条：", u, str(e)[:90])
                continue
        vendored[u] = VENDOR + "/" + name
    pages = 0
    rewritten = 0
    residual = set()
    for base, _, files in os.walk(OUT):
        for f in files:
            if not f.endswith(".html"):
                continue
            p = os.path.join(base, f)
            t = io.open(p, encoding="utf-8", errors="replace").read()
            orig = t
            pages += 1
            depth = os.path.relpath(base, OUT).replace(os.sep, "/")
            up = "" if depth == "." else "../" * (depth.count("/") + 1)
            for u, local in vendored.items():
                if u in t:
                    t = t.replace(u, up + local)
                    rewritten += 1
            if t != orig:
                io.open(p, "w", encoding="utf-8", newline="\n").write(t)
            for m in re.finditer(r'(?:src|href)="(https?://[^"]+)"', t):
                residual.add(m.group(1).split("?")[0])
    rep = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": "source/upstream/3jcn/assemble_3jcn_offline.py",
           "site_tree": "source/upstream/3jcn/site", "out_tree": "source/upstream/3jcn/offline",
           "html_pages": pages, "cdn_refs_rewritten": rewritten, "vendored": vendored,
           "residual_cross_origin_refs": sorted(residual),
           "out_bytes": sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs),
           "note": "offline/ 与 site/、pages/、demos/ 同规被 .gitignore 挡住：整棵树是第三方 HTML 与三方库副本，不入库。"}
    io.open(os.path.join(HERE, "3jcn-offline-build.json"), "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2))
    print("页面 %d 份，改写跨域引用 %d 处，代理了 %d 个 CDN 文件，仍剩跨域引用 %d 种（图标/字体一类）"
          % (pages, rewritten, len(vendored), len(residual)))
    for u in sorted(residual)[:6]:
        print("   仍跨域：", u)
    print("输出", OUT, "(%d B)" % rep["out_bytes"], "；证据 3jcn-offline-build.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
