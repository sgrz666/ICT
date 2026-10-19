"""把 EJSS 导出包拼成断网能跑、且能改参数的可操作实验。

两族包实测长得不一样，处理方式也不同：
  · webejs 导出（`_simulation.xhtml`）：运行时走 jsDelivr CDN ⇒ 必须换成本机
    `webejs/static/assets/_ejs_library`，还得备 plotly（钉 1.x）与一个能跑回调的
    MathJax 替身，否则绘图链整个断（2026-10-19 实测过异常）。
  · EJS 6.02 导出（`<Name>_Simulation.xhtml`）：仿真页里 0 个 https，运行时就在包里
    `_ejs_library/` ⇒ 解压即用；坏路径只在外层介绍页。

改参数：两族都把默认值烘焙成 JS 赋值，且 EJS 6.02 的赋值行带
`// EjsS Model.Variables.<页>.Vars.<name>` 注释 ⇒ 可以按变量名精确改写，不用猜。
本脚本同时改编译页与 `.ejss` 源码，保证重新编译也得到同样的实验。

用法：
  python source/upstream/assemble_ejss_offline.py <zip 路径> [--param y0=45] [--param a=-9.8]
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRATCH = HERE / ".webejs-offline"
ASSETS = HERE / "webejs" / "static" / "assets" / "_ejs_library"

RUNTIME_LOCAL = {
    "css/ejss.css": "assets/_ejs_library/css/ejss.css",
    "scripts/textresizedetector.js": "assets/_ejs_library/scripts/textresizedetector.js",
    "ejsS.v1.min.js": "assets/_ejs_library/ejsS.v1.min.js",
}
CDN_MAP = {
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/css/ejss.css":
        RUNTIME_LOCAL["css/ejss.css"],
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/scripts/textresizedetector.js":
        RUNTIME_LOCAL["scripts/textresizedetector.js"],
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/ejsS.v1.min.js":
        RUNTIME_LOCAL["ejsS.v1.min.js"],
    "https://cdn.plot.ly/plotly-latest.min.js": "assets/vendor/plotly-latest.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.1/MathJax.js?config=TeX-MML-AM_CHTML":
        "assets/vendor/mathjax-wrapper.js",
}
# 上游写的是 plotly-latest.min.js（1.x 时代的别名）；EJSS 的绘图代码按 1.x 写，
# 拿 2.x 会在 line 8 反复抛 "reading 'length'"。
PLOTLY_URL = "https://cdn.plot.ly/plotly-1.58.5.min.js"
# 只给空对象会让模型在 MathJax.Hub.Queue(...) 那行抛异常、绘图链整个断 ⇒ 替身必须跑回调。
MATHJAX_SHIM = """/* 离线替身：公式排版降级，但 Hub.Queue 必须真的执行排进队列的回调。 */
window.MathJax = {
  Hub: {
    Queue: function () {
      for (var i = 0; i < arguments.length; i++) {
        var job = arguments[i];
        try {
          if (typeof job === "function") job();
          else if (Array.isArray(job) && typeof job[0] === "function") job[0].apply(null, job.slice(1));
          else if (Array.isArray(job) && job[0] && typeof job[0][job[1]] === "function")
            job[0][job[1]].apply(job[0], job.slice(2));
        } catch (e) { /* 排版失败不影响物理 */ }
      }
    },
    Typeset: function () {},
    Register: { Startup: { onLoad: function () {} } }
  },
  App: { TeX: { Chapter: { require: function () {} } } }
};
"""


def decode_bytes(raw: bytes) -> str:
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "replace")
    return raw.decode("utf-8", "replace")


def bake_page(name: str, text: str, old: str, value: str):
    """只改写当前值等于 .ejss 默认值的那几处赋值。

    不做这个限定的话，`y = ymin;` 之外的分支赋值（如另一套初始条件里的 y = -40.0）
    也会被一起改掉，那是改坏模型而不是改参数。
    """
    pat = re.compile(rf"([;{{>\s])(?<![\w.$]){re.escape(name)}\s*=\s*{re.escape(old)}(\s*;[^\n]*?)")
    hits = []

    def sub(m):
        hits.append(m.group(0).strip())
        return f"{m.group(1)}{name} = {value}{m.group(2)}"

    new, n = pat.subn(sub, text)
    return new, n, hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("zip_path")
    ap.add_argument("--param", action="append", default=[])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    src = Path(args.zip_path)
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    assert src.exists(), f"找不到包：{src}"

    params = {}
    for item in args.param:
        m = re.match(r"^([\w.]+)=(-?[\d.]+)$", item)
        assert m, f"--param 要写成 name=value，收到 {item!r}"
        params[m.group(1)] = m.group(2)

    with zipfile.ZipFile(src) as zf:
        names = zf.namelist()
        sim_pages = [n for n in names if n.endswith("_Simulation.xhtml") or n == "_simulation.xhtml"]
        ejss = [n for n in names if n.endswith(".ejss")]
        raw_all = {n: zf.read(n) for n in names if not n.endswith("/")}
    assert sim_pages, f"{src.name} 里没有仿真页"
    entry = sim_pages[0]
    family = "webejs" if entry == "_simulation.xhtml" else "ejs6"

    # 从 .ejss 参数表取默认值：改写只针对「当前值 == 默认值」的赋值
    defaults = {}
    for e in ejss:
        xml = decode_bytes(raw_all[e])
        for m in re.finditer(r"<Variable>.*?<Name><!\[CDATA\[(.*?)\]\]></Name>.*?"
                             r"<Value><!\[CDATA\[(.*?)\]\]></Value>.*?</Variable>", xml, re.S):
            defaults.setdefault(m.group(1), m.group(2).strip())
    unknown = [k for k in params if k not in defaults]
    if unknown:
        print(f"注意：{unknown} 不在 .ejss 参数表里，只按字面值匹配")

    out = Path(args.out) if args.out else SCRATCH / (src.stem.replace(".zip", ""))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for n, data in raw_all.items():
        dst = out / n
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)

    report = {"zip": src.name, "family": family, "entry": entry, "out": str(out),
              "cdn_rewrites": 0, "param_rewrites": {}, "https_left": 0, "notes": []}

    if family == "webejs":
        for rel, dst_rel in RUNTIME_LOCAL.items():
            dst = out / dst_rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ASSETS / rel, dst)
        plotly = out / "assets/vendor/plotly-latest.min.js"
        plotly.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(PLOTLY_URL, headers={"User-Agent": "EduForge-offline"}), timeout=180) as r:
            plotly.write_bytes(r.read())
        (out / "assets/vendor/mathjax-wrapper.js").write_text(MATHJAX_SHIM, encoding="utf-8")
        report["notes"].append(f"本地化运行时 + plotly 1.58.5({plotly.stat().st_size}B) + MathJax 替身")

    pages = {entry, *ejss, *[n for n in names if n.endswith((".html", ".xhtml"))]}
    for page in pages:
        p = out / page
        if not p.exists():
            continue
        text = decode_bytes(p.read_bytes())
        if family == "webejs":
            for cdn, local in CDN_MAP.items():
                if cdn in text:
                    report["cdn_rewrites"] += text.count(cdn)
                    text = text.replace(cdn, local)
        for name, value in params.items():
            old = defaults.get(name)
            if old is None:
                continue
            text, n, hits = bake_page(name, text, old, value)
            if n:
                got = report["param_rewrites"].setdefault(name, {"count": 0, "from": old, "value": value, "sample": None})
                got["count"] += n
                got["sample"] = got["sample"] or (hits[0][:110] if hits else None)
        p.write_text(text, encoding="utf-8")

    entry_text = decode_bytes((out / entry).read_bytes())
    report["https_left"] = len(re.findall(r'(?:src|href)\s*=\s*["\']https?://', entry_text))
    print(f"{src.name}  family={family}  entry={entry}")
    print(f"  输出 → {out}")
    for note in report["notes"]:
        print(f"  {note}")
    print(f"  CDN→本地 改写 {report['cdn_rewrites']} 处；仿真页剩余 https 引用 {report['https_left']} 处")
    for name, info in report["param_rewrites"].items():
        print(f"  参数 {name}：{info['from']} → {info['value']}，改了 {info['count']} 处  例：{info['sample']}")
    missed = [k for k in params if k not in report["param_rewrites"]]
    if missed:
        print(f"  没改写（不在参数表，或当前值不等于默认值）：{missed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
