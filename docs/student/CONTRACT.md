# 学生模块接口契约

Web 工作台由教师完成。第一课先阅读 `lesson_01_agent/README.md`，先与教学 Chat 完成 `tools.py` 的 Edit 接入，再用接通的 Edit 完成 `agent.py` 中四个辅助函数与 `run_turn()` 核心循环；网页事件、错误和图片处理由 `lesson_io` 提供。未完成时由预置单步教学 Chat 提供 list_files、read_course_file、check_agent；它不依赖 Agent 作业函数；tools.py 的声明与分发检查通过后，下一轮才开放 edit_course_file。Edit 保存成功的同一次工具结果会附带 `checks`，无需额外模型请求或单独调用 check_agent；通过后下一轮加载同一已检查版本的学生实现，保留对话。修改出错后返回教学 Chat。运行记录中的 runner 和 source_version 标明本轮实际实现及代码 SHA-256。教学 Chat 每次只请求一次模型，工具结果保存后等待用户继续。继续请求不追加 user 消息；普通会话等待状态可在重启后恢复。本文供查阅接口细节。第二课填写 `cua.py`。不要通过修改 `common/core/policy.py` 绕过实验条件。

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

`run_turn(user_text, state, context)` 处理一个用户回合，可以包含多次模型调用。消息准备和 `with lesson_io(...) as context` 已提供；学生实现 `with` 块内的核心循环。点击继续时 `user_text` 为 `None`，不追加新的 user 消息。

原始 `RunContext` 提供 `system_prompt`、`config`、`tools`、`complete`、`execute` 和 `emit`。进入 `lesson_io` 后，循环使用以下接口：

| 接口 | 用途 |
| --- | --- |
| `config.max_rounds` | 学生循环的次数上限 |
| `tools` | 当前可用工具定义 |
| `complete(messages, tools, config)` | 请求一次模型；自动显示文字和用量 |
| `run_tool(call)` | 调用学生的参数解析与工具执行函数，返回 ToolResult；自动记录事件与收集图片 |

四个辅助函数是同一教学阶段：保存完整回复、解析参数、等待执行、创建工具结果消息。`execute_tool` 收到原始 context，使用 `await context.execute(name, arguments)`；循环中的 `context.run_tool(call)` 会连接这两个工具相关辅助函数。

学生负责的规则：

1. 每次模型返回后，将完整 `reply.message` 保存到历史。
2. 根据 `reply.tool_calls` 是否为空决定结束，不能只看是否有文字。
3. 遍历全部工具调用，将每个 ID 对应的结果放回历史，再次请求模型。
4. 最多请求 `config.max_rounds` 次，不清空历史、不重复追加用户输入。

框架提供的规则：

- `lesson_io` 发送 assistant、usage、tool_start、tool_end 和上限事件，学生无需手写 Event。
- 参数解析或工具执行的普通错误转为错误 ToolResult；ExercisePending 与取消信号继续向外传播。
- 同批工具的全部结果写回后，才在下一次模型请求前追加图片消息，保留来源 ID 与图片内容。
- `lesson_io` 本身不会请求模型、执行工具、回传工具结果或自动循环；这些动作只发生在学生调用相应接口时。

第二课使用同一组接口与标准循环。不要求 streaming。

## 教师提供的 Edit 工具

「长文件局部编辑」 的 `context.tools` 自动包含以下工具，均通过通用的 `context.execute` 分发，无需写特例。可写路径仅为本轮副本中的 `course_page.py`。

| 工具 | 契约 |
| --- | --- |
| `search_file(path, query, after_line=0)` | 字面搜索，最多返回20处带行号上下文，可翻页；返回文件 `version` |
| `read_file(path, start_line=1, end_line=120)` | 首尾行均包含，每次最多160行；返回 `version` 和带行号文本，前缀不是文件内容 |
| `edit(path, base_version, edits)` | `edits` 是1—12个 `{old_text, new_text}`；基于同一版本检查所有替换后一次写入 |

`old_text` 必须非空、唯一匹配且不与其他补丁重叠，每个字符串最多8,000字符。不要全局替换或回传完整5,000行文件。版本变化、匹配歧义或任一补丁失败都会返回 `ToolResult(is_error=True)`，整批不写入。成功返回新版本和实际 diff。模型决定哪里改，教师工具程序负责验证和回写。

「长文件局部编辑」首次运行创建基线副本；后续消息复用学生 Agent 的历史与上轮文件，只有点击“重置实验”才清空历史、恢复基线。每轮保存独立文件快照，避免后续撤销覆盖先前记录。结束后框架检查8项代码条件，结果写入 `run.json` 的 `grade`，不以模型自报为准。工具循环仍需把失败结果回传模型；不要求参数生成到一半就执行，也不要求 token 级流式解析。

## 教师提供的 Bash 工具

Lesson 01/02 的 `context.tools` 还包含 `bash(command, cwd?, timeout_seconds=30)`，经 `context.execute` 调用。名称是统一接口：macOS 实际运行 zsh，Linux 运行 Bash，Windows 优先 pwsh、其次 powershell；具体平台、shell、默认目录在工具 description 中。模型应依照该说明生成语法，不根据工具名假定 Bash。

`command` 最多16000字符，超时1—120秒，非交互执行且每次是新进程。`cwd` 可为绝对路径或相对于工具默认目录的路径；默认目录为项目根，「长文件局部编辑」 为当轮代码副本。普通本机权限，没有目录隔离；「长文件局部编辑」 题目仍要求通过 edit 完成指定补丁。

`ToolResult.text` 是 JSON，字段为 `platform`、`shell`、`cwd`、`exit_code`、`stdout`、`stderr`、`timed_out`、`stdout_truncated`、`stderr_truncated`，成功启动的命令另有 `duration_seconds`。非零退出、超时和启动失败会设置 `is_error=True`；启动失败的 exit_code 为 null。输出按 UTF-8 解码，每个流最多16KiB。工具不要求 stdin 输入，不加载用户 shell 配置，不延续上一条命令的变量和 cd 状态。

界面复用 `tool_start`/`tool_end` 显示简化命令和退出结果；不要求学生写 shell 或 UI 特例。Lesson 01 提供基础工具；Lesson 02 保留 bash 并叠加 Cua。电脑实验需检查模型是否按要求仅使用 Cua 操作界面。

## Cua

框架管理 MCP 进程和会话生命周期。学生实现：

- `list_tools(session) -> list[ToolSpec]`：通过 MCP 查询，将 `inputSchema` 转成公共工具结构。
- `call_tool(session, name, arguments) -> dict`：执行，返回 MCP 结果的字典形式，保留 `content`、`structuredContent`、`isError`。

框架从原生工具中选出窗口观察、点击、输入、按键和滚动；不会向模型提供文件读取、shell、DOM、浏览器脚本等旁路工具。

`get_window_state` 的观察开关由框架注入，模型不能修改。输出也再次过滤。纯视觉模式移除 element_token；树/混合允许从树中获取的 token。所有模式保留窗口识别元数据。注意：因此该实验比较的是观察与定位方式组合，并非只改变输入、严格固定所有动作寻址能力的因果实验。

本实验的策略层控制教学条件，不是隔离恶意 Python 代码的安全沙箱。

## 可选上下文压缩入口

第一课提供空的 `compact_history(messages, context)`，由消息准备代码在核心 Loop 前调用。函数可按需原地修改历史；基础检查不要求实现压缩。保留 `@context_compaction`：装饰器只报告运行、结束、失败或取消，不替学生实现算法或请求模型。UI 显示“正在上下文压缩”，这一过程不计入工具调用次数。
