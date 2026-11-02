# tools/ — 实验质检、无头浏览器探针与批量构建工具

**职责**：存放对生成页面进行自动化审查、文字重叠检测、视觉截图探针、交互稳定性测试及画廊构建的辅助工具脚本。

## 内容

| 脚本 / 工具 | 说明 |
|---|---|
| `build_gallery.py` / `lib_gallery.html` | 实验画廊索引页面构建与预览 |
| `check_page.js` / `check_text_overlap.js` | 页面可用性检查与画布文本重叠审计脚本 |
| `quality_probe.js` / `probe*.js` | 基于 Puppeteer/Playwright 的多维度质量探针 |
| `shot_*.js` / `montage.js` | 自动化无头浏览器多状态截图与拼接工具 |
| `test_*.js` | 浮力、透镜、立方体等学科交互逻辑单元自动化测试 |
| `relib*.py` / `reshell.py` | 页面外框批量重构与库依赖注入工具 |

## 与上下层的关系

- **父层索引**：[`../README.md`](../README.md)。
- **质检支撑**：为 `../04_review_agent/` 的无头浏览器审查与实验验证提供底层测试工具集。

## 已知的坑与纪律

1. **依赖环境**：脚本依赖 Node.js 与 Puppeteer/Playwright，执行前需保证无头浏览器环境就绪。
