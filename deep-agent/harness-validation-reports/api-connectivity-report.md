# api-connectivity-report.md

阶段 D：真实 DeepSeek API 接入与联调。全程未使用 Mock 模型；`pnpm run mock:llm` 未被调用。密钥不出现在聊天、报告或提交内容中。

## 1. 接入方式

先读官方 Provider 文档再决定模型与传输：`docs/user/guide/providers.md` 与 `packages/llm/llm-deepseek/README.md`。

- 内置 provider 路由：`deepseek-official`，适配器 `@deepseek-ai/dsh-llm-deepseek`。
- 默认 `baseURL = https://api.deepseek.com/anthropic`，即 **Anthropic Messages 协议**（不是 OpenAI Chat Completions）；请求追加 `/v1/messages`，图片走 `/v1/files`。
- 鉴权：API key 用 `x-api-key` 头（账户 token 模式用 `x-dsh-auth-token`，本次未用）；请求拒绝重定向以免凭据外泄。
- 凭据解析顺序（官方实现）：`$DSH_HOME/.credentials.yaml`（GUI 托管）→ 进程环境 → 项目 `.env` → 用户 `.env`。
- 本次接入路径：在仓库根 `.env` 写入 `DEEPSEEK_API_KEY`（该文件被上游 `.gitignore` 覆盖，未入库、未打印）。官方 Web UI 的 Settings → Models →「编辑 DeepSeek (deepseek-official)」表单实测显示 `已检测到环境变量（DEEPSEEK_API_KEY）`，DeepSeek 卡片状态为「API 密钥已配置」。
- 未把密钥二次写入托管存储 `.credentials.yaml`：环境变量已被官方 UI 与 headless 两条路径识别，再存一份只会多一处需要清理的副本。用户在聊天里贴出的密钥需在 DeepSeek 控制台轮换（用户已声明用后删除）。

## 2. 模型目录（不猜模型名，取实际服务返回值）

`GET https://api.deepseek.com/models`（`Authorization: Bearer`）→ HTTP 200：

| model id | 显示名 | 输入模态 | context | max output | effort |
|---|---|---|---|---|---|
| `deepseek-flash` | DeepSeek-V4.1-Flash | text, image | 1,048,576 | 393,216 | low/high/max，默认 high |
| `deepseek-v4-pro` | DeepSeek-V4-Pro | text | 1,048,576 | 393,216 | low/high/max，默认 high |

- 与 Harness 内置默认目录一致（`llm-deepseek` 未配置 `models` 时即 advertise `deepseek-flash` + `deepseek-v4-pro`，各 1,000,000 上下文）。base bundle 默认选择：`provider: deepseek-official`、`model: deepseek-flash`。
- `GET /anthropic/v1/models` → HTTP 404：官方 Anthropic 兼容根不提供模型列举端点，Harness 依赖配置目录，属预期。
- 注意：仓库内测试 patch 出现的 `deepseek-v4-flash` 在实际服务目录中不存在；按实际目录使用 `deepseek-flash`。

## 3. 工具调用协议（协议级预检）

`POST https://api.deepseek.com/anthropic/v1/messages`，声明一个 `get_weather` 工具、`tool_choice: auto` → HTTP 200：

- `stop_reason: "tool_use"`；
- content 块依次为 `thinking`（带 `signature`）、`text`、`tool_use`（`id=call_00_…`，`name=get_weather`，`input={"city":"Beijing"}`）；
- `usage` 返回 `input_tokens=300 / output_tokens=48` 及 cache 字段。

结论：Harness 所需的 Messages 工具调用协议、思考块签名回传、usage 计量在该端点均可用，参数为合法 JSON 对象，无协议错误。

## 4. 经 Harness 的真实调用（框架级）

| 运行 | 会话 | 结果 | 用量（各 step 求和） |
|---|---|---|---|
| 冒烟：`Reply with exactly: OK` | `session-63146e58-…` | exit 0，4s，模型返回 `OK` | in 1,691 / out 2 / cacheRead 5,760 |
| 测试 1 工作区探索 | `session-d6952efb-…` | exit 0，20s，1 turn / 4 steps | in 4,719 / out 3,064 / cacheRead 30,336 / total 38,119 |
| 测试 2 建计算器并跑测试 | `session-6074ad2f-…` | exit 0，18s | 4 calls（见测试报告） |
| 测试 3 失败后自主修复 | `session-18a2e93f-…` | exit 0，24s，8 steps | in 7,953 / out 2,855 / cacheRead 89,344 / total 100,152 |
| 测试 4 多工具组合 | t4 | exit 0，58s | 18 calls |
| 测试 5 会话恢复 | 复用 `session-18a2e93f-…`，日志续写为 **turn 2** | exit 0，32s | in 1,025 / out 5,672 / cacheRead 51,456 / total 58,153 |

- KV cache 命中显著（cacheRead 远大于 input），与适配器声明的 DeepSeek 缓存复用一致。
- 推理等级：Web UI 模型条显示 `DeepSeek-V4.1-Flash · High`，与端点默认 effort 一致。
- 失败码：适配器声明的稳定错误码族（`AUTH`/`QUOTA`/`RATE_LIMIT`/`INVALID_REQUEST`/`TRANSPORT`/…）在本次联调中**一个都没触发**；全部 HTTP 200。出现的唯一稳定报错来自本地沙箱（`SetNamedSecurityInfoW … Win32 5`），与 API 无关。

## 5. 检查项逐条结论

| 要求 | 结论 | 证据 |
|---|---|---|
| 1. API 能否建立连接 | 通过 | `/models` 200；`.env` 密钥被官方 UI 识别为已配置 |
| 2. 能否返回普通文本 | 通过 | 框架内 `Reply with exactly: OK` → `{"type":"final","text":"OK"}` |
| 3. 是否支持 Harness 需要的工具调用协议 | 通过 | Messages 协议 `tool_use` 块 + `stop_reason: tool_use`；框架内真实发出 `pwsh/read/glob/edit/skill/…` 工具调用 |
| 4. 工具调用期间是否发生参数/协议错误 | 未见 API 侧错误 | 6 次运行中所有 `tool_result` 的 error 均来自本地沙箱或模型自身命令写法；无 `MALFORMED_RESPONSE`/`STREAM_CLOSED`/`INVALID_REQUEST` |
| 5. 鉴权/额度/网络/兼容性 | 未见鉴权与额度问题 | 无 401/403/QUOTA；唯一网络噪声是 npm 下载的低速告警（与 API 无关） |

## 6. 未测得与限制

- **API 成本（货币）：未测得。** 框架只上报 token 计数，未提供价格字段；DeepSeek 该模型组价目未在本次核实，不做推算。
- **单次请求端到端时延**：只有整轮耗时，未拆分网络时延 → 未测得。
- Web UI 的 Settings → Models **保存**按钮写入托管存储的链路未单独验证（本次走环境变量），标记 pending。
- 图片输入（`deepseek-flash` 声明支持）未测试 → 官方已有、本轮未验证。
- `deepseek-account` 登录路由（非 API key）未测试 → 官方已有、本轮未验证。
