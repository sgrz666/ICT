/**
 * verify_page.js —— 生成阶段的真浏览器冒烟验证脚本（Playwright）
 *
 * 用法：node verify_page.js <html路径>
 * 输出：最后一行输出 JSON，供 generator_agent.py 解析
 */

const {chromium} = require('playwright');
const {pathToFileURL} = require('url');

const FILE = process.argv[2];

(async () => {
  const out = {
    fatal: null,
    errors: [],
    ranges: {count: 0, responsive: 0, details: []},
    buttons: 0,
    buttonsClicked: [],
    canvas: [],
  };

  if (!FILE) {
    out.fatal = '未指定 HTML 文件路径';
    console.log(JSON.stringify(out));
    return;
  }

  let browser;
  try {
    const launchOpts = {headless: true};
    if (process.env.CHROME_PATH) {
      launchOpts.executablePath = process.env.CHROME_PATH;
    }
    browser = await chromium.launch(launchOpts);
    const page = await browser.newPage({viewport: {width: 1366, height: 820}});

    page.on('pageerror', (err) => {
      out.errors.push(
          '页面异常: ' + (err && err.message ? err.message : String(err))
      );
    });
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        out.errors.push('控制台错误: ' + msg.text());
      }
    });

    await page.goto(pathToFileURL(FILE).href, {
      waitUntil: 'domcontentloaded',
      timeout: 20000,
    });
    await page.waitForTimeout(250);

    const snapshot = async () => {
      return await page.evaluate(() => {
        const text = (document.body ? document.body.innerText : '').replace(
            /\s+/g,
            ' '
        );
        const data = window.__DATA__ ? JSON.stringify(window.__DATA__) : '';
        const cvs = Array.from(document.querySelectorAll('canvas'))
            .filter((c) => !(c.style && c.style.display === 'none'))
            .map((c) => {
              try {
                const ctx = c.getContext('2d');
                if (!ctx || !c.width || !c.height) return '';
                const d = ctx.getImageData(
                                 0,
                                 0,
                                 Math.min(c.width, 160),
                                 Math.min(c.height, 120)
                ).data;
                let s = 0;
                for (let i = 0; i < d.length; i += 16) s = (s * 31 + d[i]) | 0;
                return String(s);
              } catch (e) {
                return '';
              }
            })
            .join('|');
        return text + '##' + data + '##' + cvs;
      });
    };

    // 1. 测试每个滑块
    const rangeCount = await page.locator('input[type="range"]').count();
    out.ranges.count = rangeCount;
    for (let i = 0; i < rangeCount; i++) {
      const info = await page.evaluate((idx) => {
        const el = document.querySelectorAll('input[type="range"]')[idx];
        if (!el) return null;
        const label =
            (el.labels && el.labels[0] && el.labels[0].innerText) ||
            el.getAttribute('aria-label') ||
            el.id ||
            el.name ||
            '滑块#' + (idx + 1);
        return {
          label: label.trim().slice(0, 24),
          min: parseFloat(el.min || '0'),
          max: parseFloat(el.max || '100'),
          step: parseFloat(el.step || '1') || 1,
          val: parseFloat(el.value || '0'),
        };
      }, i);
      if (!info) continue;

      const before = await snapshot();
      const target =
          Math.abs(info.val - info.max) > 1e-6 ? info.max : info.min;
      await page.evaluate(
          ({idx, val}) => {
            const el = document.querySelectorAll('input[type="range"]')[idx];
            if (!el) return;
            el.value = String(val);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
          },
          {idx: i, val: target}
      );
      await page.waitForTimeout(80);
      const after = await snapshot();
      const changed = before !== after;
      if (changed) out.ranges.responsive++;
      out.ranges.details.push({滑块: info.label, 有响应: changed});
    }

    // 2. 测试按钮
    const btnList = await page.evaluate(() => {
      const btns = Array.from(
          document.querySelectorAll(
              '#sec-ctrl button, .sec-ctrl button, main button'
          )
      );
      return btns
          .map((b, idx) => ({
            idx,
            text: (b.innerText || b.textContent || '').trim().slice(0, 20),
            disabled: !!b.disabled,
            visible: b.offsetWidth > 0 && b.offsetHeight > 0,
          }))
          .filter(
              (b) =>
                  b.visible &&
                  !b.disabled &&
                  b.text &&
                  !/下载|全屏|返回|关闭/.test(b.text)
          );
    });
    out.buttons = btnList.length;
    for (const b of btnList.slice(0, 6)) {
      const before = await snapshot();
      await page.evaluate((idx) => {
        const btns = Array.from(
            document.querySelectorAll(
                '#sec-ctrl button, .sec-ctrl button, main button'
            )
        );
        if (btns[idx]) btns[idx].click();
      }, b.idx);
      await page.waitForTimeout(80);
      const after = await snapshot();
      out.buttonsClicked.push({按钮: b.text, 有响应: before !== after});
    }

    // 3. 画布像素采样
    out.canvas = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('canvas'))
          .filter((c) => !(c.style && c.style.display === 'none'))
          .map((c) => {
            let painted = 0;
            try {
              const ctx = c.getContext('2d');
              if (ctx && c.width > 0 && c.height > 0) {
                const w = Math.min(c.width, 300);
                const h = Math.min(c.height, 200);
                const data = ctx.getImageData(0, 0, w, h).data;
                let bgR = data[0],
                    bgG = data[1],
                    bgB = data[2],
                    bgA = data[3];
                for (let i = 0; i < data.length; i += 16) {
                  const dr = Math.abs(data[i] - bgR);
                  const dg = Math.abs(data[i + 1] - bgG);
                  const db = Math.abs(data[i + 2] - bgB);
                  const da = Math.abs(data[i + 3] - bgA);
                  if (data[i + 3] > 10 && dr + dg + db + da > 18) painted++;
                }
              }
            } catch (e) {
              painted = 200;
            }
            return {width: c.width, height: c.height, painted};
          });
    });
  } catch (e) {
    out.fatal = e && e.message ? e.message : String(e);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }

  console.log(JSON.stringify(out));
})();
