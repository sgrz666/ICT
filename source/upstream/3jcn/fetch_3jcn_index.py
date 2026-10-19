#!/usr/bin/env python3
"""Mirror 3JCN's static physics-sim catalogue pages and extract an inventory.

3JCN has no API and no git repo: the sims are listed on category pages of a static
site. This script downloads those pages once (into 3jcn/pages/) and writes
3jcn-inventory.json = every sim title + link found, so the resource is at least
searchable offline. Whether an individual sim is machine-controllable is NOT
established here (see the note field).
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
PAGES = HERE / "pages"
BASE = "https://www.new3jcn.com/"
CATS = [
    "index.html",
    "simulation.html",
    "motion_category.html",
    "optics_category.html",
    "thermo_category.html",
    "electricity_category.html",
    "modern_category.html",
    "labs_category.html",
]
UA = {"User-Agent": "Mozilla/5.0 (EduForge resource inventory; one-off fetch)"}


def fetch(name: str) -> str | None:
    dest = PAGES / name
    if dest.exists() and dest.stat().st_size > 0:
        return dest.read_text(encoding="utf-8", errors="replace")
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + name, headers=UA), timeout=40) as r:
            body = r.read().decode("utf-8", errors="replace")
        PAGES.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8")
        return body
    except Exception as exc:  # noqa: BLE001 - record, don't crash the inventory
        print(f"FAIL {name}: {exc}", file=sys.stderr)
        return None


def main() -> int:
    entries = []
    seen = set()
    fetched = 0
    for name in CATS:
        html = fetch(name)
        time.sleep(0.4)
        if html is None:
            continue
        fetched += 1
        for m in re.finditer(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S | re.I):
            href, inner = m.group(1).strip(), re.sub(r"<[^>]+>", "", m.group(2)).strip()
            inner = re.sub(r"\s+", " ", inner)
            if not inner or len(inner) < 4:
                continue
            if href.startswith(("mailto:", "javascript:", "#")):
                continue
            key = (href, inner)
            if key in seen:
                continue
            seen.add(key)
            entries.append({"page": name, "title": inner, "href": href if href.startswith("http") else BASE + href.lstrip("/")})

    out = {
        "source": BASE,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "pages_fetched": fetched,
        "pages_expected": len(CATS),
        "links": len(entries),
        "note": "3JCN 是静态站点，无仓库、无 API：这里只能拿到「有哪些演示」的目录与链接。"
        "单个演示是否可被 Agent 改参并未由本脚本证实（多为 applet/自研 3D 页面），"
        "所以只作为资源检索候选，不进引擎清单。",
        "entries": entries,
    }
    (HERE / "3jcn-inventory.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"pages {fetched}/{len(CATS)} | links {len(entries)} | -> 3jcn-inventory.json")
    return 0 if fetched == len(CATS) else 1


if __name__ == "__main__":
    sys.exit(main())
