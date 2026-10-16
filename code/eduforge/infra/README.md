# infra/ — 基础设施与容器编排

本目录存放 EduForge 本地联调与生产部署的 Dockerfile 与 Compose 编排文件。

## 1. 职责

提供完整环境拓扑的容器化定义，包括业务 API、Agent 规划服务、TypeScript Engine Host、受限代码沙箱以及本地轻量启动器。

## 2. 内容

- [`compose.local.yaml`](compose.local.yaml)：本地容器拓扑（PostgreSQL 16 :5432、Engine Host :4000、Agent :8001；db 健康后起 agent）；
- [`agent/Dockerfile`](agent/README.md)：Python 3.12 业务 API 与 Agent 运行时镜像（24 行；构建上下文为工程根）；
- [`engine-host/Dockerfile`](engine-host/README.md)：Node 24 TypeScript 仿真与网关镜像（19 行；直接跑预构建 `dist/main.js`）；
- [`sandbox/Dockerfile`](sandbox/README.md)：隔离代码定制沙箱（14 行；禁网 + 预装工具链；切片 7 预留）；
- [`launcher/Dockerfile`](launcher/README.md)：离线启动器（11 行；Go 1.22 交叉编译 Windows exe；切片 9 预留，**当前引用的 `tools/offline-server` 尚未落地**）。

每个子目录各有一份 README（逐文件说明与坑）。

## 3. 与上下层的关系

- **服务来源**：打包 [`../python/`](../python/)、[`../services/engine-host/`](../services/engine-host/) 与 [`../tools/`](../tools/)；
- **操作集成**：统一由根目录脚本 [`../../../scripts/eduforge.ps1`](../../../scripts/eduforge.ps1) 负责环境检测与状态管理；
- **两套端口拓扑并存**：本层容器路径（engine-host :4000 / agent :8001）与脚本无容器路径（API :8000 / Engine Host :8010 / 浏览器网关 :4174）——对照表见 [`../../../scripts/README.md`](../../../scripts/README.md)，不要混用。

## 4. 已知的坑与纪律

- 本地未装 Docker 时，统一脚本通过内嵌式/独立式 Postgres 进行无容器自愈，不强行依赖 Docker Desktop 守护进程；因此本层各镜像在**本机均未实测构建**（pending）——首次启用先跑一次构建。
- `launcher/Dockerfile` 目前**不可构建**（`tools/offline-server` 源码目录缺失，切片 9 预留）；`engine-host` 镜像不含上游 `dist-node` bundle——容器内仿真链路尚未闭环。
