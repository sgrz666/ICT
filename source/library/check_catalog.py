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
    if isinstance(x.get("measured_evidence"), str):
        paths.append(x["measured_evidence"])
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

# 自检：状态词必须在 status_words 里有定义；引用的引擎必须真的在 engines 里；
# 声明 verified 的实验必须带 measured_evidence（防止「口头已验证」）
declared = set(data["status_words"])
engine_ids = {e["id"] for e in data["engines"]}
bad_status, bad_engine, no_evidence = [], [], []
for x in data["experiments"]:
    if x["status"] not in declared:
        bad_status.append((x["id"], x["status"]))
    for eid in x.get("engines", []):
        if eid not in engine_ids:
            bad_engine.append((x["id"], eid))
    if x["status"].endswith("verified") and not x.get("measured_evidence"):
        no_evidence.append(x["id"])

print("engines:", len(data["engines"]), "| experiments:", n_exp, "| not_installed:", len(data["not_installed"]))
print("priority:", prio, "| status:", by_status)
print("paths checked:", len(dict.fromkeys(paths)), "| missing:", len(missing))
for m in missing:
    print("  MISSING:", m)
print("undeclared status:", len(bad_status), bad_status)
print("unknown engine refs:", len(bad_engine), bad_engine)
print("verified-but-no-evidence:", len(no_evidence), no_evidence)
sys.exit(0 if not (missing or bad_status or bad_engine or no_evidence) else 1)
