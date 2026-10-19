#!/usr/bin/env python3
"""把 3JCN 演示页的**同源依赖闭包**镜像下来，让页面能在本机真的跑起来。

为什么要这一支：上一轮 `jcn3_headless_lab.mjs` 在无头里跑到 canvas 恒 0，
误以为「3JCN 的 3D 场景跑不起来」。查了页面源码才发现真相更简单——
演示页用 `<script type="module">` 从 `../jsm/three.module.js` 引 three.js（还有
OrbitControls / FontLoader / TextGeometry / GLTFLoader），而镜像只抓了 HTML 与目录页，
`jsm/`、`css/`、`models/` 一个都没取。模块 import 失败不抛 pageerror，所以旧探针只看到
「没异常但也没画面」，那是**我的镜像缺料**，不是站点坏。

做法：从给定种子页出发，BFS 抓所有**同源**（www.new3jcn.com）引用，按站点相对路径落
`site/`（html/css/js/mjs/glb/json/png/jpg…），跨域（jQuery/bootstrap CDN）保持原样不代理，
只把清单记下来，供后面离线化时再处理。默认深度 3、文件上限 400，防止整站漫游。

跑法：python source/upstream/3jcn/mirror_3jcn_site.py [种子页 ...] [--depth 3] [--max 400]
"""
import io
import json
import os
import re
import sys
import time
import urllib.request
from urllib.parse import urljoin, urlparse

BASE = "https://www.new3jcn.com/"
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "site")
ASSET_EXT = (".js", ".mjs", ".css", ".json", ".glb", ".gltf", ".png", ".jpg", ".jpeg", ".svg", ".woff", ".mp3", ".wasm")
REF_RE = re.compile(r"""(?:src|href)\s*=\s*["']([^"']+)["']|from\s+["']([^"']+)["']|import\s+["']([^"']+)["']|url\(\s*["']?([^"')]+)""", re.I)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "eduforge-resource-audit/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read(), r.headers.get("Content-Type", "")


def same_origin(url):
    return urlparse(url).netloc == urlparse(BASE).netloc


def local_path(url):
    p = urlparse(url).path.lstrip("/") or "index.html"
    return os.path.join(SITE, *[x for x in p.split("/") if x not in ("", ".", "..")])


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    depth = int(sys.argv[sys.argv.index("--depth") + 1]) if "--depth" in sys.argv else 3
    maxn = int(sys.argv[sys.argv.index("--max") + 1]) if "--max" in sys.argv else 400
    seeds = args or [BASE + "Phyc140/buoyant_force_exp.html", BASE + "Phyc140/flat_mirror_prob.html"]
    seen, queue, fetched, failed, external = set(), [], 0, [], set()
    for s in seeds:
        u = s if s.startswith("http") else urljoin(BASE, s)
        queue.append((u, 0))
    while queue and fetched < maxn:
        url, d = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        if not same_origin(url):
            external.add(url)
            continue
        try:
            raw, ctype = get(url)
        except Exception as e:                                    # noqa: BLE001
            failed.append({"url": url, "error": str(e)[:120]})
            continue
        dst = local_path(url)
        os.makedirs(os.path.dirname(dst) or SITE, exist_ok=True)
        io.open(dst, "wb").write(raw)
        fetched += 1
        if d < depth and (".html" in url or "text/html" in ctype):
            t = raw.decode("utf-8", errors="replace")
            for m in REF_RE.finditer(t):
                ref = next((g for g in m.groups() if g), "")
                if not ref or ref.startswith(("data:", "mailto:", "#", "javascript:")):
                    continue
                au = urljoin(url, ref.split("?")[0])
                if not same_origin(au):
                    external.add(au)
                    continue
                if au.endswith(ASSET_EXT) or au.endswith(".html"):
                    if au not in seen:
                        queue.append((au, d + 1))
        elif d < depth:
            # 资产本身也引资源（three.module.js 里的贴图、css 里的 url(...)）
            t = raw.decode("utf-8", errors="replace")
            for m in re.finditer(r"""["'(]([^"')]+\.(?:png|jpg|json|glb|gltf|woff|wasm))["')\s]""", t, re.I):
                au = urljoin(url, m.group(1))
                if same_origin(au) and au not in seen:
                    queue.append((au, d + 1))
        print("  [%d] %s (%d B)" % (d, url.replace(BASE, "/"), len(raw)))
        time.sleep(0.35)
    report = {"base": BASE, "mirrored_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "seeds": seeds,
              "depth": depth, "max_files": maxn, "files_fetched": fetched,
              "site_bytes": sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(SITE) for f in fs) if os.path.isdir(SITE) else 0,
              "cross_origin_kept_as_is": sorted(external), "failed": failed}
    io.open(os.path.join(HERE, "3jcn-mirror.json"), "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2))
    print("\nmirrored %d files into %s (%d B); 跨域保留 %d; 失败 %d" % (fetched, SITE, report["site_bytes"], len(external), len(failed)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
