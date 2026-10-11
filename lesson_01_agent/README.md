# Lesson 01 · 用 Python 拼出一个 Agent

本课只做三件事：**接入 Edit → 一起完成四个辅助函数 → 写出核心 Loop**。

目标是理解：模型提出工具调用，Python 执行工具，把结果交回模型，再由模型决定下一步。你需要会函数、列表、字典、`for` 和 `if`；网页展示、模型接口、错误转换和图片处理均已提供。

## 开始

```bash
uv run mini-agent --lesson 1 --open
```

在左下角填写 Base URL、API Key 和模型。先用「测试 LLM」确认连接，然后新建对话。

教学 Chat 每次只请求一次模型。工具返回后点击「继续下一步」，或发送补充要求，模型才会读到结果。完成你自己的 Loop 后，才会自动执行“模型 → 工具 → 模型”。

课程路径已知，可以直接读文件；不用每次先列目录。工具 `read_course_file` 返回版本和带行号文本，`next_start_line` 非空表示还有未读内容，按需继续读取。

## 阶段一 · 接入 Edit

修改 [tools.py](tools.py) 的两个 TODO：

| 函数 | 你要做的事 |
| --- | --- |
| `get_tools()` | 返回一个 `ToolSpec`，声明 `edit_course_file` 的名称、用途和参数 |
| `call_tool(name, arguments, editor)` | 名称匹配时 `await editor.execute(arguments)`，返回原来的结果；未知名称返回错误 |

`ToolSpec` 接收 `name`、`description`、`parameters`；参数定义 `EDIT_PARAMETERS` 已提供。

对 Chat 说：

> 读取 tools.py 和 README，简短解释工具声明与执行分发，一次给出这两个函数的接入代码。

这一次需要手动保存代码，因为编辑工具还没有接通。保存后让 Chat 调用 `check_agent`。Edit 的两项检查通过后，下一轮就能使用它修改作业。

编辑范围只有 `lesson_01_agent/tools.py` 和 `lesson_01_agent/agent.py`。编辑前读取最新版本，使用 `version` 作为 `base_version`；精确替换的原文不要带行号。框架检查版本、唯一匹配和 Python 语法，保存备份后整批写入。

**保存成功会直接返回 `checks`，不需要另开一轮调用 `check_agent`。** 保存成功不代表作业通过：看 `checks.ready` 和逐项结果。若编辑未保存，先处理版本冲突或原文匹配问题。手动修改文件后，仍可点击「检查我的代码」。

## 阶段二 · 一起完成四个辅助函数

这四个函数是同一条数据流，一次讨论、一个编辑批次完成，不必每填一行就检查。

```text
模型完整回复 → 保存到历史
工具调用参数 → 解析成字典 → 执行工具 → 包装成工具消息
```

### 1. 保存模型回复

`remember_assistant_message(messages, reply)` 把完整的 `reply.message` 字典追加到 `messages`。它可能同时包含文字、工具调用和模型元数据，不能只保存 `reply.text`。

### 2. 解析工具参数

`parse_tool_arguments(call)` 用 `json.loads()` 解析 `call["function"]["arguments"]`，并确认结果是 `dict`；不是字典就抛出 `ValueError`。无效 JSON 的异常直接抛出，不使用 `eval()`。

例如 `'{"operation":"multiply","a":6,"b":7}'` 应得到一个有三个键的字典。

### 3. 执行工具

`execute_tool(name, arguments, context)` 等待 `context.execute(name, arguments)` 并返回原来的 `ToolResult`。不要硬编码工具名，不需要自己捕获异常。

### 4. 包装结果

`make_tool_message(call_id, result)` 返回包含三个键的字典：

| 键 | 内容 |
| --- | --- |
| `role` | `"tool"` |
| `tool_call_id` | 原来的 `call_id` |
| `content` | `json.dumps({"is_error": result.is_error, "text": result.text}, ensure_ascii=False)` |

这个函数只创建消息，循环负责把它追加到历史。错误结果也要交回模型，不能跳过。

对 Chat 说：

> 读取 agent.py，解释这四个函数之间的数据流，用一个编辑批次完成它们。保留 run_turn 的 TODO，根据编辑返回的 checks 告诉我结果。

