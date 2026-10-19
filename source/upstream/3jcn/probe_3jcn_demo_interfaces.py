#!/usr/bin/env python3
"""3JCN（new3jcn.com）的程序化接口到底有什么——把简报里那句「尚未核实」量成数字。

已有镜像只有分类页（8 个 html），里面列的是各演示的绝对链接；单个演示页没取过，
所以「能不能被 Agent 改参」一直是空白。这一步做的事：
  ① 从分类页把演示链接全量收出来（按目录分组，看站点自己怎么归类）；
  ② 抓前 N 个演示页到 demos/，逐页统计「可程序化触达的面」：
     外部依赖数、内联 <script> 数与字节、three.js 版本、range 控件数、
     DOM id 数、`var 名字 = 数字` 这类可直接改的常量个数；
  ③ 记下每页的许可声明（分类页里链的是 CC BY 4.0，比 PhET 成品的 CC BY-NC 宽）。
判据不写成布尔：没有 API 但有「改内联 JS 常量」这条路，和「什么都改不了」是两回事。

跑法：python source/upstream/3jcn/probe_3jcn_demo_interfaces.py [N]
"""
import io
import json
import os
import re
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "pages")
DEMO_DIR = os.path.join(HERE, "demos")
BASE = "https://www.new3jcn.com/"
NAV = {"index.html", "patent.html", "about_3jcn.html", "simulation.html", "contact-form/index.html"}
CATEGORY = ["motion_category.html", "thermo_category.html", "electricity_category.html",
            "optics_category.html", "modern_category.html", "labs_category.html"]


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "eduforge-resource-audit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    links = {}
    for f in CATEGORY:
        p = os.path.join(PAGES, f)
        if not os.path.exists(p):
            continue
        t = io.open(p, encoding="utf-8", errors="replace").read()
        for h in re.findall(r'href="([^"]+\.html)"', t):
            if not h.startswith(BASE) or h.split("/")[-1] in NAV:
                continue
            links.setdefault(h.split("/")[3] if h.count("/") > 3 else "(root)", []).append(h)
    uniq = sorted({u for v in links.values() for u in v})
    print("demo links: %d unique, dirs: %s" % (len(uniq), {k: len(v) for k, v in sorted(links.items())}))

    os.makedirs(DEMO_DIR, exist_ok=True)
    rows, report = [], {"source": BASE, "probed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "unique_demo_links_in_mirror": len(uniq),
                        "by_directory": {k: sorted(set(v)) for k, v in sorted(links.items())},
                        "demos": []}
    for url in uniq[:n]:
        name = url.rstrip("/").split("/")[-1]
        local = os.path.join(DEMO_DIR, "%s__%s" % (url.split("/")[3] if url.count("/") > 3 else "root", name))
        try:
            if not os.path.exists(local):
                raw = get(url)
                io.open(local, "wb").write(raw)
                time.sleep(0.6)
            raw = io.open(local, "rb").read()
        except Exception as e:                                    # noqa: BLE001
            rows.append({"url": url, "error": str(e)[:160]})
            print("  FAIL %-46s %s" % (name, str(e)[:70]))
            continue
        t = raw.decode("utf-8", errors="replace")
        scripts = re.findall(r"<script\b([^>]*)>(.*?)</script>", t, re.S | re.I)
        inline = [b for a, b in scripts if "src=" not in a.lower()]
        extern = [a for a, _ in scripts if "src=" in a.lower()]
        consts = re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(-?\d+(?:\.\d+)?)\s*[;,]", t)
        rows.append({
            "url": url, "file": os.path.relpath(local, HERE).replace(os.sep, "/"), "bytes": len(raw),
            "external_scripts": len(extern), "three_js_ref": len(re.findall(r"THREE\.|three\.js|three.min.js", t)),
            "three_version": (re.findall(r"THREE\.REVISION\s*=\s*['\"]?(\d+)", t) or [None])[0],
            "inline_script_blocks": len(inline), "inline_js_bytes": sum(len(x) for x in inline),
            "range_inputs": len(re.findall(r"type=[\"']?range", t, re.I)),
            "dom_ids": len(set(re.findall(r'getElementById\(["\']([^"\']+)', t))),
            "numeric_constants": len(consts),
            "numeric_constant_names": [k for k, _ in consts][:25],
            "licence": (re.findall(r"licenses/by[^\"'<\s]*", t) or [None])[0],
            "has_canvas": len(re.findall(r"<canvas", t, re.I)),
        })
        r = rows[-1]
        print("  %-28s bytes=%-7d three=%-3d rev=%-4s range=%-2d ids=%-3d 常量=%-3d 外部脚本=%d 许可=%s"
              % (name[:28], r["bytes"], r["three_js_ref"], r["three_version"], r["range_inputs"],
                 r["dom_ids"], r["numeric_constants"], r["external_scripts"], r["licence"]))
    report["demos"] = rows
    ok = [r for r in rows if "error" not in r]
    report["summary"] = {
        "fetched": len(ok), "failed": len(rows) - len(ok),
        "with_three_js": len([r for r in ok if r["three_js_ref"]]),
        "with_range_controls": len([r for r in ok if r["range_inputs"]]),
        "editable_numeric_constants_total": sum(r["numeric_constants"] for r in ok),
        "demos_with_editable_constants": len([r for r in ok if r["numeric_constants"]]),
        "external_script_free": len([r for r in ok if r["external_scripts"] == 0]),
        "licences_seen": sorted({r["licence"] for r in ok if r["licence"]}),
    }
    out = os.path.join(HERE, "3jcn-demo-interface-probe.json")
    io.open(out, "w", encoding="utf-8").write(json.dumps(report, ensure_ascii=False, indent=2))
    print("summary:", json.dumps(report["summary"], ensure_ascii=False))
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
