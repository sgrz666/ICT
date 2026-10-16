# sandbox — 代码定制沙箱镜像（切片 7 预留）

**职责**：为「代码定制」路线准备受限执行环境的容器镜像：Node 24 alpine + git/python3/make/g++，预建标准工作区目录，镜像内默认以非特权用户运行。

## 内容

| 文件 | 行数 | 关键步骤 |
|---|---|---|
| `Dockerfile` | 14 | `FROM node:24-alpine` → `apk add git python3 make g++` → 预建 `/workspace/{src,dist,tests}` → `USER node` → `CMD ["sh"]` |

## 与上下层的关系

- 预期消费方：Python 侧 [`../../python/src/eduforge/coding/`](../../python/src/eduforge/coding/README.md) 的 `sandbox_factory.py`（**当前未接入运行时**，`code` route 在 planning 阶段即被拒）。
- 编排入口：[`../compose.local.yaml`](../compose.local.yaml) 尚未包含本镜像的服务定义。

## 已知的坑与纪律

- **镜像本身不构成沙箱**：真正的隔离（禁网 `network_disabled=True`、资源限额）由 OpenSandbox 运行时参数控制——镜像只是"里面长什么样"。
- 本机无 Docker Desktop，本镜像**未实测构建**（pending）——切片 7 启用前先补这一步。
- `/workspace/{src,dist,tests}` 目录结构与 Python 侧 `coding/workspace.py` 的白名单约定耦合——改目录结构两处同改。
