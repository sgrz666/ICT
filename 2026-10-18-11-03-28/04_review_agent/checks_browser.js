/**
 * checks_browser.js —— 第四关「浏览器测试」的取证脚本
 *
 * 规范（《界面设计+审查判据》3.4 第4关）要求：加载、点击、参数变化、重置、离线运行。
 * 所以这里不只是"能打开"，还要真的：
 *   1. 记录六个区域是否渲染出内容
 *   2. 抓 window.__DATA__ / __GEO__（第三关 J1–J8 的独立复算原料）
 *   3. 拖滑块到极值，看读数/图像/代入式是否跟着变
 *   4. 点「重置」，比对是否回到与首屏一致的状态（规范 2.3 必做项）
 *   5. 点「单步/下一步」，看状态序列是否卡住
 *   6. 点「记录」，看表格是否真的追加行
 *   7. 统计运行时有没有 file:// 之外的请求（离线运行）
 *
 * 用法：node checks_browser.js <html路径>
 * 输出：一行 JSON（stdout），供 Python 侧解析
 */

const {chromium} = require('playwright');
const {pathToFileURL} = require('url');

const FILE = process.argv[2];

/**
 * 画布绘制取证：包装 2D 上下文，记录每次 fillText 与 fill/fillRect 的
 * 设备像素包围盒和先后顺序。页面无需任何配合。
 * 判定依据：后绘制的图元如果盖住先绘制的文字，就是"文字被图像遮住"。
 */
