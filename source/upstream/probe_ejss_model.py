#!/usr/bin/env python3
"""读出 EJSS / WebEJS 模型（.ejs / .ejss / 含 _source.ejss 的 zip）的参数面与代码块。

EJSS 系模型没有像 Ray Optics 那样的「场景 JSON 接口」：它的可改参数与物理方程都写在
XML 定义里，所以「Agent 能不能改这个实验」这件事，第一步就是把这个 XML 解析成清单。
本脚本只做静态解析（不执行模型、不需要浏览器），因此它证明的是**参数面可读可改**，
不证明**跑起来读数对**——那一步要 webejs 运行时 + 浏览器，仍然 pending。

用法：
    python source/upstream/probe_ejss_model.py <模型路径.ejs|.ejss|.zip> [--json 输出文件]
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path

CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
VARIABLE = re.compile(r"<Variable>(.*?)</Variable>", re.S)


def strip_cdata(text: str) -> str:
    m = CDATA.search(text or "")
    return (m.group(1) if m else (text or "")).strip()


def field(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", block, re.S)
    return strip_cdata(m.group(1)) if m else ""


def load_source(path: Path) -> tuple[str, str]:
    """返回 (XML 文本, 实际读到的成员名)。EJSS 存盘常见 UTF-16 带 BOM。"""
    if path.suffix.lower() == ".zip" or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for cand in ("_source.ejss", "_source.ejs"):
                if cand in z.namelist():
                    raw = z.read(cand)
                    return decode(raw), cand
            raise SystemExit(f"{path} 里没有找到 _source.ejss / _source.ejs；成员示例：{z.namelist()[:6]}")
    return decode(path.read_bytes()), path.name


def decode(raw: bytes) -> str:
    # 只看 BOM 判 UTF-16：不带 BOM 的 ASCII/UTF-8 文件长度为偶数时能被 utf-16 「解成功」，
    # 结果是整篇乱码却毫不报错（2026-10-19 实测：仿真页里的 var _model / CDN 引用因此全部读成 0）。
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff") or raw[:4] == b"\x00\x00\xfe\xff":
        return raw.decode("utf-16")
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit("无法解码模型 XML")


def probe(xml: str) -> dict:
    variables = []
    for m in VARIABLE.finditer(xml):
        b = m.group(1)
        declared = field(b, "Domain")
        variables.append({
            "name": field(b, "Name"),
            "type": field(b, "Type"),
            "domain": declared or "undeclared",
            "domain_declared": bool(declared),
            "dimension": field(b, "Dimension"),
            "value": field(b, "Value"),
            "comment": field(b, "Comment"),
        })
    code_blocks = {}
    for tag in ("Osejs.Model.Initialization", "Osejs.Model.Evolution", "Osejs.Model.Constraints",
                "Osejs.Model.Library", "Osejs.Description"):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.S)
        if m:
            chunks = [strip_cdata(c) for c in CDATA.findall(m.group(1))] or [m.group(1)]
            joined = "\n".join(c for c in chunks if c.strip())
            code_blocks[tag] = joined[:4000] + ("…（截断）" if len(joined) > 4000 else "")
    # EJSS 的 <Domain> 只在带"参数页"的模型里写；导出包普遍省略它，省略不等于不可改。
    public = [v for v in variables if v["domain"] not in ("internal", "private")]
    return {
        "title": field(xml, "Title") or field(xml, "Osejs.Model.ModelName"),
        "author": field(xml, "Author"),
        "copyright": field(xml, "Copyright"),
        "library": field(xml, "Osejs.Model.Library") and "有" or "无",
        "frames_per_second": field(xml, "Osejs.Model.FramesPerSecond"),
        "steps_per_display": field(xml, "Osejs.Model.StepsPerDisplay"),
        "use_interpreter": field(xml, "UseInterpreter"),
        "variables_total": len(variables),
        "variables_public": len(public),
        "variables_domain_declared": sum(1 for v in variables if v["domain_declared"]),
        "public_variables": public,
        "internal_or_private_variables": [v["name"] for v in variables if v["domain"] == "internal"],
        "code_blocks": code_blocks,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    xml, member = load_source(path)
    out = {"model_file": str(path), "source_member": member, **probe(xml)}
    print(f"{out['title']} ｜ 作者 {out['author']} ｜ 变量 {out['variables_total']} 个（public {out['variables_public']}）")
    for v in out["public_variables"]:
        print(f"  - {v['name']:<12} {v['type']:<8} = {v['value'][:38]:<38} {v['comment'][:60]}")
    for k, code in out["code_blocks"].items():
        head = code.strip().splitlines()[:6]
        print(f"  [{k}] {len(code)} 字节：{ ' | '.join(h.strip() for h in head)[:260] }")
    if "--json" in sys.argv:
        dst = Path(sys.argv[sys.argv.index("--json") + 1])
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("→", dst)
    return 0


if __name__ == "__main__":
    sys.exit(main())
