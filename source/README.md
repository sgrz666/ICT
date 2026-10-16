# source — 上游源码

EduForge 的思路是「复用成熟实验环境」，所以把上游开源引擎的源码请进工作区，**原样保留、定点锁定**，适配代码全部写在 [`../code/eduforge`](../code/eduforge/README.md) 一侧，不改上游一行。

## 内容

- [`upstream/`](upstream/README.md) — 上游源码区：`upstream.lock.json`（唯一的自有文件，记录每个上游的来源、构建与实测事实）+ `ray-optics/`（已接通的第一个引擎）。

## 纪律

- 上游目录是「只读参考」：需要修改行为时，在 engine-host 的 adapters 层包一层，不在上游仓库里打补丁。
- 版本与构建事实以 `upstream.lock.json` 为唯一权威；它只记实测（跑过的命令与输出），未跑的一律标 `pending`。
- 新增上游引擎时，先在 lock 文件登记（含 decision/reason），再决定是否克隆。
