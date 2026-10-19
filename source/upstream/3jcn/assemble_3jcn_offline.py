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
    # 这一条是 diagnose_offline_load.mjs 量出来的：模块链修好、canvas 起来之后，断网仍剩 1 条被拦请求。
    # 它写在 JS 的**字符串**里（FontLoader().load("https://threejs.org/examples/fonts/…typeface.json")），
    # 静态正则 BFS 看不见 —— 与 GLTF 的 `scene.bin` 同一类坑，只有真开浏览器按请求记账才能发现。
    # 25 个页面都用这一份字模，缺它 3D 场景能渲染但立体文字标签出不来。
    "https://threejs.org/examples/fonts/droid/droid_serif_bold.typeface.json",
]
# three.js 这一条**不能**走代理，是 A/B 试出来的：上一版把 FontLoader.js 里的
# `from "https://threejs.org/build/three.module.js"` 换成 `_vendor/three.module.js`，
# 断网复跑 canvas 仍是 0；diagnose_offline_load.mjs 记到唯一一条 404 —— `_vendor/three.core.js`。
# 根因两条：① threejs.org 如今的 build/three.module.js 是**拆分产物**（首行就 `import … from './three.core.js'`），
# 只搬主文件必然缺半条依赖；② 那一份比站方自带的 `jsm/three.module.js` 新得多，
# 让同一个页面同时挂两份 THREE 实例本来就是隐患。所以改成指向**包内已有的那一份**
# （实测 0 处 three.core 引用，自洽），既补上离线，又把实例数收回 1。
THREE_LOCAL = "jsm/three.module.js"
THREE_CDN = "https://threejs.org/build/three.module.js"


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
    # HTML 层改写不够：上一轮断网复跑还剩一条被拦请求，就是因为 `import "https://threejs.org/build/three.module.js"`
    # 写在 jsm/*.js 里。所以脚本、样式一起扫，按**每个文件自己的深度**算相对路径。
    scan_ext = (".html", ".js", ".mjs", ".css")
    js_hits = 0
    three_repointed = 0
    root_abs_fixed = 0
    residual = set()
    for base, _, files in os.walk(OUT):
        for f in files:
            if not f.endswith(scan_ext):
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
                    if not f.endswith(".html"):
                        js_hits += 1
            if THREE_CDN in t:
                n = t.count(THREE_CDN)
                t = t.replace(THREE_CDN, up + THREE_LOCAL)
                three_repointed += n
                rewritten += n
                if not f.endswith(".html"):
                    js_hits += n
            # 站点根绝对路径（`from '/jsm/three.module.js'`）在「包=站点根」时刚好能碰对，
            # 但作为 ZIP 交付、解压到任意子目录下必 404 —— 实测这一类只有 RoundedBoxGeometry.js 一处，
            # 但它会让整条 module 链断掉（canvas 0），所以按每个文件自己的深度改成相对。
            # 保守：只吃引号里以单个 / 开头的（`//host/…` 协议相对不动它）。
            def _rel(mx):
                nonlocal root_abs_fixed
                root_abs_fixed += 1
                return mx.group(1) + '"' + up + mx.group(2)[1:] + '"'
            t = re.sub(r'((?:from|import)\s+)["\'](/[^"\'/\s][^"\']*)["\']', _rel, t)
            if t != orig:
                io.open(p, "w", encoding="utf-8", newline="\n").write(t)
            for m in re.finditer(r'(?:src|href)="(https?://[^"]+)"', t):
                residual.add(m.group(1).split("?")[0])
    rep = {"built_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "tool": "source/upstream/3jcn/assemble_3jcn_offline.py",
           "site_tree": "source/upstream/3jcn/site", "out_tree": "source/upstream/3jcn/offline",
           "files_scanned": pages, "cdn_refs_rewritten": rewritten, "rewrites_outside_html": js_hits,
           "three_cdn_repointed_to_local": three_repointed, "root_absolute_specifiers_relabilized": root_abs_fixed,
           "vendored": vendored,
           "residual_cross_origin_refs": sorted(residual),
           "out_bytes": sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs),
           "note": "offline/ 与 site/、pages/、demos/ 同规被 .gitignore 挡住：整棵树是第三方 HTML 与三方库副本，不入库。"}
    io.open(os.path.join(HERE, "3jcn-offline-build.json"), "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2))
    print("扫描 %d 个文件（含 js/css），改写跨域引用 %d 处（其中非 HTML 文件 %d 处），three 改指包内自带 %d 处，"
          "站点根绝对路径改相对 %d 处，代理 %d 个 CDN 文件，仍剩跨域引用 %d 种"
          % (pages, rewritten, js_hits, three_repointed, root_abs_fixed, len(vendored), len(residual)))
    for u in sorted(residual)[:6]:
        print("   仍跨域：", u)
    print("输出", OUT, "(%d B)" % rep["out_bytes"], "；证据 3jcn-offline-build.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
