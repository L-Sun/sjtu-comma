# 学生模块接口契约

Web 工作台由教师完成。第一课先阅读 `lesson_01_agent/README.md`，和教学 Chat 一起完成 `agent.py` 中六个辅助函数与 `run_turn()` 循环；接口和事件格式已提供。未完成时由预置教学 Chat 提供 list_files、read_course_file、check_agent；它不依赖作业函数。保存 agent.py 后自动检查，通过后下一轮加载同一已检查版本的学生实现，保留对话。修改出错后返回教学 Chat。运行记录中的 runner 和 source_version 标明本轮实际实现及代码 SHA-256。本文供查阅接口细节。第二课填写 `cua.py`。不要通过修改 `common/core/policy.py` 绕过实验条件。

## LLM（已提供，无需实现）

`common/core/llm.py` 中的 `complete(messages, tools, config) -> ModelReply` 是**一次**模型请求。通过 `context.complete()` 使用。

- `config.base_url`：OpenAI 兼容接口前缀，来自设置面板。
- `config.api_key`：密钥；不打印、不写日志。
- `config.model`、`config.max_tokens`：模型 ID 和输出上限。
- `messages`：OpenRouter 消息数组，包含 system/user/assistant/tool。
- `ToolSpec.api_dict()`：工具的 function-calling 格式。
- `ModelReply.message`：保留完整 assistant 消息，包含 `tool_calls` 和供应商需要的 reasoning 元数据。
- `ModelReply.usage`：原样传递用量；没有费用时显示缺失，不自行猜测。

使用异步 API 请求。每次请求检查 HTTP 状态和响应内容。工具参数尚未执行，不要在此函数中调用工具。

可通过 OpenRouter `/api/v1/models` 的 `supported_parameters` 核对模型参数。不要向不支持的模型强行传 `temperature`；严格 provider routing 会因此拒绝请求。教师参考客户端会按目录选择可用参数，并在 usage 事件里附加 `request_parameters`。运行记录的 `temperature=null` 表示未显式设置或未知，不代表温度为0。

## Agent

`run_turn(user_text, state, context)` 处理一个用户回合，可以包含多次模型调用。此函数也是学生作业（第 7 步）。与 Chat 一起实现循环，按 README 流程图调用六个辅助函数，并实现多工具、异常与停止条件。

学生函数按约定追加 `state.messages`，无需自己设计状态管理。新对话和取消时框架清空它。`context` 提供：

| 属性 | 用途 |
| --- | --- |
| `system_prompt` | 首条 system 消息内容 |
| `config` | 当前模型、模式、轮数上限 |
| `tools` | 此次允许的工具定义 |
| `complete(messages, tools, config)` | 教师已提供的模型调用函数 |
| `execute(name, arguments)` | 已检查工具白名单/参数的执行入口 |
| `emit(Event(...))` | 通知界面，不用接触 HTTP 或浏览器 DOM |

事件：

```python
Event("assistant", {"text": "回复"})
Event("status", {"text": "第 2 次请求"})
Event("tool_start", {"id": call_id, "name": tool_name, "arguments": arguments})
Event("tool_end", {"id": call_id, "name": tool_name, "result": tool_result})
Event("usage", reply.usage)
Event("status", {"text": "达到上限", "limit": True})
```

重要约束：

1. 保存含 `tool_calls` 的 assistant 消息，再写回对应 ID 的 tool 结果。
2. 一个模型回复包含多个调用时，每个调用都需要结果。电脑动作顺序执行。
3. 所有 tool 结果写回后，再追加图片 user 消息，避免打断工具结果批次。
4. `ToolResult.text`、`is_error` 和 `images` 都有意义；不能把图片对象简单 `str()`。
5. 图片用 `{"type":"image_url","image_url":{"url":"data:image/png;base64,..."}}` 作为 user 内容块。注明来源工具调用 ID。
6. 达到 `max_rounds` 必须停止；不要捕获/吞掉 `asyncio.CancelledError`。