const CANVAS_HOOK = () => {
  const proto = CanvasRenderingContext2D.prototype;
  const st = {seq: 0, texts: [], fills: [], frames: []};
  // 质感取证：只记帧内比率，动画多帧不会把数字冲淡
  st.q = {
    fills: 0,
    grad: 0,
    alpha: 0,
    flat: 0,
    rect: 0,
    curve: 0,
    radial: 0,
    ellipse: 0,
    blur: 0,
  };
  window.__CANVAS_AUDIT__ = st;

  const alphaOf = (style, ga) => {
    let a = ga;
    if (typeof style === 'string') {
      const m = style.match(/rgba?\(([^)]+)\)/);
      if (m) {
        const p = m[1].split(',').map(parseFloat);
        if (p.length === 4) a *= p[3];
      } else if (style.startsWith('#') && style.length === 9) {
        a *= parseInt(style.slice(7, 9), 16) / 255;
      }
    }
    return a;
  };

  // 被隐藏的画布（例如被库兜底接管后留在 DOM 里的旧渲染层）学生看不见，
  // 它的文字和填充不参与取证，否则会把「页面上根本看不到」的字判成被遮挡。
  const shown = (c) => !(c && c.style && c.style.display === 'none');

  const dev = (ctx, x, y, w, h) => {
    const m = ctx.getTransform();
    return {
      x: m.a * x + m.c * y + m.e,
      y: m.b * x + m.d * y + m.f,
      w: Math.abs(w * (Math.abs(m.a) || 1)),
      h: Math.abs(h * (Math.abs(m.d) || 1)),
    };
  };

  const origBegin = proto.beginPath;
  proto.beginPath = function(...a) {
    this.__bb = null;
    return origBegin.apply(this, a);
  };
  const grow = (ctx, x, y) => {
    if (!isFinite(x) || !isFinite(y)) return;
    const b = ctx.__bb;
    if (!b) ctx.__bb = {x1: x, y1: y, x2: x, y2: y};
    else {
      b.x1 = Math.min(b.x1, x);
      b.y1 = Math.min(b.y1, y);
      b.x2 = Math.max(b.x2, x);
      b.y2 = Math.max(b.y2, y);
    }
  };

  for (const fn of ['moveTo', 'lineTo']) {
    const orig = proto[fn];
    proto[fn] = function(x, y, ...r) {
      grow(this, x, y);
      return orig.call(this, x, y, ...r);
    };
  }
  for (const fn of ['quadraticCurveTo', 'bezierCurveTo']) {
    const orig = proto[fn];
    proto[fn] = function(...a) {
      st.q.curve++;
      if (a.length >= 2) grow(this, a[a.length - 2], a[a.length - 1]);
      return orig.apply(this, a);
    };
  }
  const origArc = proto.arc;
  proto.arc = function(x, y, r, ...rest) {
    st.q.curve++;
    grow(this, x - r, y - r);
    grow(this, x + r, y + r);
    return origArc.call(this, x, y, r, ...rest);
  };
  const origEllipse = proto.ellipse;
  if (origEllipse) {
    proto.ellipse = function(x, y, rx, ry, ...rest) {
      st.q.curve++;
      st.q.ellipse++;
      grow(this, x - rx, y - ry);
      grow(this, x + rx, y + ry);
      return origEllipse.call(this, x, y, rx, ry, ...rest);
    };
  }
  const origRect = proto.rect;
  proto.rect = function(x, y, w, h) {
    st.q.rect++;
    grow(this, x, y);
    grow(this, x + w, y + h);
    return origRect.call(this, x, y, w, h);
  };
  const origRoundRect = proto.roundRect;
  if (origRoundRect) {
    proto.roundRect = function(x, y, w, h, ...rest) {
      st.q.curve++;
      grow(this, x, y);
      grow(this, x + w, y + h);
      return origRoundRect.call(this, x, y, w, h, ...rest);
    };
  }
  const origRadial = proto.createRadialGradient;
  proto.createRadialGradient = function(...a) {
    const g = origRadial.apply(this, a);
    if (g) g.__isRadial = true;
    return g;
  };

  const origClear = proto.clearRect;
  proto.clearRect = function(x, y, w, h) {
    const c = this.canvas;
    if (c && w >= c.width * 0.8 && h >= c.height * 0.8) {
      st.texts = st.texts.filter((t) => t.c !== c);
      st.fills = st.fills.filter((f) => f.c !== c);
    }
    return origClear.call(this, x, y, w, h);
  };

  const recordFill = (ctx, x, y, w, h, by) => {
    if (!shown(ctx.canvas)) return;
    const d = dev(ctx, x, y, w, h);
    const c = ctx.canvas;
    const area = d.w * d.h;
    const cArea = (c ? c.width * c.height : 0) || 1;
    const isGrad =
        ctx.fillStyle && typeof ctx.fillStyle === 'object' ? 1 : 0;
    const a = alphaOf(ctx.fillStyle, ctx.globalAlpha);
    st.q.fills++;
    if (isGrad) {
      st.q.grad++;
      if (ctx.fillStyle.__isRadial) st.q.radial++;
    }
    if (a < 0.92) st.q.alpha++;
    if (ctx.shadowBlur > 1) st.q.blur++;
    if (
        !isGrad &&
        a >= 0.95 &&
        area > cArea * 0.04 &&
        area < cArea * 0.82 &&
        by === 'fillRect'
    ) {
      st.q.flat++;
    }
    if (area < cArea * 0.85 && a >= 0.35 && d.w > 2 && d.h > 2) {
      st.fills.push({
        seq: ++st.seq,
        c,
        x: d.x,
        y: d.y,
        w: d.w,
        h: d.h,
        by,
      });
    }
  };

  const origFillRect = proto.fillRect;
  proto.fillRect = function(x, y, w, h) {
    st.q.rect++;
    recordFill(this, x, y, w, h, 'fillRect');
    return origFillRect.call(this, x, y, w, h);
  };

  const origFill = proto.fill;
  proto.fill = function(...a) {
    if (this.__bb) {
      const b = this.__bb;
      recordFill(this, b.x1, b.y1, b.x2 - b.x1, b.y2 - b.y1, 'fill');
    } else if (shown(this.canvas)) {
      st.q.fills++;
      if (this.fillStyle && typeof this.fillStyle === 'object') st.q.grad++;
    }
    return origFill.apply(this, a);
  };

  const origFillText = proto.fillText;
  proto.fillText = function(text, x, y, ...rest) {
    const s = String(text == null ? '' : text).trim();
    if (s && shown(this.canvas)) {
      const m = this.measureText(s);
      const fsMatch = String(this.font || '').match(/(\d+(?:\.\d+)?)px/);
      const fs = fsMatch ? parseFloat(fsMatch[1]) : 14;
      const w = Math.max(m ? m.width : s.length * fs * 0.6, 4);
      const h = fs;
      let tx = x;
      if (this.textAlign === 'center') tx = x - w / 2;
      else if (this.textAlign === 'right' || this.textAlign === 'end')
        tx = x - w;
      let ty = y - h * 0.8;
      if (this.textBaseline === 'middle') ty = y - h / 2;
      else if (this.textBaseline === 'top' || this.textBaseline === 'hanging')
        ty = y;
      const d = dev(this, tx, ty, w, h);
      st.texts.push({
        seq: ++st.seq,
        c: this.canvas,
        text: s,
        x: Math.round(d.x),
        y: Math.round(d.y),
        w: Math.round(d.w),
        h: Math.round(d.h),
        cw: this.canvas ? this.canvas.width : 0,
        ch: this.canvas ? this.canvas.height : 0,
      });
    }
    return origFillText.call(this, text, x, y, ...rest);
  };
};

