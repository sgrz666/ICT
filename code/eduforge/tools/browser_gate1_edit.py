"""GATE-1 浏览器验证（人工路径）：在真实上游编辑器里完成
载入种子场景 -> 经 Code 页签改焦距 -> 用应用自己的"复制分享链接"导出 -> 解回对比。

走的是应用自身的输入与导出通道（Code 页签有 sanitizePastedJson，导出用 lzma 压缩
editor.lastActionJson），不去戳内部对象，所以结论对教师实际使用路径负责。
"""
import json
import pathlib
import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8099/simulator/"
HASH = pathlib.Path(r"D:/codeplus/ICT/output/eduforge/reports/share-hash.txt").read_text().strip()
NATIVE = json.loads(pathlib.Path(
    r"D:/codeplus/ICT/code/eduforge/catalog/templates/optics/convex-lens/native.json"
).read_text(encoding="utf-8"))
OUT = pathlib.Path(r"D:/codeplus/ICT/output/eduforge/reports/slice1-browser-edit.json")

report: dict = {}


def lens(scene):
    return next((o for o in scene.get("objs", []) if o.get("name") == "lens_1"), None)


def copy_share_link(page):
    """点"复制分享链接"菜单项，读回剪贴板里的完整 URL。"""
    page.evaluate(
        """() => {
      const want = ['复制分享链接', 'Copy Shareable Link'];
      // 菜单项的 innerText 往往把标题和说明拼在一起，所以按"自身文本"匹配再找可点击祖先
      const all = [...document.querySelectorAll('*')];
      for (const el of all) {
        const own = [...el.childNodes].filter(n => n.nodeType === 3)
          .map(n => n.textContent.trim()).join('').trim();
        if (want.includes(own)) {
          const target = el.closest('a, button, .dropdown-item, li') || el;
          target.click();
          return own;
        }
      }
      return null;
    }"""
    )
    page.wait_for_timeout(1200)
    return page.evaluate(
        """async () => { try { return await navigator.clipboard.readText(); } catch (e) { return 'CLIPBOARD_DENIED: ' + e; } }"""
    )


def decode_hash(page, url):
    """用上游同款 json-url('lzma') 把分享 URL 解回场景。"""
    if not url or "#" not in url:
        return None
    h = url.split("#", 1)[1]
    return page.evaluate(
        """async (h) => {
        const jsonurl = window.__jsonurl || null;
        // 页面内部才打包了 json-url，走它的 onpopstate：改 hash 让 app 自己解
        // 这里改为直接返回 hash，由本机 Node 解码
        return h;
    }""",
        h,
    )


with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(
        viewport={"width": 1400, "height": 900},
        permissions=["clipboard-read", "clipboard-write"],
    )
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(BASE + "#" + HASH, wait_until="networkidle")
    page.wait_for_timeout(2500)

    report["step1_load"] = {
        "title": page.title(),
        "welcome_hidden": not page.locator("#welcome").is_visible(),
        "sized_canvases": page.evaluate(
            "() => [...document.querySelectorAll('canvas')].filter(c => c.width > 0 && c.height > 0).length"
        ),
        "page_errors": errors[:5],
    }

    # 导出一次，确认未编辑时与我们的种子场景一致（控制组）
    url_before = copy_share_link(page)
    report["step2_export_before"] = {
        "url_len": len(url_before or ""),
        "hash_len": len(url_before.split("#", 1)[1]) if url_before and "#" in url_before else 0,
        "hash": (url_before.split("#", 1)[1] if url_before and "#" in url_before else url_before),
    }

    # 切到 Code 页签，用键盘方式把改了焦距的 JSON 粘进去
    # 侧边栏默认折叠成抽屉，页签在视口外点不到；先点它自带的展开按钮
    expand = page.locator('button.drawer-toggle-expand[aria-label="Show sidebar"]')
    report["sidebar_expand"] = {"found": expand.count() > 0}
    if expand.count() > 0:
        expand.first.click()
        page.wait_for_timeout(1000)
    report["sidebar_visible_class"] = page.evaluate(
        "() => !!document.querySelector('#sidebar.sidebar-visible')"
    )

    tabs = page.locator("#sidebar button[role=tab]")
    report["sidebar_tabs"] = {
        "count": tabs.count(),
        "labels": [tabs.nth(i).inner_text() for i in range(tabs.count())],
    }
    if tabs.count() >= 2:
        tabs.nth(1).click()
        page.wait_for_timeout(800)

    edited = json.loads(json.dumps(NATIVE))
    lens(edited)["focalLength"] = 150  # 10cm -> 15cm，模板约定 1cm = 10 场景单位

    edited_present = page.evaluate(
        """() => {
      const ed = document.querySelector('#jsonEditor');
      return ed ? {present: true, visible: ed.offsetWidth > 0} : {present: false};
    }"""
    )
    report["step3_code_tab"] = edited_present

    if edited_present["present"] and edited_present["visible"]:
        page.click("#jsonEditor")
        page.keyboard.press("Control+a")
        page.keyboard.insert_text(json.dumps(edited))
        page.wait_for_timeout(2500)

        # 读编辑器当前内容，确认改动已在 ACE 文档里
        ace_value = page.evaluate(
            """() => {
          const el = document.querySelector('#jsonEditor');
          if (!el || !el.env || !el.env.editSession) return null;
          return el.env.editSession.getValue();
        }"""
        )
        report["step4_ace_value"] = {
            "readable": ace_value is not None,
            "lens_focalLength": (
                lens(json.loads(ace_value)).get("focalLength") if ace_value else None
            ),
        }

        # 应用自己同步到场景后，再导出一次
        url_after = copy_share_link(page)
        report["step5_export_after"] = {
            "url_len": len(url_after or ""),
            "hash": (url_after.split("#", 1)[1] if url_after and "#" in url_after else None),
        }

    page.screenshot(path=str(OUT).replace(".json", "-final.png"))
    report["final_page_errors"] = errors[:8]
    browser.close()

OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2)[:2500])
sys.exit(0)
