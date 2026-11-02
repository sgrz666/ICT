# 03 教学工具生成 Agent（六区域版）

输入：需求 JSON（01）+ 知识包 JSON（02）
输出：一个已套「师伴」平台外壳、可双击打开离线运行的实验页面

## 这一版改了什么

| | 旧版 | 现在 |
|---|---|---|
| 模型输出 | 完整 HTML（`<!DOCTYPE>`…`</html>`） | **只输出六块内容**（`<!--1-->`…`<!--6-->` + `<!--CSS-->` + `<!--JS-->`） |
| 外壳（页眉/右栏/页脚/弹窗） | 模型每次重写，会漂移 | 由 `shell.py` 用固定模板装配，所有页面完全一致 |
| 样式 | 模型内联一堆 CSS | 复用 `frame/frame.css` + `frame/exp.css`，模型基本不用写 CSS |
| 交付物 | 单个 html | 一个目录：html + frame.css + exp.css + logo.png + zip |

道理很简单：**模型负责「实验对不对」，外壳负责「页面像不像同一个产品」**。
把这两件事混在一个提示词里，模型会为了省 token 把页脚、导航悄悄砍掉。

## 一、目录

```
03_generator_agent/
├── prompts.py                  六区域提示词（契约 + 学科判据 + 自查清单）
├── generator_agent.py          主程序：清洗 → 硬校验 → 修复一次 → 兜底
├── templates/ohm_law_experiment.html   旧版单文件模板（保留备查，新链路不再使用）
├── verify_page.js              单页自检脚本
└── output/
    ├── 教学资源_xxx.html        最终交付物（依赖同目录的 frame.css / exp.css / logo.png）
    ├── 教学资源_xxx.zip         整个案例打包，发给别人双击就能看
    └── 教学资源_xxx.meta.json   生成元信息（给质量审查 Agent 用）

项目根目录配套：
frame/      平台外壳（frame.css 老师原样下发 / exp.css 六区域样式 / shell.html / logo.png）
shell.py    装配器：切段 → 校验 → 套壳 → 落盘 + zip
```

## 二、跑起来

```bash
python generator_agent.py                       # 自动找最新的需求 + 知识包
python generator_agent.py --show-prompt         # 只打印最终提示词，不调模型（改提示词时核对用）
python generator_agent.py --template-only       # 不调模型，用兜底片段验证链路
python generator_agent.py --feedback "读数不刷新"  # 带审查意见重做
python generator_agent.py --open                # 生成后直接打开
```

装配器可以单独用——手工写好的内容片段也能套壳：

```bash
python shell.py build cases/数学_平面截正方体.txt --title 平面截正方体 --out deliver
```

## 三、输出契约（模型必须遵守，shell.py 按此解析）

```
<!--1--> ① 实验信息     h2.exp-name / .exp-tags / .exp-goals-title「学习目标」/ ul.exp-goals
<!--2--> ② 演示         canvas#cv 或 svg#cv（只放画布，标题由外壳提供）
<!--3--> ③ 参数与操作   .exp-field > input[type=range][data-key] + .exp-btns > button.exp-btn
<!--4--> ④ 结果与反馈   .exp-reads（读数）+ #fml（实时代入式）+ #hint + #alert
<!--5--> ⑤ 实验记录     table.exp-table > tbody#rows（脚本追加行）
<!--6--> ⑥ 教学说明     原理 / 易错点 / 探究问题 / 结论 / 注意事项
<!--CSS--> 可选补充样式
<!--JS-->  全部脚本
```

三条硬要求（少一条就装配失败或审查扣分）：

1. 页面上必须出现「学习目标」「结论」「注意事项」三处文字
2. 必须暴露 `window.__DATA__`（数学/几何用 `window.__GEO__`），审查会拿它和显示值比对
3. 单一 `state` + 单一 `render()`，所有事件只改状态再调 `render()`

## 四、三道关

1. **清洗**：围栏、客套话、模型顺手带上的 `<html>`/`<body>` 都削掉
2. **硬校验**：六块是否齐、关键类名在不在、有没有外链、有没有暴露机读数据、长度是否超
3. **修复 → 兜底**：带着问题清单让模型改一次；仍不合格就换兜底片段，保证「永远有能演示的东西」

兜底片段是一个通用的 `y = kx` 演示页，走同一套外壳与同一套校验，不是假页面，
但页面上会明确标注「兜底演示（模型输出未通过校验）」。

## 五、和审查器的接口

`reviewer.py` / `checks_browser.js` 会读页面上那一行代入式，用通用算术规则复算
（`a + b = c`、`a × b = c`、`a ÷ b = c` 都认），所以新学科不用再为每种公式写一套正则。

## 六、新增一个学科要做什么

1. `prompts.py` 的 `JUDGE_BY_SUBJECT` 加一行（该学科的核验判据）
2. `topics.py` 加一条主题配置
3. `02_retrieval_agent/knowledge/` 放 5 个带「主题:」字段的 md

只有出现全新的画法时才动 `exp.css`；外壳 `frame.css` 一律不碰。
