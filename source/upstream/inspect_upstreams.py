#!/usr/bin/env python3
"""扫描 source/upstream 下已安装的上游引擎，把实测事实写成 inventory.json。

只记磁盘上真实存在的东西：commit、分支、上游提交时间、体积、文件数、许可证文件、
按扩展名统计的主要文件、以及每类引擎的接入探针（可改参数与可读数落在哪）。
没跑过的（构建、无头调用）不在这里出现，那些写在 upstream.lock.json 的 pending 里。
"""
import json
import os
import subprocess
from collections import Counter
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.abspath(__file__))          # source/upstream
OUT = os.path.join(BASE, "inventory.json")
PRUNE = {".git", "node_modules", "__pycache__", ".pytest_cache", "dist-node"}


def sh(args, cwd=None):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return r.stdout.strip() if r.returncode == 0 else ""


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [d for d in dirnames if d not in PRUNE]
        for f in filenames:
            yield os.path.join(dirpath, f)


def probe(path):
    """返回该安装单元的实测事实；path 为相对 source/upstream 的路径。"""
    root = os.path.join(BASE, path)
    if not os.path.isdir(root):
        return {"path": path, "installed": False}
    size = 0
    ext = Counter()
    lic = []
    n = 0
    for f in walk(root):
        if os.path.basename(f).lower().startswith(("license", "copying", "copyright", "notice")):
            lic.append(os.path.relpath(f, root).replace("\\", "/"))
        try:
            size += os.path.getsize(f)
        except OSError:
            pass
        e = os.path.splitext(f)[1].lower() or "(none)"
        ext[e] += 1
        n += 1
    return {
        "path": path,
        "installed": True,
        "commit": sh(["git", "-C", root, "rev-parse", "HEAD"]),
        "branch": sh(["git", "-C", root, "rev-parse", "--abbrev-ref", "HEAD"]),
        "upstream_commit_date": sh(["git", "-C", root, "log", "-1", "--format=%cI"]),
        "size_kb": size // 1024,
        "files": n,
        "top_extensions": dict(ext.most_common(8)),
        "license_files": sorted(lic)[:6],
    }


UNITS = [
    ("ray-optics", "ray-optics"),
    ("myphysicslab", "myphysicslab"),
    ("circuitjs1", "circuitjs1"),
    ("matter-js", "matter-js"),
    ("rapier-js", "rapier-js"),
    ("three", "three"),
    ("stellarium-web-engine", "stellarium-web-engine"),
    ("webots", "webots"),
    # Open Source Physics 家族（EJSS 线），2026-10-19 由 fetch_osp_family.sh 浅克隆
    ("osp", "osp"),
    ("osp_ejs", "osp_ejs"),
    ("webejs", "webejs"),
    ("resources", "resources"),
    ("STP", "STP"),
    ("csm", "csm"),
    # PhET 官方发布的 HTML5 成品（单文件、可离线），2026-10-19 由 fetch_phet_published.py 下载
    ("phet-published-html5", "phet/published"),
]
for d in sorted(os.listdir(os.path.join(BASE, "phet", "libs"))) if os.path.isdir(os.path.join(BASE, "phet", "libs")) else []:
    if os.path.isdir(os.path.join(BASE, "phet", "libs", d, ".git")):
        UNITS.append((f"phet-lib-{d}", f"phet/libs/{d}"))
for d in sorted(os.listdir(os.path.join(BASE, "phet", "sims"))) if os.path.isdir(os.path.join(BASE, "phet", "sims")) else []:
    if os.path.isdir(os.path.join(BASE, "phet", "sims", d, ".git")):
        UNITS.append((f"phet-sim-{d}", f"phet/sims/{d}"))

units = []
for uid, path in UNITS:
    rec = probe(path)
    rec["id"] = uid
    units.append(rec)

# 接入探针：只看「参数与读数落在哪」这类结构性事实
def count_files(path, suffix):
    root = os.path.join(BASE, path)
    if not os.path.isdir(root):
        return 0
    return sum(1 for f in walk(root) if f.lower().endswith(suffix))


