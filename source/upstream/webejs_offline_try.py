"""把 WebEJS 导出的 EJSS 模型拼成真正离线的可运行包，并检查还剩几个外链。

上游那批 `webejs_model_*.zip` 的 `_simulation.xhtml` 是从 jsDelivr 的 GitHub CDN
取运行时（ejsS.v1.min.js / ejss.css / textresizedetector.js）再外加 plotly、MathJax，
所以「包里带了模型」离「断网能跑」还差一步：把 CDN 换成本地相对路径。

本脚本只做机械替换与拷贝，不碰上游任何一个字节；产物落在 .webejs-offline/（不入库）。

用法：python source/upstream/webejs_offline_try.py [--param N=8]
"""

from __future__ import annotations

import re
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODEL = HERE / "resources" / "docs" / "CollectionTest" / "webejs_model_MultislitDiffraction.zip"
ASSETS = HERE / "webejs" / "static" / "assets" / "_ejs_library"
OUT = HERE / ".webejs-offline" / "multislit"

# CDN → 本地。runtime 三件套本机已有（webejs 仓），plotly/MathJax 需要下载
CDN_MAP = {
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/css/ejss.css":
        "assets/_ejs_library/css/ejss.css",
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/scripts/textresizedetector.js":
        "assets/_ejs_library/scripts/textresizedetector.js",
    "https://cdn.jsdelivr.net/gh/OpenSourcePhysics/webejs/static/assets/_ejs_library/ejsS.v1.min.js":
        "assets/_ejs_library/ejsS.v1.min.js",
    "https://cdn.plot.ly/plotly-latest.min.js": "assets/vendor/plotly-latest.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/mathjax/2.7.1/MathJax.js?config=TeX-MML-AM_CHTML":
        "assets/vendor/mathjax-wrapper.js",
}
VENDOR_URLS = {
    # 上游写的是 plotly-latest.min.js（1.x 时代的别名）；EJSS 的绘图代码按 1.x API 写，
    # 拿 2.x 会在 line 8 反复抛 "reading 'length'"，所以钉在最后一个 1.x
    "assets/vendor/plotly-latest.min.js": "https://cdn.plot.ly/plotly-1.58.5.min.js",
}
# MathJax 在包里只用来排版公式，但模型会调 MathJax.Hub.Queue(...) 并把回调排在队列里。
# 只给一个空对象会让那一行抛异常、把整条绘图链打断（本轮实测过），所以 Queue 必须真的执行回调。
MATHJAX_SHIM = """/* 离线替身：公式排版降级，但 Hub.Queue 必须照跑回调，否则 EJSS 的绘图链会在
   "MathJax.Hub.Queue is not a function" 处断掉（2026-10-19 实测就是这个异常）。 */
window.MathJax = {
  Hub: {
    Queue: function () {
      for (var i = 0; i < arguments.length; i++) {
        var job = arguments[i];
        try {
          if (typeof job === "function") job();
          else if (Array.isArray(job) && typeof job[0] === "function") job[0].apply(null, job.slice(1));
          else if (Array.isArray(job) && typeof job[0] === "object" && job[0] && typeof job[0][job[1]] === "function")
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
BAKED = re.compile(r"(?m)^(\s*)(N|D|d|lambda|L|width|height)(\s*=\s*)(-?[\d.]+)(;)")


def parse_overrides(argv) -> dict:
    """接受两种写法：--param N=8 或直接 N=8。"""
    out, i = {}, 0
    while i < len(argv):
        arg = argv[i]
        kv = argv[i + 1] if arg == "--param" and i + 1 < len(argv) else arg
        m = re.match(r"^(N|D|d|lambda|L|width|height)=(-?[\d.]+)$", kv)
        if m:
            out[m.group(1)] = m.group(2)
            i += 2 if arg == "--param" else 1
            continue
        i += 1
    return out


def main() -> int:
    overrides = parse_overrides(sys.argv[1:])

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    with zipfile.ZipFile(MODEL) as zf:
        zf.extractall(OUT)

    # 1) 拷本机运行时
    copied = []
    for rel in ("css/ejss.css", "scripts/textresizedetector.js", "ejsS.v1.min.js"):
        src = ASSETS / rel
        if not src.exists():
            print(f"缺本机资源：{src}")
            return 1
        dst = OUT / "assets" / "_ejs_library" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied.append((rel, src.stat().st_size, dst.stat().st_size))

    # 2) 下载第三方（plotly）
    downloaded = []
    for rel, url in VENDOR_URLS.items():
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "EduForge-offline-assembly"}), timeout=180) as r:
                dst.write_bytes(r.read())
            downloaded.append((rel, url, dst.stat().st_size))
        except Exception as exc:
            downloaded.append((rel, url, f"FAILED {type(exc).__name__}: {exc}"))

    # MathJax 只用于渲染公式，离线包里给一个 no-op shim，避免 404 打断脚本执行
    shim = OUT / "assets" / "vendor" / "mathjax-wrapper.js"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text(MATHJAX_SHIM, encoding="utf-8")

    # 3) 重写 _simulation.xhtml 与 _main.html 里的 CDN 路径
    rewrites = []
    for name in ("_simulation.xhtml", "_main.html", "index.html"):
        p = OUT / name
        if not p.exists():
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        n = 0
        for cdn, local in CDN_MAP.items():
            if cdn in t:
                n += t.count(cdn)
                t = t.replace(cdn, local)
        if overrides:
            def sub(m):
                k = m.group(2)
                return f"{m.group(1)}{k}{m.group(3)}{overrides.get(k, m.group(4))}{m.group(5)}" if k in overrides else m.group(0)
            t, _ = BAKED.subn(sub, t)
        p.write_text(t, encoding="utf-8")
        rewrites.append((name, n))

    # 4) 剩余外链（file:// 下会失败的点）
    remaining = []
    for p in sorted(OUT.rglob("*")):
        if p.is_file() and p.suffix.lower() in (".html", ".xhtml", ".js", ".css"):
            txt = p.read_text(encoding="utf-8", errors="replace")
            for m in re.finditer(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', txt):
                remaining.append((p.relative_to(OUT).as_posix(), m.group(1)))

    print(f"解包 → {OUT}")
    for rel, a, b in copied:
        print(f"  拷贝 _ejs_library/{rel}: {a} → {b} 字节")
    for row in downloaded:
        print(f"  下载 {row[0]} ← {row[1]}: {row[2]}")
    print(f"  MathJax shim: {shim.stat().st_size} 字节（公式渲染降级，物理不受影响）")
    for name, n in rewrites:
        print(f"  改写 {name}: {n} 处 CDN → 本地")
    if overrides:
        print(f"  参数改写（直接改 _simulation.xhtml 里烘焙的赋值）: {overrides}")
    print(f"  剩余外链 {len(remaining)} 条:")
    for f, u in remaining[:12]:
        print(f"    {f} -> {u}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
