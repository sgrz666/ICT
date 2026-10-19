"""清点 OSP 家族 6 仓里到底有多少个「Agent 能读参数、能取物理代码」的 EJSS 模型。

区分三种东西：模型源码（.ejss）、可离线运行的交付包（自带 _ejs_library 运行时 + HTML 启动页）、
以及只有网页壳没有模型的压缩包。嵌套 zip 只下钻一层，按模型名去重。

用法：python source/upstream/survey_ejss_models.py [--json]
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from probe_ejss_model import decode, probe  # noqa: E402

ROOTS = ["resources", "webejs", "STP", "csm", "osp", "osp_ejs"]
SKIP_MEMBER = ("__MACOSX",)


def bundle_health(raw: bytes) -> dict:
    """核对交付包自己声明的文件与 HTML 里引用的路径，是否真在包里。

    这一步专门用来防止「包里带了运行时 = 浏览器里能打开」这种口头结论。
    引用解析不出来的分两类：跳出包外（要连同上层目录一起部署）与包内缺失（生成器自己的 bug）。
    """
    import re

    out = {"meta_source": None, "meta_source_present": None,
           "refs_checked": 0, "refs_escape_bundle": 0, "refs_missing_inside": 0, "examples": []}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            for cand in ("_metadata.txt",):
                if cand in names:
                    meta = zf.read(cand).decode("utf-8", "replace")
                    m = re.search(r"^source:\s*(.+)$", meta, re.M)
                    if m:
                        out["meta_source"] = m.group(1).strip()
                        out["meta_source_present"] = out["meta_source"] in names
                    break
            for name in list(names):
                if not name.lower().endswith((".html", ".xhtml")):
                    continue
                text = zf.read(name).decode("utf-8", "replace")
                for ref in re.findall(r'(?:src|href)="([^"?#]+)', text):
                    if ref.startswith(("http", "data:", "mailto:")):
                        continue
                    out["refs_checked"] += 1
                    if ref.startswith("../"):
                        out["refs_escape_bundle"] += 1
                        if len(out["examples"]) < 3:
                            out["examples"].append(f"{name} -> {ref} (指向包外)")
                        continue
                    target = (Path(name).parent / ref).as_posix()
                    if target not in names and not any(n.endswith("/" + ref) for n in names):
                        out["refs_missing_inside"] += 1
                        if len(out["examples"]) < 3:
                            out["examples"].append(f"{name} -> {ref} (包内缺失)")
    except Exception:
        pass
    return out


def zip_entries(raw: bytes):
    """列出 zip 里的模型源码、运行时、启动页与嵌套 zip。"""
    out = {"ejss": [], "ejs": [], "runtime": None, "launcher": None, "nested": [], "html": 0}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            for info in zf.infolist():
                name = info.filename
                if any(part in SKIP_MEMBER for part in name.split("/")):
                    continue
                low = name.lower()
                if low.endswith(".ejss"):
                    out["ejss"].append((name, info.file_size))
                elif low.endswith(".ejs"):
                    out["ejs"].append((name, info.file_size))
                elif low.endswith(".html"):
                    out["html"] += 1
                    if "ejss_html" in low or "launch" in low:
                        out["launcher"] = name
                elif "_ejs_library/ejss.v1.min.js" in low or "_ejs_library/ejss" in low:
                    out["runtime"] = name
                elif low.endswith(".zip"):
                    out["nested"].append((name, info.file_size))
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def walk_zips():
    for root_name in ROOTS:
        root = HERE / root_name
        if not root.is_dir():
            continue
        import os

        for base, sub, files in os.walk(root):
            sub[:] = [d for d in sub if d not in {".git", "node_modules", "build", "dist"}]
            for f in files:
                if f.lower().endswith(".zip"):
                    yield Path(base) / f


def model_info(src_bytes: bytes) -> dict:
    xml = decode(src_bytes)
    info = probe(xml)
    return {
        "title": (info.get("title") or "").strip(),
        "public_vars": info.get("variables_public", 0),
        "vars_total": info.get("variables_total", 0),
        "code_blocks": {k: len(v) for k, v in (info.get("code_blocks") or {}).items() if v},
    }


def main() -> int:
    models: dict[str, dict] = {}
    containers = 0
    shell_zips = 0
    scanned = 0

    for path in sorted(walk_zips()):
        scanned += 1
        raw = path.read_bytes()
        top = zip_entries(raw)
        has_runtime = bool(top["runtime"])
        sources = list(top["ejss"])
        rel = str(path.relative_to(HERE))
        if not sources and not top["nested"]:
            if top["ejs"]:
                models.setdefault(rel, {"zip": rel, "kind": "legacy_ejs", "public_vars": None})
            else:
                shell_zips += 1
            continue
        if not sources:
            containers += 1  # 只是把一批子 zip 打在一起的外层包
        health = bundle_health(raw)
        for name, size in sources:
            key = Path(name).stem.lower()
            entry = {"zip": rel, "member": name, "member_bytes": size, "self_contained": has_runtime,
                     "launcher": top["launcher"], "kind": "ejss", "bundle_health": health}
            if key not in models:
                try:
                    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                        entry.update(model_info(zf.read(name)))
                except Exception as exc:
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                models[key] = entry
        # 下钻一层：外层包里每个子 zip 也是一个交付包
        for name, _size in top["nested"]:
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    inner = zf.read(name)
            except Exception:
                continue
            got = zip_entries(inner)
            for mname, msize in got["ejss"]:
                key = Path(mname).stem.lower()
                if key in models:
                    continue
                entry = {"zip": f"{rel}::{name}", "member": mname, "member_bytes": msize,
                         "self_contained": bool(got["runtime"]), "launcher": got["launcher"], "kind": "ejss"}
                try:
                    with zipfile.ZipFile(io.BytesIO(inner)) as zf2:
                        entry.update(model_info(zf2.read(mname)))
                except Exception as exc:
                    entry["error"] = f"{type(exc).__name__}: {exc}"
                models[key] = entry

    vals = [m for m in models.values() if m.get("kind") == "ejss"]
    with_params = [m for m in vals if m.get("public_vars")]
    with_code = [m for m in vals if m.get("code_blocks")]
    self_contained = [m for m in vals if m.get("self_contained")]
    var_counts = sorted(m.get("public_vars") or 0 for m in with_params)

    declared_source_present = [m for m in vals if (m.get("bundle_health") or {}).get("meta_source_present") is True]
    escape_bundles = [m for m in vals if (m.get("bundle_health") or {}).get("refs_escape_bundle")]
    broken_inside = [m for m in vals if (m.get("bundle_health") or {}).get("refs_missing_inside")]

    summary = {
        "roots_scanned": ROOTS,
        "zip_files_scanned": scanned,
        "outer_container_zips": containers,
        "zip_without_model": shell_zips,
        "ejss_models_unique": len(vals),
        "models_with_param_table": len(with_params),
        "models_with_code": len(with_code),
        "models_self_contained": len(self_contained),
        "models_declaring_source_present": len(declared_source_present),
        "models_with_refs_outside_bundle": len(escape_bundles),
        "models_with_refs_missing_inside": len(broken_inside),
        "public_vars_min": var_counts[0] if var_counts else None,
        "public_vars_median": var_counts[len(var_counts) // 2] if var_counts else None,
        "public_vars_max": var_counts[-1] if var_counts else None,
        "parse_errors": sum(1 for m in vals if m.get("error")),
    }
    if "--json" in sys.argv:
        out = HERE / "ejss-survey.json"
        out.write_text(
            json.dumps({"summary": summary, "models": sorted(models.values(), key=lambda m: m["zip"])},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"写入 {out}")
    for k, v in summary.items():
        print(f"{k}: {v}")
    print("—— 抽样 10 个模型 ——")
    for m in sorted(vals, key=lambda x: -(x.get("public_vars") or 0))[:10]:
        print(f"  {m['zip']} :: {m['member']} | 参数 {m.get('public_vars')} | 自包含 {m.get('self_contained')} | {m['title'][:30]}")
    print("—— 交付包内部引用的缺口（前 6 条）——")
    shown = 0
    for m in vals:
        for ex in (m.get("bundle_health") or {}).get("examples", []):
            if shown >= 6:
                break
            print(f"  {Path(m['zip']).name}: {ex}")
            shown += 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
