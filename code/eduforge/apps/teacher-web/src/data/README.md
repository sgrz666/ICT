# data — 前端数据集

**职责**：教师端内置数据集。当前只有一个文件：**81 个交互式光学演示案例**的元数据（上游 Ray Optics 官方图库的中文化整理），供「光学仿真模拟器」与「81 案例库」两个视图共同消费。

## 内容（逐文件）

| 文件 | 行数 | 内容 |
|---|---|---|
| `galleryData.json` | 983 | 81 条案例；每条字段：`id` / `category` / `categoryName` / `title` / `description` / `contributors` / `sceneUrl` / `pageUrl` |

## 分类分布（81 条，实测）

| category | categoryName | 数量 |
|---|---|---|
| reflection | 光的反射 | 16 |
| refraction | 光的折射 | 12 |
| lens | 透镜 | 14 |
| combination-of-lenses | 透镜组合 | 13 |
| GRIN-optics | 渐变折射率光学 | 7 |
| miscellaneous | 其他 | 19 |

## 与上下层的关系

- 消费方：[`../components/GalleryView.tsx`](../components/README.md)（分类过滤 + 全文检索）、[`../components/SimulatorView.tsx`](../components/README.md)（场景选择器 + 热门预设）。
- 场景本体不在本目录：`sceneUrl` 指向模拟器的场景路径（经网关同源 `/simulator/` 托管），这里只存元数据。

## 已知的坑与纪律

- 改数据只改这一个文件——两个视图都直接 import，没有中间层。
- `category` 取值必须与 `GalleryView.tsx` 的 `CATEGORIES` 常量一致；新增分类两处同改。
- `description` 含 LaTeX 片段（如 `\frac`、`^\circ`）——渲染端注意转义与展示兼容。
