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


def deliverability(raw: bytes) -> dict:
    """只看仿真主页面（不是外层介绍页）能不能断网加载、有没有运行时控制面。

    区分两族很关键：webejs 导出的主页用 `<script src="https://cdn.jsdelivr.net/...">` 取运行时，
    EJS 6.02 导出的主页把 `_ejs_library/` 装在包里、0 个远程加载。此前的「28/28 都有包外引用」
    是把整包所有 HTML（含包装页）混在一起数的，会把「主页面其实能用」这条好消息一起埋掉。
    控制面按文本特征判定（`var _model` + serialize/unserialize），真机数值另见
    `ejss-runtime-evidence.json`；这里只回答「哪些包值得拿去实测」。
    """
    import posixpath
    import re

    out = {"family": None, "entry": None, "entry_bytes": None, "remote_loads": None,
           "local_loads_missing": 0, "model_global": False, "serialize": False,
           "unserialize": False, "baked_var_comments": 0}
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = set(zf.namelist())
            pages = [n for n in names if n.lower().endswith((".html", ".xhtml"))]
            if not pages:
                return out
            low = {n.lower(): n for n in pages}
            if "_simulation.xhtml" in low:            # webejs 导出：根下就叫 _simulation.xhtml
                out["family"], entry = "webejs", low["_simulation.xhtml"]
            else:                                     # EJS 6.02 导出：<Name>_Simulation.xhtml
                hit = [n for n in pages if n.lower().endswith("_simulation.xhtml")]
                if hit:
                    out["family"], entry = "ejs6", sorted(hit)[-1]
            if not entry:
                return out
            raw_bytes = zf.read(entry)
            out["entry"], out["entry_bytes"] = entry, len(raw_bytes)
            text = decode(raw_bytes)
            out["model_global"] = bool(re.search(r"\bvar\s+_model\b", text))
            out["serialize"] = "serialize" in text
            out["unserialize"] = "unserialize" in text
            out["baked_var_comments"] = len(re.findall(r"EjsS Model\.Variables", text))
            remote = local_missing = 0
            # 不能只按标签属性匹配：webejs 那族的 <script src> 是运行时用 document.write 拼出来的，
            # 远程地址在 JS 字符串里。所以 src="http…" 一律算远程加载；href 只在 <link> 上算，
            # 正文里的 <a href="http…">（许可链接等）不算加载，别把它当成「断网打不开」。
            remote = len(re.findall(r'src\s*=\s*["\']https?://', text, re.I))
            remote += len(re.findall(r'<link\b[^>]{0,400}?href\s*=\s*["\']https?://', text, re.I | re.S))
            for m in re.finditer(r'<(?:script|link|iframe|img)\b[^>]{0,400}?\b(?:src|href)="([^"]+)"', text, re.I | re.S):
                ref = m.group(1)
                if ref.startswith(("http:", "https:", "data:", "#", "/")):
                    continue
                target = posixpath.normpath(posixpath.join(posixpath.dirname(entry), ref))
                if target.lstrip("/") not in names:
                    local_missing += 1
            out["remote_loads"], out["local_loads_missing"] = remote, local_missing
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
        deliv = deliverability(raw)
        for name, size in sources:
            key = Path(name).stem.lower()
            entry = {"zip": rel, "member": name, "member_bytes": size, "self_contained": has_runtime,
                     "launcher": top["launcher"], "kind": "ejss", "bundle_health": health,
                     "deliverability": deliv}
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
            deliv_inner = deliverability(inner)
            for mname, msize in got["ejss"]:
                key = Path(mname).stem.lower()
                if key in models:
                    continue
                entry = {"zip": f"{rel}::{name}", "member": mname, "member_bytes": msize,
                         "self_contained": bool(got["runtime"]), "launcher": got["launcher"],
                         "kind": "ejss", "deliverability": deliv_inner}
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

    def dv(m):
        return m.get("deliverability") or {}

    fam = {}
    for m in vals:
        fam[dv(m).get("family") or "no-sim-page"] = fam.get(dv(m).get("family") or "no-sim-page", 0) + 1
    offline_ready = [m for m in vals if dv(m).get("entry") and not dv(m).get("remote_loads")
                     and not dv(m).get("local_loads_missing")]
    needs_localise = [m for m in vals if dv(m).get("remote_loads")]
    entry_broken = [m for m in vals if dv(m).get("local_loads_missing")]
    with_global = [m for m in vals if dv(m).get("model_global")]
    with_serde = [m for m in vals if dv(m).get("serialize") and dv(m).get("unserialize")]
    with_baked = [m for m in vals if dv(m).get("baked_var_comments")]

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
        "entry_page_family_breakdown": fam,
        "entry_page_offline_ready": len(offline_ready),
        "entry_page_needs_cdn_localise": len(needs_localise),
        "entry_page_with_missing_local_ref": len(entry_broken),
        "entry_page_with_model_global": len(with_global),
        "entry_page_with_serialize_unserialize": len(with_serde),
        "entry_page_with_baked_var_comments": len(with_baked),
        "note_bundle_health_scope": "上面两个 refs_* 计数是把包里所有 HTML（含外层介绍页）混在一起数的；"
                                    "仿真主页面能不能断网加载看 entry_page_* 这几项，两者结论不同，别互相替代。",
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
        d = m.get("deliverability") or {}
        print(f"  {m['zip']} :: {m['member']} | 参数 {m.get('public_vars')} | 自包含 {m.get('self_contained')} | "
              f"{m['title'][:30]}")
        print(f"      主页 {d.get('family')} remote_loads={d.get('remote_loads')} "
              f"local_missing={d.get('local_loads_missing')} _model={d.get('model_global')} "
              f"serde={int(bool(d.get('serialize') and d.get('unserialize')))} "
              f"烘焙注释={d.get('baked_var_comments')}")
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
