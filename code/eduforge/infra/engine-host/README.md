# engine-host — Node 侧镜像定义（Dockerfile）

**职责**：构建 Engine Host（仿真宿主）的容器镜像：Node 24 alpine 底座，装生产依赖，拷入 `services/engine-host` 与 `catalog/`。

## 内容

| 文件 | 行数 | 关键步骤 |
|---|---|---|
| `Dockerfile` | 19 | `FROM node:24-alpine` → `npm install --omit=dev` → 拷 `services/engine-host` 与 `catalog/` → `EXPOSE 4000` → `CMD ["node", "dist/main.js"]` |

## 与上下层的关系

- 被 [`../compose.local.yaml`](../compose.local.yaml) 的 `engine-host` 服务引用（构建上下文为工程根）。
- 服务本体：[`../../services/engine-host/`](../../services/engine-host/README.md)。

## 已知的坑与纪律

- **镜像直接跑 `dist/main.js`，不含构建步骤**：必须先本地构建出 `dist/` 再打镜像——`npm install --omit=dev` 不装 devDependencies，无法在镜像内构建。
- 容器端口 **4000** 与本地无容器路径的 **8010** 不同（两套拓扑，见 [`../README.md`](../README.md)）。
- 上游 Ray Optics 的 `dist-node` bundle 不在本镜像的拷贝范围内——依赖引擎的容器部署需要另行挂载/内置（未闭环项）。
