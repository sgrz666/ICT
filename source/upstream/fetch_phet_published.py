"""安装 PhET 官方发布的 HTML5 成品（单文件、可离线），并逐份核验身份与自包含性。

上一轮把「PhET 官方发布成品」判成装不上（测的 5 种 URL 形态全 404），实际形态是
    https://phet.colorado.edu/sims/html/<sim>/latest/<sim>_all.html
这份脚本会下载、解出版本号与许可证行、算 sha256，并检查文件里有没有指向外的
<script src> / <link href>——即「单文件离线能不能真跑」的最小证据。

用法：python source/upstream/fetch_phet_published.py [--check-only]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "phet" / "published"
BASE = "https://phet.colorado.edu/sims/html/{sim}/latest/{sim}_all.html"

# 只装与 18 条优先实验对得上的那些；括号里是对应的实验
SIMS = {
    "bending-light": "光的折射与折射定律 / 全反射与临界角 / 三棱镜色散",
    "geometric-optics": "平面镜成像 / 凹透镜成像",
    "wave-interference": "双缝干涉（水波类比）",
    "pendulum-lab": "单摆周期规律",
    "energy-skate-park-basics": "机械能守恒（补充）",
    "friction": "摩擦生热（补充）",
    "circuit-construction-kit-dc": "欧姆定律 / 串联和并联电路",
    "ohms-law": "欧姆定律（简化版）",
    "capacitor-lab-basics": "RC 充放电 / 电容",
    "gas-properties": "理想气体状态变化",
    "states-of-matter": "物态变化（补充）",
    "gravity-and-orbits": "太阳系与开普勒定律",
    "charges-and-fields": "带电粒子在电场中（3D 电磁的 2D 类比）",
}
VERSION = re.compile(r"(\d+\.\d+\.\d+[A-Za-z0-9_.\-]*)")
LICENSE = re.compile(r"(Creative Commons Attribution-NonCommercial 4\.0[^.\n]*|GNU GENERAL PUBLIC LICENSE[^.\n]*|GNU GPLv3)", re.I)
EXTERNAL = re.compile(r"""<(script[^>]+src|link[^>]+href)\s*=\s*["']https?://""", re.I)


def fetch(sim: str) -> bytes:
    req = urllib.request.Request(BASE.format(sim=sim), headers={"User-Agent": "EduForge-resource-inventory/1.0"})
    with urllib.request.urlopen(req, timeout=180) as r:
        if r.status != 200:
            raise RuntimeError(f"HTTP {r.status}")
        return r.read()


def inspect(sim: str, raw: bytes) -> dict:
    text = raw.decode("utf-8", "replace")
    m = VERSION.search(text[:4000]) or VERSION.search(text[:200000])
    lm = LICENSE.search(text)
    return {
        "sim": sim,
        "file": f"source/upstream/phet/published/{sim}_all.html",
        "maps_to_experiments": SIMS[sim],
        "bytes": len(raw),
        "sha256_16": hashlib.sha256(raw).hexdigest()[:16],
        "version": m.group(1) if m else None,
        "license_line": (lm.group(1).strip() if lm else None),
        "external_script_or_link_tags": len(EXTERNAL.findall(text)),
        "has_production_meta": 'name="phet-sim-level" content="production"' in text[:1200],
        "source_url": BASE.format(sim=sim),
    }


def main() -> int:
    check_only = "--check-only" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for sim in SIMS:
        dst = OUT / f"{sim}_all.html"
        try:
            if dst.exists() and check_only:
                raw = dst.read_bytes()
                note = "recheck"
            else:
                raw = fetch(sim)
                dst.write_bytes(raw)
                note = "downloaded"
        except Exception as exc:
            rows.append({"sim": sim, "status": "FAILED", "error": f"{type(exc).__name__}: {exc}"})
            print(f"FAIL {sim}: {type(exc).__name__}: {exc}")
            continue
        info = inspect(sim, raw)
        info["status"] = note
        rows.append(info)
        print(f"OK   {sim:34} v{info['version'] or '?':10} {info['bytes']/1e6:6.2f} MB  外链标签 {info['external_script_or_link_tags']}  {info['license_line'] or '许可未解析'}")

    (HERE / "phet-published.json").write_text(
        json.dumps({"source": "PhET Interactive Simulations, University of Colorado Boulder",
                    "url_form": BASE, "sims": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    (HERE / "phet-published-log.tsv").write_text(
        "sim\tversion\tbytes\tsha256_16\texternal_tags\tstatus\n"
        + "".join(f"{r.get('sim')}\t{r.get('version') or '-'}\t{r.get('bytes', '-')}\t{r.get('sha256_16', '-')}"
                  f"\t{r.get('external_script_or_link_tags', '-')}\t{r.get('status')}\n" for r in rows),
        encoding="utf-8")
    ok = sum(1 for r in rows if r.get("status") in ("downloaded", "recheck"))
    print(f"完成 {ok}/{len(SIMS)}，清单见 phet-published.json")
    return 0 if ok == len(SIMS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