不要求 streaming；先完成整段回复即可。

## 教师提供的 Edit 工具

A5 的 `context.tools` 自动包含以下工具，均通过通用的 `context.execute` 分发，无需写特例。可写路径仅为本轮副本中的 `course_page.py`。

| 工具 | 契约 |
| --- | --- |
| `search_file(path, query, after_line=0)` | 字面搜索，最多返回20处带行号上下文，可翻页；返回文件 `version` |
| `read_file(path, start_line=1, end_line=120)` | 首尾行均包含，每次最多160行；返回 `version` 和带行号文本，前缀不是文件内容 |
| `edit(path, base_version, edits)` | `edits` 是1—12个 `{old_text, new_text}`；基于同一版本检查所有替换后一次写入 |

`old_text` 必须非空、唯一匹配且不与其他补丁重叠，每个字符串最多8,000字符。不要全局替换或回传完整5,000行文件。版本变化、匹配歧义或任一补丁失败都会返回 `ToolResult(is_error=True)`，整批不写入。成功返回新版本和实际 diff。模型决定哪里改，教师工具程序负责验证和回写。

每次开始 A5 重建基线并清空模型历史。结束后框架检查8项代码条件，结果写入 `run.json` 的 `grade`，不以模型自报为准。工具循环仍需把失败结果回传模型；不要求参数生成到一半就执行，也不要求 token 级流式解析。

## 教师提供的 Bash 工具

Lesson 01/02 的 `context.tools` 还包含 `bash(command, cwd?, timeout_seconds=30)`，经 `context.execute` 调用。名称是统一接口：macOS 实际运行 zsh，Linux 运行 Bash，Windows 优先 pwsh、其次 powershell；具体平台、shell、默认目录在工具 description 中。模型应依照该说明生成语法，不根据工具名假定 Bash。

`command` 最多16000字符，超时1—120秒，非交互执行且每次是新进程。`cwd` 可为绝对路径或相对于工具默认目录的路径；默认目录为项目根，A5 为当轮代码副本。普通本机权限，没有目录隔离；A5 题目仍要求通过 edit 完成指定补丁。

`ToolResult.text` 是 JSON，字段为 `platform`、`shell`、`cwd`、`exit_code`、`stdout`、`stderr`、`timed_out`、`stdout_truncated`、`stderr_truncated`，成功启动的命令另有 `duration_seconds`。非零退出、超时和启动失败会设置 `is_error=True`；启动失败的 exit_code 为 null。输出按 UTF-8 解码，每个流最多16KiB。工具不要求 stdin 输入，不加载用户 shell 配置，不延续上一条命令的变量和 cd 状态。

界面复用 `tool_start`/`tool_end` 显示简化命令和退出结果；不要求学生写 shell 或 UI 特例。Lesson 01 提供基础工具；Lesson 02 保留 bash 并叠加 Cua。电脑实验需检查模型是否按要求仅使用 Cua 操作界面。

## Cua

框架管理 MCP 进程和会话生命周期。学生实现：

- `list_tools(session) -> list[ToolSpec]`：通过 MCP 查询，将 `inputSchema` 转成公共工具结构。
- `call_tool(session, name, arguments) -> dict`：执行，返回 MCP 结果的字典形式，保留 `content`、`structuredContent`、`isError`。

框架从原生工具中选出窗口观察、点击、输入、按键和滚动；不会向模型提供文件读取、shell、DOM、浏览器脚本等旁路工具。

`get_window_state` 的观察开关由框架注入，模型不能修改。输出也再次过滤。纯视觉模式移除 element_token；树/混合允许从树中获取的 token。所有模式保留窗口识别元数据。注意：因此该实验比较的是观察与定位方式组合，并非只改变输入、严格固定所有动作寻址能力的因果实验。

本实验的策略层控制教学条件，不是隔离恶意 Python 代码的安全沙箱。
