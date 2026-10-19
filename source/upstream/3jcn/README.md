# 3jcn — 3JCN Physics Simulations 的目录镜像（不是引擎）

职责：把 3JCN（`https://www.new3jcn.com/`）这个静态站点的**演示目录**抓到本地，让资源库能离线检索「有哪些 3D 演示」，同时把它**不能**做的事写清楚：这里没有可运行产物，也没有任何已验证的改参接口。

## 内容

- `fetch_3jcn_index.py` — 抓取与抽取脚本。抓 8 个页面（`index.html`、`simulation.html` 与 motion/optics/thermo/electricity/modern/labs 六个分类页）存 `pages/`，再从 `<a>` 里抽 title+href，去重后写 `3jcn-inventory.json`。已存在即跳过（可重复跑），每页之间 sleep 0.4 s。跑法：`python source/upstream/3jcn/fetch_3jcn_index.py`。
- `3jcn-inventory.json` — 落盘清单（2026-10-19 实测：**8/8 页全部抓到、90 条链接**），含 `note` 字段说明「目录 ≠ 可控」。
- `pages/` — 抓下来的第三方 HTML（实测 8 个文件、205 KB，最大 `simulation.html` 48,115 字节）。被 `.gitignore` 挡住不入库，重跑脚本即得。

## 与上下层的关系

- 上层说明在 [`../README.md`](../README.md)：3JCN 是简报「适合补充进来的 2D/3D 仿真平台」表里唯一**没有 git 仓库**的一项，因此 lock 里这条锁的是抓取时间与页面字节数，不是 commit。
- 目录层：被 [`../../library/experiments.json`](../../library/experiments.json) 以 `engines[]` 里 `id: 3jcn-catalog` 登记，状态是 `reference_only`（比 `resource_installed` 更轻），不背任何实验的验收。
- 对比着看：`circuitjs1/`（构建 + 官方 JS 接口已实测）、`osp/`（源码落盘但控制面 pending）与这里构成三种不同的「装」——能跑 ≠ 能改参 ≠ 只是清单。

## 已知的坑与纪律

1. **站点无开源许可声明**（实测页面只有版权行与 `patent.html` 链接）⇒ 这里的 HTML 与任何演示产物都**不得**打进离线交付包，也不进 code/eduforge 的依赖。
2. **别把 90 条链接当 90 个可用实验**。本轮只验证了「目录抓得下来」；单个演示是否可被 Agent 改参一个都没验（pending）。简报里「程序化接口尚未核实」这句至今仍然成立。
3. 无 commit 可锁 ⇒ 可复现性靠「抓取时间 + 页面字节数」，脚本重跑若发现某页大小变了，要在 lock 的 `facts_measured` 里更新数字，不要静默覆盖。
4. `pages/` 是第三方内容，**本目录只在这一层写项目侧说明**，不逐文件登记（与 `phet/`、`ray-optics/` 的口径一致，见 [`../../README.md`](../../README.md) 与 [`../README.md`](../README.md)）。