probes = {
    "ray-optics.gallery_scene_items": len(os.listdir(os.path.join(BASE, "ray-optics/data/galleryScenes")))
        if os.path.isdir(os.path.join(BASE, "ray-optics/data/galleryScenes")) else 0,
    "ray-optics.gallery_scenes_json": count_files("ray-optics/data/galleryScenes", ".json"),
    "myphysicslab.sim_html": count_files("myphysicslab/src/sims", ".html"),
    "myphysicslab.ts_sources": count_files("myphysicslab/src", ".ts"),
    "myphysicslab.compiled_js": count_files("myphysicslab/src", ".js"),
    "circuitjs1.java_sources": count_files("circuitjs1/src", ".java"),
    "circuitjs1.built_js_in_war": count_files("circuitjs1/war", ".js"),
    "circuitjs1.sample_circuits": count_files("circuitjs1", ".cir"),
    "three.src_js": count_files("three/src", ".js"),
    "three.examples_jsm": count_files("three/examples/jsm", ".js"),
    "matter-js.build_js": count_files("matter-js/build", ".js"),
    "rapier-js.js_artifacts": count_files("rapier-js", ".js"),
    "rapier-js.wasm_artifacts": count_files("rapier-js", ".wasm"),
    "stellarium.wasm": count_files("stellarium-web-engine", ".wasm"),
    "webots.worlds_wbproj": count_files("webots/projects", ".wbproj"),
    "webots.protos": count_files("webots/projects", ".proto"),
    "webots.controllers_py": count_files("webots/projects", ".py"),
    "webots.controllers_c": count_files("webots/projects", ".c") + count_files("webots/projects", ".cpp"),
    "phet.sims_installed": sum(1 for u in units if u["id"].startswith("phet-sim-")),
    "phet.libs_installed": sum(1 for u in units if u["id"].startswith("phet-lib-")),
    # Open Source Physics 家族 + 3JCN 目录镜像（2026-10-19）
    "osp.java_sources": count_files("osp", ".java"),
    "osp_ejs.java_sources": count_files("osp_ejs", ".java"),
    "STP.java_sources": count_files("STP", ".java"),
    "STP.thermal_packages": sorted(
        d for d in os.listdir(os.path.join(BASE, "STP/src/org/opensourcephysics/stp"))
        if os.path.isdir(os.path.join(BASE, "STP/src/org/opensourcephysics/stp", d))
    ) if os.path.isdir(os.path.join(BASE, "STP/src/org/opensourcephysics/stp")) else [],
    "csm.java_sources": count_files("csm", ".java"),
    "webejs.js_artifacts": count_files("webejs", ".js"),
    "webejs.wasm_artifacts": count_files("webejs", ".wasm"),
    "resources.html_pages": count_files("resources", ".html"),
    "3jcn.pages_mirrored": count_files("3jcn/pages", ".html"),
    "phet.published_html5_sims": count_files("phet/published", "_all.html"),
    "3jcn.catalog_links": len(json.load(open(os.path.join(BASE, "3jcn/3jcn-inventory.json"), encoding="utf-8"))["entries"])
        if os.path.exists(os.path.join(BASE, "3jcn/3jcn-inventory.json")) else 0,
}
for u in units:
    if u["id"].startswith("phet-sim-"):
        name = u["id"][len("phet-sim-"):]
        p = f"phet/sims/{name}"
        u["phet_probe"] = {
            "js_sources": count_files(p + "/js", ".js"),
            "ts_sources": count_files(p + "/js", ".ts"),
            "dependencies_json": os.path.exists(os.path.join(BASE, p, "dependencies.json")),
            "dev_html": os.path.exists(os.path.join(BASE, p, f"{name}_en.html")),
            "phetio_overrides": os.path.exists(os.path.join(BASE, p, f"{name}-phet-io-overrides.js")),
            "stub_main_only": u["branch"] == "main" and u["files"] < 20,
        }

inst = [u for u in units if u.get("installed")]
data = {
    "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    "generated_by": "source/upstream/inspect_upstreams.py",
    "comment": "本文件由脚本生成，数字全部来自磁盘实测。重跑：python source/upstream/inspect_upstreams.py",
    "totals": {
        "installed_units": len(inst),
        "total_size_kb": sum(u.get("size_kb", 0) for u in inst),
        "total_files": sum(u.get("files", 0) for u in inst),
    },
    "probes": probes,
    "units": units,
}
with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
print("units:", len(inst), "| size_kb:", data["totals"]["total_size_kb"], "| files:", data["totals"]["total_files"])
for k, v in probes.items():
    print(f"  {k} = {v}")
