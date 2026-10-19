#!/usr/bin/env python3
"""校验 source/library/experiments.json 里引用的每一条路径都真实存在。

资源库最容易犯的错是「目录里写了个不存在的路径」，Agent 照着取种子就会 404。
这个脚本把 engines 的 install_path、seed、measured_evidence、fetch_logs 全过一遍，
missing 必须为 0 才算这份目录可用。跑法：python source/library/check_catalog.py
"""
import json
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CAT = os.path.join(REPO, "source", "library", "experiments.json")

data = json.load(open(CAT, encoding="utf-8"))
paths = []
for e in data["engines"]:
    for k in ("install_path", "npm_component"):
        if e.get(k):
            paths.append(e[k])
    for v in e.get("resource_seeds", {}).get("examples", []):
        paths.append(v)
for x in data["experiments"]:
    paths.extend(x.get("seed", []))
for v in data["verification_log"].values():
    if isinstance(v, str):
        paths.append(v)
    elif isinstance(v, list):
        paths.extend(v)

def norm(p):
    return p.split("@")[0]  # npm_component 写成 包名@版本，落盘路径没有 @ 后缀


missing = [p for p in dict.fromkeys(paths) if not os.path.exists(os.path.join(REPO, norm(p).replace("/", os.sep)))]

n_exp = len(data["experiments"])
by_status = {}
for x in data["experiments"]:
    by_status[x["status"]] = by_status.get(x["status"], 0) + 1
prio = {}
for x in data["experiments"]:
    prio[x["priority"]] = prio.get(x["priority"], 0) + 1

print("engines:", len(data["engines"]), "| experiments:", n_exp, "| not_installed:", len(data["not_installed"]))
print("priority:", prio, "| status:", by_status)
print("paths checked:", len(dict.fromkeys(paths)), "| missing:", len(missing))
for m in missing:
    print("  MISSING:", m)
sys.exit(1 if missing else 0)