四个函数完成会显示 4/5；核心 Loop 仍然需要你和 Chat 编写。

## 阶段三 · 写出核心 Loop

[agent.py](agent.py) 的 `run_turn()` 中已提供消息准备和 `with lesson_io(...) as context`。保留这些代码，在 `with` 块中实现循环。

`lesson_io` 只处理输入输出：显示文字与用量、记录工具执行、转换普通错误、传递停止信号、追加图片和显示轮数上限。**它不会替你请求模型、遍历工具、回传工具结果或决定继续。**

循环只要完成这条主线：

```text
最多重复 max_rounds 次：
    请求模型，保存完整回复
    没有工具调用 → 结束
    遍历本次回复的全部工具调用：
        执行工具
        将对应结果追加到历史
    带着所有结果，再次请求模型
```

需要的接口都在这里：

| 操作 | 调用方式 |
| --- | --- |
| 请求模型 | `reply = await context.complete(messages, context.tools, context.config)` |
| 保存完整回复 | `remember_assistant_message(messages, reply)` |
| 判断是否结束 | `reply.tool_calls` 为空时 `return` |
| 执行一个调用 | `result = await context.run_tool(call)` |
| 创建对应结果 | `make_tool_message(call["id"], result)` |
| 写回结果 | 把上面返回的字典追加到 `messages` |
| 限制循环次数 | `context.config.max_rounds` |

`context.run_tool(call)` 已连接你写的 `parse_tool_arguments` 和 `execute_tool`。普通错误也返回 `ToolResult`；你只需把它正常写回历史。网页事件、用量和图片不属于作业，不需要写 `Event`、`emit` 或 `try/except`。

注意三个控制流程问题：

- 有回复文字仍可能有工具调用；根据 `reply.tool_calls` 判断是否结束。
- 一次回复可能包含多个工具；每个结果都写回后再问模型。
- `messages` 复用当前历史，不要清空，也不要在每次循环时重复追加用户输入。

点击继续时 `user_text` 为 `None`，消息准备代码会保留已有工具结果，不追加新用户消息。循环不用另写“继续”分支。

对 Chat 说：

> 和我推演“计算6×7”：模型发出调用，工具返回42，模型据此回答。然后在 with 块里写出这个循环，用 Edit 保存；根据返回的全部检查结果一次修复相关问题。

编辑后会自动检查聊天、多轮历史、工具往返、批量工具和停止条件。全部通过后，下一轮由你的 Agent 接管；当前回合仍保持原来的运行方式。

## 可选扩展 · 上下文压缩

`agent.py` 预留 `compact_history(messages, context)`，函数体为 `pass`。它不属于基础五项检查；空实现不修改历史，也不请求模型。完成核心 Loop 后，可再和 Chat 一起设计压缩策略。

提供的消息准备代码会在进入 Loop 前调用它。`@context_compaction` 负责网页状态：函数执行期间显示“正在上下文压缩”，返回后结束这一条记录，报错或停止时显示对应状态。保留装饰器，不需要自己写 UI 事件。

实现时在原来的 `messages` 列表上修改，保留 system、当前任务和完整的工具调用/结果配对；需要时才压缩。摘要调用次数、保留范围与触发条件由你的函数决定，框架不提供压缩算法。空函数立即返回，所以不会持续停留在压缩状态。

## 自己验证

```bash
# 所有检查均离线执行，不消耗模型额度
uv run python -m lesson_01_agent.check_edit
uv run python -m lesson_01_agent.check
# 需要定位时，可单独检查某个辅助函数或核心循环
uv run python -m lesson_01_agent.check 2
uv run python -m lesson_01_agent.check loop
```

最后在网页发送：

> 先计算 6×7，再取得当前时间，最后根据工具结果回答。

查看执行记录，确认模型请求了工具、工具结果写回了历史、模型又发起了请求。能解释这三件事，就理解了 Agent loop。

需要了解提供的接口时，可查阅 [公共类型](../common/core/types.py)、[输入输出支持](../common/core/lesson_io.py) 和 [接口契约](../docs/student/CONTRACT.md)，不必把它们重新实现。

下一课 [Computer Use](../lesson_02_computer_use/README.md) 保留同一套核心循环，提供标准实现，只需再接入 Cua 工具。
