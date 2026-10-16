"""GATE-1 的人工那一半：用真实浏览器打开上游编辑器，经官方分享 URL 载入我们的种子场景，
在 UI 的 JSON 页签里改焦距，再读回序列化结果，确认上游接受改动、name 绑定不被破坏、仿真真的在跑。

内置浏览器视口不可用，所以这条路是 Playwright 起真实 Chromium；不是可选装饰。
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099/simulator/"
HASH = pathlib.Path(r"D:/codeplus/ICT/output/eduforge/reports/share-hash.txt").read_text().strip()
OUT = pathlib.Path(r"D:/codeplus/ICT/output/eduforge/reports/slice1-browser.json")

report: dict = {"url_with_hash_len": len(HASH), "steps": []}


def step(name, **kw):
    report["steps"].append(name)
    report[name] = kw


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1400, "height": 900})

    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

    page.goto(BASE + "#" + HASH, wait_until="networkidle")
    page.wait_for_timeout(2500)

    # 1) 页面与仿真表面
    canvas = page.evaluate(
        """() => [...document.querySelectorAll('canvas')].map(c => ({
             id: c.id, w: c.width, h: c.height}))"""
    )
    sized = [c for c in canvas if c["w"] > 0 and c["h"] > 0]
    step("load", title=page.title(), canvases=canvas, sized_canvases=len(sized),
         welcome_visible=page.locator("#welcome").count() > 0
         and page.locator("#welcome").is_visible(),
         page_errors=errors[:5])

    page.screenshot(path=str(OUT).replace(".json", "-loaded.png"), full_page=False)

    # 2) 找到 JSON/代码页签并读回当前场景
    tab_candidates = page.evaluate(
        """() => [...document.querySelectorAll('button, a, [role=tab], .nav-link')]
             .map(e => (e.innerText || '').trim()).filter(t => t && t.length < 24).slice(0, 40)"""
    )
    step("toolbar_texts", found=tab_candidates)

    # 上游 i18n 是中文；"代码" 即 JSON 编辑器页签
    opened = False
    for label in ("代码", "Code", "JSON"):
        loc = page.get_by_text(label, exact=False).first
        try:
            loc.click(timeout=2500)
            opened = True
            break
        except Exception:
            continue
    page.wait_for_timeout(1200)
    step("json_tab", opened=opened)

    # ACE 编辑器（ace-builds 在依赖里）
    editor_text = page.evaluate(
        """() => {
          const el = document.querySelector('.ace_text-layer');
          if (el) return el.innerText;
          const ta = document.querySelector('textarea');
          return ta ? ta.value : null;
        }"""
    )
    parsed = None
    if editor_text:
        try:
            parsed = json.loads(editor_text)
        except Exception as e:
            step("json_parse_error", error=str(e), sample=editor_text[:200])
    step("scene_from_ui", parsed=parsed is not None,
         objs=parsed and len(parsed.get("objs", [])),
         version=parsed and parsed.get("version"),
         names=parsed and [o.get("name") for o in parsed.get("objs", [])],
         lens_focalLength=parsed and next(
             (o.get("focalLength") for o in parsed.get("objs", []) if o.get("name") == "lens_1"),
             None))

    # 3) 在 UI 里把焦距 100 -> 150（等价于教学单位 10cm -> 15cm），提交后读回
    if parsed is not None:
        for o in parsed["objs"]:
            if o.get("name") == "lens_1":
                o["focalLength"] = 150
        page.evaluate(
            """(text) => {
               const el = document.querySelector('.ace_text-layer');
               const editor = window.ace ? null : null;
               // 走 DOM：优先找可编辑 textarea
               const ta = document.querySelector('textarea');
               if (ta) { ta.value = text; ta.dispatchEvent(new Event('input', {bubbles:true})); return 'textarea'; }
               return 'no-editable-target';
            }""",
            json.dumps(parsed),
        )
        page.wait_for_timeout(1500)
        reloaded = page.evaluate(
            """() => {
              const el = document.querySelector('.ace_text-layer');
              if (el) return el.innerText;
              const ta = document.querySelector('textarea');
              return ta ? ta.value : null;
            }"""
        )
        after = None
        try:
            after = json.loads(reloaded) if reloaded else None
        except Exception:
            after = None
        step("edit_in_ui",
             target_found=reloaded is not None,
             lens_focalLength_after=after and next(
                 (o.get("focalLength") for o in after.get("objs", []) if o.get("name") == "lens_1"),
                 None),
             names_after=after and [o.get("name") for o in after.get("objs", [])])

    # 4) UI 是否暴露对象改名入口（决定 name 绑定的真实风险）
    name_affordances = page.evaluate(
        """() => {
          const labels = [...document.querySelectorAll('label, .form-label, input') ]
            .map(e => ((e.innerText || '') + ' ' + (e.getAttribute('placeholder') || '') + ' ' + (e.getAttribute('aria-label') || '')).trim())
            .filter(t => /name|名称|名字/i.test(t));
          return labels.slice(0, 15);
        }"""
    )
    step("name_edit_affordances", found=name_affordances)

    report["final_page_errors"] = errors[:10]
    browser.close()

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2)[:3000])
sys.exit(0)