/**
 * 从页面可见文字中提取「代入式」并独立复算
 * 例如：「1000 kg/m³ × 10 N/kg × 0.0002 m³ = 2.00 N」
 */
function parseAndCheckFormulas(rawText, stageName) {
  const checks = [];
  if (!rawText) return checks;
  const lines = String(rawText)
                    .split(/[\n；;｜|]+/)
                    .map((s) => s.trim())
                    .filter(Boolean);
  const seen = new Set();

  for (const line of lines) {
    const parts = line.split('=');
    if (parts.length < 2) continue;
    for (let i = 0; i < parts.length - 1; i++) {
      const lhs = parts[i].trim();
      const rhs = parts[i + 1].trim();
      if (!/[0-9]/.test(lhs) || !/[×*·÷/+\-−²³]/.test(lhs)) continue;
      const rhsMatch = rhs.match(/^\s*(-?\d+(?:\.\d+)?)/);
      if (!rhsMatch) continue;
      const shownVal = parseFloat(rhsMatch[1]);
      if (!isFinite(shownVal)) continue;

      // 清洗单位但保留算术运算符与括号
      let expr = lhs
                     // 复合单位如 kg/m³、g/cm³、N/kg、m/s²、J/(kg·℃) 先整体抹掉，防止其中的 / 被当成除号
                     .replace(
                         /[A-Za-zμΩ°℃%]+\s*\/\s*[A-Za-zμΩ°℃%³²0-9()·]+/g,
                         ' '
                     )
                     .replace(/²/g, '**2')
                     .replace(/³/g, '**3')
                     .replace(/[×·]/g, '*')
                     .replace(/÷/g, '/')
                     .replace(/−/g, '-')
                     // 去掉剩余单位字符（字母、中文、Ω、°、% 等）
                     .replace(/[^\d.+\-*/()\s]/g, ' ')
                     .replace(/\*\s*\*\s*(\d)/g, '**$1')
                     .trim();

      if (!expr || !/[+\-*/]/.test(expr)) continue;
      // 至少包含两个数字或幂运算，排除单个数字
      const nums = expr.match(/\d+(?:\.\d+)?/g) || [];
      if (nums.length < 2) continue;
      if (!/^[\d.+\-*/()\s]+$/.test(expr)) continue;

      let expected = null;
      try {
        // 仅对纯数字与四则运算符求值
        expected = Function('"use strict"; return (' + expr + ');')();
      } catch (e) {
        expected = null;
      }
      if (typeof expected !== 'number' || !isFinite(expected)) continue;

      const snippet = (lhs + ' = ' + rhsMatch[0].trim()).replace(/\s+/g, ' ');
      const key = stageName + ':' + snippet;
      if (seen.has(key)) continue;
      seen.add(key);

      const tol = Math.max(0.05, Math.abs(expected) * 0.03);
      const ok = Math.abs(shownVal - expected) <= tol;
      checks.push({
        text: snippet.slice(0, 80),
        显示: Number(shownVal.toFixed(4)),
        应为: Number(expected.toFixed(4)),
        ok,
        阶段: stageName,
      });
    }
  }
  return checks;
}

