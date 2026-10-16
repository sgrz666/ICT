# infra/ — 基础设施与容器编排

本目录存放 EduForge 本地联调与生产部署的 Dockerfile 与 Compose 编排文件。

## 1. 职责

提供完整环境拓扑的容器化定义，包括业务 API、Agent 规划服务、TypeScript Engine Host、受限代码沙箱以及本地轻量启动器。

## 2. 内容

- [`compose.local.yaml`](compose.local.yaml)：本地开发运行拓扑（PostgreSQL 16、Engine Host 4000 端口、Agent 8001 端口）；
- [`agent/Dockerfile`](agent/Dockerfile)：Python 3.12 业务 API 与 Agent 运行时镜像定义；
- [`engine-host/Dockerfile`](engine-host/Dockerfile)：Node 24 TypeScript 仿真与浏览器网关服务镜像定义；
- [`sandbox/Dockerfile`](sandbox/Dockerfile)：隔离代码定制沙箱（禁止联网，预装构建工具链）；
- [`launcher/Dockerfile`](launcher/Dockerfile)：离线启动器（Go 1.22 静态编译，跨平台打包）。

## 3. 与上下层的关系

- **服务来源**：打包 [`../python/`](../python/)、[`../services/engine-host/`](../services/engine-host/) 与 [`../tools/`](../tools/)；
- **操作集成**：统一由根目录脚本 [`../../../scripts/eduforge.ps1`](../../../scripts/eduforge.ps1) 负责环境检测与状态管理。

## 4. 已知的坑与纪律

- 本地未装 Docker 时，统一脚本通过内嵌式/独立式 Postgres 进行无容器自愈，不强行依赖 Docker Desktop 守护进程。
