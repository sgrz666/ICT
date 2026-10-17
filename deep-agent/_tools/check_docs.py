"""deep-agent 文档门：每个目录都要有 README，相对链接都要可解析。

用 os.walk 就地剪枝，绝不进入 2.7 GB 的上游克隆与缓存目录
（`find -not -path` 与 pathlib.rglob 都会先把整棵树走一遍，会挂住）。
退出码 0 = 通过；1 = 有缺失或缺链接。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 不要求 README、也不扫描链接的目录（理由见 ../AGENTS.md 第 3 节与 ../README.md 目录地图）
SKIP = {
    "deepseek-harness",  # 上游源码，内部 README 是上游资产
    "_corepack",         # pnpm 缓存
    ".dsh-home",         # 隔离的 DSH_HOME
    "harness-smoke-workspace",  # 一次性 Agent 工作区，含嵌套 .git
    "node_modules",
    "__pycache__",
    ".git",
    "runtime",
}

dirs = []
md_files = []
for base, subdirs, files in os.walk(ROOT):
    subdirs[:] = [d for d in subdirs if d not in SKIP]
    rel = os.path.relpath(base, ROOT)
    dirs.append("." if rel == "." else rel)
    for f in files:
        if f.endswith(".md"):
            md_files.append(os.path.join(base, f))

missing = [d for d in dirs if not os.path.isfile(os.path.join(ROOT, d, "README.md"))]

broken = []
# _probe/gh_*.md 是上游仓库的逐字快照，其中的相对链接指向**上游仓库内**的路径，
# 在本目录里必然解析不到。它们与 ICT 纪律里「source/upstream 内部 README 保持原样」同理，
# 属链接检查豁免对象（豁免理由写在 _probe/README.md）。
EXEMPT_LINK_CHECK = re.compile(r"[\\\\/]gh_[A-Za-z0-9_-]+\.md$")

for path in md_files:
    if EXEMPT_LINK_CHECK.search(path):
        continue
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        target = match.group(1).strip().split("#")[0]
        if not target or target.startswith(("http", "mailto:")):
            continue
        resolved = os.path.normpath(os.path.join(os.path.dirname(path), target))
        if not os.path.exists(resolved):
            broken.append((os.path.relpath(path, ROOT), target))

print(f"dirs checked: {len(dirs)} | md files: {len(md_files)}")
print(f"README missing: {len(missing)} {missing}")
print(f"broken links: {len(broken)}")
for item in broken:
    print("  BROKEN:", item[0], "->", item[1])
sys.exit(1 if (missing or broken) else 0)