(async () => {
  const out = {
    loadMs: 0,
    fatal: null,
    errors: [],
    network: [],
    sections: [],
    machine: {},
    formula: {checks: []},
    ranges: {count: 0, responsive: 0, bounds: []},
    buttons: 0,
    buttonsClicked: [],
    steps: {found: false, count: 0, unique: 0, stuck: 0},
    records: {clicked: 0, before: 0, after: 0, added: 0},
    tables: [],
    reset: {found: false, restored: false, dataDiff: false, textDiff: 0, resetText: ''},
    csv: {found: false},
    canvas: [],
    textOverlap: {
      canvas: {textCount: 0, covered: [], outOfBounds: [], worst: 0},
      dom: {checked: 0, issues: []},
    },
    quality: null,
    typography: null,
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
    const context = await browser.newContext({
      viewport: {width: 1366, height: 820},
      deviceScaleFactor: 1,
    });
    await context.addInitScript(CANVAS_HOOK);
    const page = await context.newPage();

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
    page.on('request', (req) => {
      const url = req.url();
      if (
          !url.startsWith('file://') &&
          !url.startsWith('data:') &&
          !url.startsWith('blob:')
      ) {
        out.network.push(url);
      }
    });

    const t0 = Date.now();
    await page.goto(pathToFileURL(FILE).href, {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await page.waitForTimeout(300);
    out.loadMs = Date.now() - t0;

    // 1. 六区域与首屏快照
    const SECS = [
      {id: 'sec-info', cls: 'exp-info', alt: 'sec-info', name: '①实验信息'},
      {id: 'sec-stage', cls: 'exp-stage', alt: 'sec-stage', name: '②实验演示'},
      {id: 'sec-control', cls: 'exp-control', alt: 'sec-ctrl', name: '③参数与操作'},
      {id: 'sec-result', cls: 'exp-result', alt: 'sec-result', name: '④结果与反馈'},
      {id: 'sec-record', cls: 'exp-record', alt: 'sec-record', name: '⑤实验记录'},
      {id: 'sec-teach', cls: 'exp-teach', alt: 'sec-note', name: '⑥教学说明'},
    ];

    out.sections = await page.evaluate((secs) => {
      return secs.map((s) => {
        const el =
            document.getElementById(s.id) ||
            document.getElementById(s.alt) ||
            document.querySelector('.' + s.cls) ||
            document.querySelector('.' + s.alt);
        if (!el) return {...s, 存在: false, 空: true, text: ''};
        const txt = (el.textContent || el.innerText || '')
                        .replace(/\s+/g, ' ')
                        .trim();
        const hasCanvas =
            el.querySelectorAll('canvas, svg, table, input, button').length > 0;
        return {
          ...s,
          存在: true,
          空: txt.length < 4 && !hasCanvas,
          text: txt.slice(0, 600),
        };
      });
    }, SECS);

    const getMachine = async () => {
      return await page.evaluate(() => {
        const clone = (v) => {
          try {
            return v ? JSON.parse(JSON.stringify(v)) : null;
          } catch (e) {
            return null;
          }
        };
        return {
          DATA: clone(window.__DATA__),
          GEO: clone(window.__GEO__),
          CONFIG: clone(window.__CONFIG__ || window.CONFIG),
          EXP: clone(window.__EXP__ || window.EXP),
        };
      });
    };

    out.machine = await getMachine();

    const getVisibleText = async () => {
      return await page.evaluate(() => {
        const res =
            document.getElementById('sec-result') ||
            document.querySelector('.sec-result');
        const main = document.querySelector('main') || document.body;
        return {
          resultText: res ? res.innerText || '' : '',
          bodyText: main ? main.innerText || '' : '',
        };
      });
    };

    const initTexts = await getVisibleText();
    const initFormulaChecks = parseAndCheckFormulas(
        initTexts.resultText + '\n' + initTexts.bodyText,
        '初态'
    );
    out.formula.checks.push(...initFormulaChecks);

    // 2. 画布覆盖、出界、质感与像素统计（在交互改变画布前先取首屏质感与遮挡）
    const auditData = await page.evaluate(() => {
      const st = window.__CANVAS_AUDIT__ || {
        texts: [],
        fills: [],
        q: {
          fills: 0,
          grad: 0,
          alpha: 0,
          flat: 0,
          rect: 0,
          curve: 0,
          radial: 0,
          ellipse: 0,
          blur: 0,
        },
      };
      const covered = [];
      const outOfBounds = [];
      let worst = 0;

      for (const t of st.texts) {
        if (t.cw > 0 && t.ch > 0) {
          if (
              t.x < -2 ||
              t.y < -2 ||
              t.x + t.w > t.cw + 2 ||
              t.y + t.h > t.ch + 2
          ) {
            outOfBounds.push({
              text: t.text,
              box: [t.x, t.y, t.w, t.h],
              canvas: [t.cw, t.ch],
            });
          }
        }
        for (const f of st.fills) {
          if (f.c !== t.c || f.seq <= t.seq) continue;
          const ix = Math.max(0, Math.min(t.x + t.w, f.x + f.w) - Math.max(t.x, f.x));
          const iy = Math.max(0, Math.min(t.y + t.h, f.y + f.h) - Math.max(t.y, f.y));
          const inter = ix * iy;
          const area = Math.max(1, t.w * t.h);
          const ratio = inter / area;
          if (ratio > 0.25) {
            worst = Math.max(worst, ratio);
            covered.push({text: t.text, by: f.by, ratio});
            break;
          }
        }
      }

      // DOM 文字遮挡检查
      const domIssues = [];
      let domChecked = 0;
      const walker = document.createTreeWalker(
          document.body,
          NodeFilter.SHOW_TEXT
      );
      let node;
      while ((node = walker.nextNode())) {
        const txt = (node.nodeValue || '').trim();
        if (!txt) continue;
        const el = node.parentElement;
        if (!el) continue;
        const tag = el.tagName.toLowerCase();
        if (
            tag === 'script' ||
            tag === 'style' ||
            tag === 'title' ||
            tag === 'option'
        )
          continue;
        const style = window.getComputedStyle(el);
        if (
            style.display === 'none' ||
            style.visibility === 'hidden' ||
            parseFloat(style.opacity) === 0
        )
          continue;
        const range = document.createRange();
        range.selectNodeContents(node);
        const rect = range.getBoundingClientRect();
        if (
            rect.width < 4 ||
            rect.height < 4 ||
            rect.bottom <= 0 ||
            rect.top >= window.innerHeight ||
            rect.right <= 0 ||
            rect.left >= window.innerWidth
        )
          continue;
        domChecked++;
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const topEl = document.elementFromPoint(cx, cy);
        if (topEl && !el.contains(topEl) && !topEl.contains(el)) {
          const topTag = topEl.tagName.toLowerCase();
          if (topTag === 'canvas' || topTag === 'svg' || topTag === 'img') {
            domIssues.push({
              text: txt.slice(0, 24),
              coveredBy: topTag,
              points: `${Math.round(cx)},${Math.round(cy)}`,
              viewport: '1366x820',
            });
          }
        }
      }

      const q = st.q;
      const fills = Math.max(1, q.fills);
      const paths = Math.max(1, q.rect + q.curve);
      const quality =
          q.fills > 0
              ? {
                  填充数: q.fills,
                  渐变占比: q.grad / fills,
                  叠层占比: q.alpha / fills,
                  立体件占比: (q.radial + q.ellipse + q.blur) / fills,
                  曲线占比: q.curve / paths,
                  扁平占比: q.flat / fills,
                  扁平色块: q.flat,
                }
              : null;

      // 版式统一取证
      const titleEl =
          document.querySelector('.pf-page') ||
          document.querySelector('.pf-exp-bar-title') ||
          document.querySelector('.pf-title');
      const title = titleEl
          ? (titleEl.innerText || '').replace(/^师伴-/, '').trim()
          : '';
      const nameEl = document.querySelector('#sec-info .exp-name, .exp-info .exp-name');
      const hasName = !!(
          nameEl &&
          window.getComputedStyle(nameEl).display !== 'none' &&
          (nameEl.innerText || '').trim().length > 0
      );
      const rootStyle = window.getComputedStyle(document.documentElement);
      const fsMinRaw = parseFloat(rootStyle.getPropertyValue('--pf-fs-min'));
      const fsMin = isFinite(fsMinRaw) && fsMinRaw > 0 ? fsMinRaw : 13;

      let minFs = 999;
      let small = 0;
      let colored = 0;
      const mainEl = document.querySelector('.pf-main') || document.body;
      const allEls = mainEl ? Array.from(mainEl.querySelectorAll('*')) : [];
      for (const e of allEls) {
        const tag = e.tagName.toLowerCase();
        if (['script', 'style', 'svg', 'path', 'canvas'].includes(tag)) continue;
        if (e.closest('canvas, svg')) continue;
        const directText = Array.from(e.childNodes)
                               .filter((n) => n.nodeType === 3)
                               .map((n) => n.nodeValue.trim())
                               .join('');
        if (!directText) continue;
        const cs = window.getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const r = e.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue;
        const fs = parseFloat(cs.fontSize);
        if (isFinite(fs) && fs > 0) {
          if (fs < minFs) minFs = fs;
          if (fs + 0.5 < fsMin) small++;
        }
        // 正文颜色检查（跳过按钮、徽章、读数等装饰件）
        if (
            !e.closest(
                'button, .exp-btn, .exp-tag, .exp-badge, .pf-exp-bar, .pf-header, a, .exp-alert, .exp-formula em, .exp-read .v'
            )
        ) {
          const m = cs.color.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
          if (m) {
            const [cr, cg, cb] = [
              parseInt(m[1], 10),
              parseInt(m[2], 10),
              parseInt(m[3], 10),
            ];
            if (cr > 60 || cg > 60 || cb > 60) colored++;
          }
        }
      }

      const typography = title
          ? {
              title,
              titleLen: title.length,
              hasName,
              fsMin,
              minFs: minFs === 999 ? fsMin : Math.round(minFs),
              small,
              colored,
            }
          : null;

      const canvasList = Array.from(document.querySelectorAll('canvas'))
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

      return {
        textOverlap: {
          canvas: {
            textCount: st.texts.length,
            covered,
            outOfBounds,
            worst,
          },
          dom: {
            checked: domChecked,
            issues: domIssues,
          },
        },
        quality,
        typography,
        canvas: canvasList,
      };
    });

    out.textOverlap = auditData.textOverlap;
    out.quality = auditData.quality;
    out.typography = auditData.typography;
    out.canvas = auditData.canvas;

    // 3. 快照与表格辅助函数
    const stateSig = async () => {
      return await page.evaluate(() => {
        const main = document.querySelector('main') || document.body;
        const txt = (main ? main.innerText : '').replace(/\s+/g, ' ').trim();
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
        return {txt, data, sig: txt + '##' + data + '##' + cvs};
      });
    };

    const initSig = await stateSig();

    // 4. 滑块范围与极值测试
    const rangeList = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('input[type="range"]')).map(
          (el, idx) => {
            const label =
                (el.labels && el.labels[0] && el.labels[0].innerText) ||
                el.getAttribute('aria-label') ||
                el.id ||
                el.name ||
                '滑块#' + (idx + 1);
            return {
              idx,
              名称: label.trim().slice(0, 24),
              min: parseFloat(el.min),
              max: parseFloat(el.max),
              value: parseFloat(el.value),
            };
          }
      );
    });
    out.ranges.count = rangeList.length;
    out.ranges.bounds = rangeList;

    for (const r of rangeList) {
      const before = await stateSig();
      const target =
          isFinite(r.max) && Math.abs(r.value - r.max) > 1e-6
              ? r.max
              : isFinite(r.min)
                  ? r.min
                  : r.value + 1;
      await page.evaluate(
          ({idx, val}) => {
            const el = document.querySelectorAll('input[type="range"]')[idx];
            if (!el) return;
            el.value = String(val);
            el.dispatchEvent(new Event('input', {bubbles: true}));
            el.dispatchEvent(new Event('change', {bubbles: true}));
          },
          {idx: r.idx, val: target}
      );
      await page.waitForTimeout(60);
      const after = await stateSig();
      if (after.sig !== before.sig) out.ranges.responsive++;

      const extTexts = await getVisibleText();
      const extChecks = parseAndCheckFormulas(
          extTexts.resultText + '\n' + extTexts.bodyText,
          '极值'
      );
      for (const c of extChecks) {
        if (!out.formula.checks.some((x) => x.阶段 === '极值' && x.text === c.text)) {
          out.formula.checks.push(c);
        }
      }
    }

    // 5. 按钮扫描与交互（单步、记录、CSV、普通按钮）
    const btns = await page.evaluate(() => {
      const all = Array.from(
          document.querySelectorAll(
              '#sec-ctrl button, .sec-ctrl button, main button, #sec-record button, .sec-record button'
          )
      );
      return all
          .map((b, idx) => ({
            idx,
            text: (b.innerText || b.textContent || '').trim().slice(0, 24),
            id: b.id || '',
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
    out.buttons = btns.length;

    const hasCsv = await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll('button, a'));
      return els.some((e) => /csv|导出/i.test(e.innerText || e.textContent || ''));
    });
    out.csv = {found: hasCsv};

    // 单步按钮测试
    const stepBtn = btns.find(
        (b) => /单步|下一步|步进|step/i.test(b.text) || /step/i.test(b.id)
    );
    if (stepBtn) {
      out.steps.found = true;
      const seenStates = new Set();
      let prevSig = (await stateSig()).sig;
      seenStates.add(prevSig);
      let stuck = 0;
      const clicks = 6;
      for (let k = 0; k < clicks; k++) {
        await page.evaluate((idx) => {
          const all = Array.from(
              document.querySelectorAll(
                  '#sec-ctrl button, .sec-ctrl button, main button, #sec-record button, .sec-record button'
              )
          );
          if (all[idx] && !all[idx].disabled) all[idx].click();
        }, stepBtn.idx);
        await page.waitForTimeout(50);
        const curSig = (await stateSig()).sig;
        out.steps.count++;
        if (curSig === prevSig) stuck++;
        seenStates.add(curSig);
        prevSig = curSig;
      }
      out.steps.unique = seenStates.size;
      out.steps.stuck = stuck >= clicks ? stuck : 0;
    }

    // 记录按钮测试
    const recBtn = btns.find(
        (b) => /记录|记入|添加数据|保存数据|record/i.test(b.text) || /record|add-row/i.test(b.id)
    );
    const countRows = async () => {
      return await page.evaluate(() => {
        return document.querySelectorAll('#sec-record tbody tr, .sec-record tbody tr, table tbody tr').length;
      });
    };
    if (recBtn) {
      const beforeRows = await countRows();
      out.records.before = beforeRows;
      await page.evaluate((idx) => {
        const all = Array.from(
            document.querySelectorAll(
                '#sec-ctrl button, .sec-ctrl button, main button, #sec-record button, .sec-record button'
            )
        );
        if (all[idx] && !all[idx].disabled) all[idx].click();
      }, recBtn.idx);
      await page.waitForTimeout(60);
      const afterRows = await countRows();
      out.records.clicked = 1;
      out.records.after = afterRows;
      out.records.added = Math.max(0, afterRows - beforeRows);
    }

    // 普通按钮点击响应测试
    for (const b of btns.slice(0, 6)) {
      if (/重置|复位|重新开始|reset|清空|导出|csv/i.test(b.text)) continue;
      const before = await stateSig();
      await page.evaluate((idx) => {
        const all = Array.from(
            document.querySelectorAll(
                '#sec-ctrl button, .sec-ctrl button, main button, #sec-record button, .sec-record button'
            )
        );
        if (all[idx] && !all[idx].disabled) all[idx].click();
      }, b.idx);
      await page.waitForTimeout(60);
      const after = await stateSig();
      out.buttonsClicked.push({按钮: b.text, 有响应: after.sig !== before.sig});
    }

    // 提取页面表格数据供 J7 复算
    out.tables = await page.evaluate(() => {
      return Array.from(document.querySelectorAll('table')).map((tb) => {
        return Array.from(tb.querySelectorAll('tr')).map((tr) =>
          Array.from(tr.querySelectorAll('th, td')).map((cell) =>
            (cell.innerText || cell.textContent || '').trim()
          )
        );
      });
    });

    // 6. 重置按钮测试（最后执行，检验能否恢复首屏初态）
    const resetBtn = btns.find(
        (b) => /重置|复位|重新开始|reset/i.test(b.text) || /reset/i.test(b.id)
    );
    if (resetBtn) {
      out.reset.found = true;
      await page.evaluate((idx) => {
        const all = Array.from(
            document.querySelectorAll(
                '#sec-ctrl button, .sec-ctrl button, main button, #sec-record button, .sec-record button'
            )
        );
        if (all[idx] && !all[idx].disabled) all[idx].click();
      }, resetBtn.idx);
      await page.waitForTimeout(80);
      const afterReset = await stateSig();
      const dataSame = afterReset.data === initSig.data;
      const textDiff = Math.abs(afterReset.txt.length - initSig.txt.length);
      out.reset.dataDiff = !dataSame;
      out.reset.textDiff = textDiff;
      out.reset.restored = dataSame && textDiff <= 12;
      out.reset.resetText = afterReset.txt.slice(0, 200);
      out.buttonsClicked.push({按钮: resetBtn.text, 有响应: true});
    }
  } catch (e) {
    out.fatal = e && e.message ? e.message : String(e);
  } finally {
    if (browser) await browser.close().catch(() => {});
  }

  console.log(JSON.stringify(out));
})();
