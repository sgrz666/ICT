#!/usr/bin/env python3
"""按「最新发行分支」浅克隆 PhET 仿真源码到 source/upstream/phet/sims/。

为什么要指定分支：PhET 已把各仿真仓库的 main 分支空心化（只剩 README + doc/，
源码收进未公开的 monorepo），但每个仓库的 X.Y 发行分支仍带完整 js/ 源码。
本脚本用 git ls-remote 枚举分支，取版本号最大的那一个，再把实测结果写进日志。
"""
import os
import re
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DEST_ROOT = os.path.join(BASE, "phet", "sims")
LOG = os.path.join(BASE, "fetch-phet-log.tsv")

SIMS = [
    "bending-light", "ohms-law", "circuit-construction-kit-common",
    "circuit-construction-kit-dc", "circuit-construction-kit-ac",
    "pendulum-lab", "masses-and-springs", "hookes-law", "projectile-motion",
    "collision-lab", "wave-on-a-string", "waves-intro", "wave-interference",
    "gas-properties", "gases-intro", "gravity-and-orbits", "charges-and-fields",
    "magnets-and-electromagnets", "energy-skate-park-basics", "forces-and-motion-basics",
]


def sh(args):
    return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")


def latest_branch(name):
    r = sh(["git", "ls-remote", "--heads", f"https://github.com/phetsims/{name}.git"])
    if r.returncode != 0:
        return None, None, r.stderr.strip()[:180]
    heads = []
    for line in r.stdout.splitlines():
        m = re.search(r"refs/heads/(\S+)$", line)
        if m:
            heads.append(m.group(1))
    rel = [h for h in heads if re.fullmatch(r"\d+\.\d+(\.\d+)?", h)]
    if rel:
        rel.sort(key=lambda h: [int(p) for p in h.split(".")])
        return rel[-1], rel, heads
    return ("main" if "main" in heads else heads[0] if heads else None), rel, heads


def size_kb(p):
    total = 0
    for base, sub, files in os.walk(p):
        sub[:] = [d for d in sub if d != "__pycache__"]
        for f in files:
            try:
                total += os.path.getsize(os.path.join(base, f))
            except OSError:
                pass
    return total // 1024


def count_files(p):
    n = 0
    for base, sub, files in os.walk(p):
        if ".git" in sub:
            sub.remove(".git")
        n += len(files)
    return n


if not os.path.exists(LOG):
    with open(LOG, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("sim\tstatus\tbranch\tall_release_branches\tcommit\tsize_kb\tfiles\tnote\tts\n")

os.makedirs(DEST_ROOT, exist_ok=True)
for sim in SIMS:
    dest = os.path.join(DEST_ROOT, sim)
    branch, rel, heads = latest_branch(sim)
    note = ""
    if os.path.isdir(os.path.join(dest, ".git")):
        status = "SKIP"
        commit = sh(["git", "-C", dest, "rev-parse", "HEAD"]).stdout.strip()
    elif not branch:
        status, commit = "FAIL", ""
        note = "无可用分支"
    else:
        r = sh(["git", "clone", "--depth", "1", "--single-branch", "--branch", branch,
                f"https://github.com/phetsims/{sim}.git", dest])
        status = "OK" if r.returncode == 0 else "FAIL"
        note = "" if status == "OK" else r.stderr.strip()[:180].replace("\t", " ")
        commit = sh(["git", "-C", dest, "rev-parse", "HEAD"]).stdout.strip() if status == "OK" else ""
    size = size_kb(dest) if os.path.isdir(dest) else ""
    files = count_files(dest) if os.path.isdir(dest) else ""
    line = f"{sim}\t{status}\t{branch}\t{','.join(rel or [])}\t{commit}\t{size}\t{files}\t{note}\t{time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
    with open(LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(line)
    print(line.rstrip())
    sys.stdout.flush()
print("PHET DONE")
