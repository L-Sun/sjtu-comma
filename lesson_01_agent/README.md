# Lesson 01 · 用 Python 拼出一个 Agent

你已经会写 Python 的函数、列表、字典和 `for` 循环，就可以开始这一课。不需要有 Web、网络接口或大型项目的开发经验。

本课的目标是：**让模型提出工具调用，由 Python 执行工具，再把结果交给模型，直到模型给出回答。**

先与教学 Chat 一起接通 [tools.py](tools.py) 中的 Edit，再用刚接入的编辑能力完成 [agent.py](agent.py) 中的 **4 个辅助函数，以及第 5 步 `run_turn()`：真正的 Agent loop**。函数名称和参数固定，循环体由你们一起实现。模型接口、工具、网页和图片转换已提供，不需要自己设计工程框架。

## 先与 Chat 接入 Edit，再用它一起写 Agent

第一项练习不是写完整 Loop，而是把 **Edit 工具接进教学 Chat**。从这一步开始，学生与 Chat 一起获得后续会反复使用的编辑能力。

教学 Chat 是**单步执行器**：每次发送消息或点击“继续下一步”，只请求一次模型，执行这次回复提出的工具后暂停。工具输出保存在历史中，可在执行过程中展开“查看工具输出”；此时模型还没读到这些结果。点击继续才会携带结果发起下一次请求，也可以直接发送补充要求。

例如：读取文件 → 点击继续 → 修改文件 → 点击继续 → 检查或解释结果。继续按钮不会发送一条虚构的用户消息，也不会清空输入框草稿。普通会话的等待状态在刷新和重启后保留。

Edit 接通让你能**修改文件**；完成 `run_turn()` 后，顶部切换为**自动循环**，自己的 Agent 会自动处理工具结果并推进下一步，直到模型回答或达到上限。

在项目根目录启动：

```bash
uv run mini-agent --lesson 1 --open
```

在左下角设置 Base URL、API Key 和模型。初始显示 **教学 Chat · 单步模式 · Edit 0/2 · Loop 0/5**。现在只能使用三个工具：

| 工具 | 用途 |
| --- | --- |
| `list_files` | 列出课程文件，确认路径 |
| `read_course_file` | 读取源文件与讲义，返回行号和文件版本 |
| `check_agent` | 检查 Edit 接入和自己写的 Agent loop；使用假依赖，不产生模型费用 |

### 第一步：让模型看见 Edit 工具

先发给 Chat：

> 列出第一课的文件，读取 tools.py 和 README。和我一起接入 Edit：先解释 get_tools 与 call_tool 的区别，再给我需要粘贴的代码，保存后帮我检查。

打开 [tools.py](tools.py)，与 Chat 完成两个函数。**这两个函数初始也是 TODO，并没有替你接好。**

| 函数 | 学生与 Chat 要实现的内容 | 需要理解什么 |
| --- | --- | --- |
| `get_tools()` | 返回含一个 `ToolSpec` 的列表；名字是 `edit_course_file`，说明编辑用途，参数使用 `EDIT_PARAMETERS` | 工具名称、说明、参数让模型知道能请求什么；声明不会执行编辑 |
| `call_tool(name, arguments, editor)` | 根据工具名分发，用 `await editor.execute(arguments)` 调用底层执行器并返回结果；未知名称返回错误 | 模型只发请求，Python 在这里真正执行 |

`ToolSpec(name, description, parameters)` 和底层文件读写程序已提供。当前练习由你连接工具声明与执行入口，不需要研究磁盘原子写入等工程细节。

因为 Edit 还没有接通，**这次接入需要手动粘贴并保存 `tools.py`**。之后让 Chat 调用 `check_agent`，也可点击“检查我的代码”或运行：

```bash
uv run python -m lesson_01_agent.check_edit
```

检查使用假编辑器，确认声明正确、参数原样传入、确实等待执行、结果原样返回、未知工具不会编辑。通过后显示 **Edit 已接入**；下一轮教学 Chat 的工具列表才会真正出现 `edit_course_file`。

### 第二步：使用刚接入的 Edit，完成自己的 Agent

此时不再要求你每个函数都手动粘贴。直接对 Chat 说：

> Edit 已经接通。请读 agent.py，和我讨论当前待完成的函数，解释修改后用编辑工具写入，再检查结果。每次只完成当前讨论的步骤。

循环进行以下过程，直到 Agent loop 完成：

1. Chat 读取实际代码，与你一起讨论实现。
2. 用 `edit_course_file` 修改当前函数；右侧显示实际编辑调用，工具返回改动 diff。
3. 用 `check_agent` 检查，依据结果一起修复，再继续下一步。
4. 完成四个辅助函数与第 5 步 `run_turn()` 后，下一条消息由你们写出的 Agent 执行。这时它仍可使用你接入的 Edit 和检查工具来改进自己。

编辑必须使用读取返回的 `version`，作为 `base_version`；`old_text` 是原文件文本，不包括显示的行号。版本过期、匹配不唯一、范围重叠或 Python 语法错误时，整批不写入，请重新读取并修正。成功写入会备份原文件到本机 `.course-edits/`，并返回备份路径。

本课编辑工具可以修改 `lesson_01_agent/agent.py` 和 `lesson_01_agent/tools.py`。检查器、公共框架和配置文件不属于作业编辑范围。后续 A5 仍使用独立的长文件练习副本，比较模型编辑能力。

保存 `tools.py` 或 `agent.py` 后**不需要重启服务**。检查与加载使用同一已保存版本；当前单步或自动循环执行中不切换实现。如果 Edit 接入被改坏，工具会在下一轮撤下，教学 Chat 仍能读文件、讲解并帮助你手动修复接入。普通对话使用真实模型接口；离线检查本身不产生 API 费用。

## 1. 先看一个完整例子

用户输入：“计算 6 × 7”。一次 Agent 运行可能是这样：

| 顺序 | 谁在做 | 做了什么 |
| --- | --- | --- |
| 1 | Python | 把用户的问题加入消息列表 |
| 2 | 模型 | 返回一个请求：调用 `calculate`，参数是乘法、6、7 |
| 3 | Python | 解析参数，真正执行 `calculate`，得到 `42` |
| 4 | Python | 把工具结果加入消息列表 |
| 5 | 模型 | 看到工具结果，回答“42”，这次没有要求调用工具 |
| 6 | Python | 结束本轮，等待用户下一句话 |

**这里问了模型两次，执行了工具一次。** 模型给出工具名称和参数，Python 在 `execute_tool()` 中完成实际执行。

如果用户只是说“你好”，模型可能直接回答，不调用任何工具。若任务更复杂，模型可能需要多次调用工具；每次都重复“问模型 → 执行工具 → 交回结果”。这就是 **Agent loop（Agent 循环）**。

## 2. 先认清三个东西

### `messages`：用一个列表记住对话

每条消息是一个字典，通常有 `role` 和 `content` 两个键：

```python
messages = [
    {"role": "system", "content": "你是课堂助手"},
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
]
```

| `role` 的值 | 含义 |
| --- | --- |
| `system` | 给模型的基本说明，只在新对话的开头放一次 |
| `user` | 用户说的话 |
| `assistant` | 模型的回复，可能是文字，也可能包含工具调用请求 |
| `tool` | Python 执行工具后得到的结果 |

网页把历史列表放在 `state.messages` 中。你需要在 `run_turn()` 中用 `messages = state.messages` 取出它，这两个名字指向同一个列表。使用 `messages.append(...)` 会保留修改；不要用 `messages = []` 清空历史。

同一对话的下一次输入还会拿到这个列表，模型才能看到之前说过的话。点击“新对话”时，框架会提供新的空列表。

### `context`：一包已经准备好的函数和设置

先把它当成一个可以用点号取东西的对象，不需要自己创建它，也不需要研究它的类定义。

| 写法 | 本课中怎么用 |
| --- | --- |
| `context.complete(messages, tools, config)` | 请求一次模型，返回 `ModelReply` |
| `context.execute(name, arguments)` | 执行一个工具，返回 `ToolResult` |
| `context.tools` | 模型这次可以使用的工具说明，原样传入即可 |
| `context.config` | 模型、接口地址等配置，原样传入即可 |
| `context.system_prompt` | 放进第一条 `system` 消息的文字 |
| `context.config.max_rounds` | 最多问模型几次，避免无限循环 |

`context.emit(...)` 负责让网页显示进度，函数本身已提供；第 5 步实现循环时，按讲义中的格式调用它。

### `reply` 和 `result`：模型回复与工具结果

`reply` 是模型返回的对象：

- `reply.message`：完整的消息字典，应该存入历史。
- `reply.text`：回复中的文字；也可能是空字符串。
- `reply.tool_calls`：工具调用请求列表；空列表表示这次不需要执行工具。

`result` 是工具返回的对象：

- `result.text`：工具输出的文字。
- `result.is_error`：是否失败，值为 `True` 或 `False`。
- `result.images`：可能存在的图片；处理代码已提供，第一课不用改。

这些对象都已由框架定义。你只需要读取上面的属性。

## 3. 按这张图自己实现调用顺序

先在 `agent.py` 中找到 `run_turn()` 的 TODO。这张图是实现指引，**消息准备已经提供，后面的循环流程由你和 Chat 实现**：

```text
用户发来一条消息
        │
        ▼
准备消息（已提供）             保留历史，追加本轮用户输入
        │
        ▼
┌─→ await context.complete(...)  在 run_turn 中直接问模型
│       │
│       ▼
│   remember_assistant_message()  TODO 1：存下完整回复
│       │
│       ├─ 没有 tool_calls → 结束本轮
│       │
│       └─ 有 tool_calls → 逐个处理：
│               parse_tool_arguments()  TODO 2：把参数变成字典
│               execute_tool()          TODO 3：真正执行工具
│               make_tool_message()     TODO 4：把结果包装成消息
│               messages.append(...)    第 5 步：自己放回历史
│       │
└───────┘  带着新结果，再问一次模型
```

在你要写的 `run_turn()` 中，用外层 `for` 控制模型请求次数，内层的 `for` 处理这一条回复中提出的所有工具调用。**不是执行完一个工具就结束，也不是有回复文字就一定结束：判断条件是 `reply.tool_calls` 是否为空。**

你还要在循环中实现两个结束条件：模型没有请求工具，或达到轮数上限。工具报错要交回模型，停止信号则要向外传递。第 5 步会指导你和 Chat 一起完成这些分支。

## 4. 只需要知道的 `async` / `await`

模型请求和工具执行可能要等待，因此它们是异步函数。本课只需要按现成写法调用：

```python
async def some_function(...):
    result = await another_function(...)
    return result
```

`await` 表示等这次调用完成，再把结果赋给 `result`。少写它，得到的就不是实际结果。

`execute_tool()` 和 `run_turn()` 使用 `async def`，内部调用时要写 `await`。保留函数定义即可；不需要自己写 `asyncio.run()`、线程或并发逻辑。

函数定义中的 `: str`、`: dict`、`-> None` 等是类型提示，分别告诉你参数和返回值是什么。`-> None` 表示只修改列表，不需要返回东西。

## 5. 按顺序填写，每一步都可以单独检查

第一次使用，在**项目根目录**打开终端，即能看到 `pyproject.toml`、`common/` 和 `lesson_01_agent/` 的目录，运行：

```bash
uv sync --python 3.12
```

`uv` 的安装入口见 [项目 README](../README.md#启动)。后面的检查全部使用固定回复的假模型和假工具，**不需要 API Key、不联网、不执行本机命令，也不会产生 API 费用**。

每个函数里目前有一行 `raise ExercisePending(...)`。它表示“这一步还没有完成”。填写自己的代码时，删除或替换该行；保留函数名和参数。

### 第 1 步：`remember_assistant_message()`

把 `reply.message` 整条追加到 `messages`，无需返回值。

不要自己用 `reply.text` 重建一条消息。模型可能在同一个消息中放入 `tool_calls` 和其他需要保留的字段，丢掉它们会影响后续对话。

```bash
uv run python -m lesson_01_agent.check 1
```

保存回复函数写好后，还需要在 `run_turn()` 中调用它，才能通过 `chat` 检查。继续完成工具相关函数，再在第 5 步把它们接成循环。普通聊天只是这个循环的无工具分支，教学 Chat 从一开始就可以使用。

### 第 2 步：`parse_tool_arguments()`

模型返回的单个工具请求长这样：

```python
call = {
    "id": "call-1",
    "type": "function",
    "function": {
        "name": "calculate",
        "arguments": '{"operation":"multiply","a":6,"b":7}',
    },
}
```

注意 `arguments` 外面有引号，它是 **JSON 字符串**。取出 `call["function"]["arguments"]`，用 `json.loads()` 把它变成 Python 字典：

```python
{"operation": "multiply", "a": 6, "b": 7}
```

检查转换结果是不是 `dict`；如果不是，抛出 `ValueError`。无效 JSON 自带的异常直接抛出即可，你将在 `run_turn()` 中处理。不要使用 `eval()`。

```bash
uv run python -m lesson_01_agent.check 2
```

### 第 3 步：`execute_tool()`

调用 `context.execute(name, arguments)`，等待完成后返回原来的 `ToolResult`。

工具名和参数是模型刚刚给出的。不要把函数限定为 `calculate`，也不要自己在这里写乘法；同一个函数随后还会执行时间查询、文件搜索等工具。

```bash
uv run python -m lesson_01_agent.check 3
```

### 第 4 步：`make_tool_message()`

工具结果不能只显示在网页上，还需要交给模型。返回一条有三个键的消息：

| 键 | 应填什么 |
| --- | --- |
| `role` | 固定为 `"tool"` |
| `tool_call_id` | 参数 `call_id`，原样保留 |
| `content` | 将 `{"is_error": result.is_error, "text": result.text}` 转为 JSON 字符串 |

转换字典为字符串使用 `json.dumps(..., ensure_ascii=False)`；`ensure_ascii=False` 让中文保持可读。它与第 2 步的 `json.loads()` 方向相反。

`tool_call_id` 把工具结果和原来的请求对应起来。请求叫 `call-1`，结果就要写 `call-1`，不要写成工具名 `calculate`。

成功与失败的结果都要返回。你写的 `run_turn()` 要把这条消息追加到历史；这个函数只负责创建并返回字典。

```bash
uv run python -m lesson_01_agent.check 4
```

### 第 5 步：和 Chat 一起实现 `run_turn()`

**Agent loop 就在这个函数里，这部分也属于作业。** 不要只完成前四个函数。保留函数开头已提供的消息准备代码，只把后面的 `raise ExercisePending(...)` 替换为你们共同实现的循环；使用前面接通的 Edit 写入。

先对 Chat 说：

> 请读取 agent.py 中的 run_turn 和 README 第 5 步。和我一起推演“计算6×7”时，模型如何请求工具、工具结果如何回传、模型如何再回答。然后根据这个过程一起写循环，解释每个 for、if、return 的位置，用接通的 Edit 写入并检查。

`run_turn()` 开头已提供以下代码，不再作为单独练习：

```python
messages = state.messages
if not messages:
    messages.append({"role": "system", "content": context.system_prompt})
if user_text is not None:
    messages.append({"role": "user", "content": user_text})
```

它复用当前会话的历史，首次加入 system，有新输入时只追加一次用户消息。点击“继续下一步”时 `user_text` 为 `None`，直接处理已有工具结果；这个分支已经提供。把后面的循环接在这里，不能清空历史或在每次模型请求前重复追加输入。完成循环后，`check chat` 会验证连续两轮消息。

#### 围绕工具调用，实现一个完整循环

直接实现 Agent loop。普通聊天对应其中的一个分支：模型没有提出工具请求，就显示回复并结束；不用另外写一个聊天程序，也不用先完成一个聊天阶段。

先讨论：为什么只问一次模型不够？工具返回结果后，谁来决定是否继续？用下面的伪代码作为思路，不要直接当作 Python 粘贴：

```text
已提供：保留历史，把本轮用户输入放进历史（只做一次）
重复，最多 max_rounds 次：
    问模型，保存完整回复，显示文字和用量
    如果没有工具调用：结束本轮
    对这条回复中的每个工具调用：
        显示“开始调用工具”
        解析参数，执行工具
        显示“工具已返回”
        把与调用 ID 对应的工具结果放回历史
    所有工具结果已放回历史，再开始下一次模型请求
```

在循环内部直接请求一次模型，拿到 `ModelReply`：

```python
reply = await context.complete(messages, context.tools, context.config)
```

`context.complete` 已经封装了 HTTP、鉴权与接口差异。这里直接传入当前历史、可用工具和配置，不需要再写一个转发函数。下一次循环会带着新追加的工具结果再次请求模型。

请自己决定并解释 `for`、`if`、`return` 的位置，再让 Chat 帮你检查。不要因为 `reply.text` 有文字就退出：同一条回复可能既有文字，又有 `tool_calls`。也不要把 `return` 放在第一个工具执行完的位置。

网页事件只负责展示。每次模型回复发出 `Event("usage", reply.usage)`；有回复文字时发出 `Event("assistant", {"text": reply.text})`。工具调用时用这两种事件，其中 `call` 是当前工具请求，`name` 是工具名，`result` 是执行结果：

```python
context.emit(Event("tool_start", {
    "id": call["id"], "name": name, "arguments": call["function"]["arguments"]
}))
context.emit(Event("tool_end", {"id": call["id"], "name": name, "result": result}))
```

若工具带图片，把 `image_messages(call, result)` 返回的列表先收集起来，一批工具的 `tool` 消息全部加入历史后，再用 `messages.extend(...)` 加入图片。图片转换函数已写好，不需要自己编码图片。

#### 在同一个循环里处理错误与结束条件

与 Chat 一起把以下规则放进循环的正确位置：

- 参数解析或工具执行出错：生成 `ToolResult(str(exc), is_error=True)`，仍然写回该工具的结果，再处理其余调用。模型看到错误后可以调整。
- `ExercisePending` 表示代码尚未完成，`asyncio.CancelledError` 表示用户按了停止：单独捕获并用 `raise` 继续抛出，不当成普通工具错误。
- 外层最多循环 `context.config.max_rounds` 次。没有工具调用时 `return`；用完次数仍未结束时，发送 `Event("status", {"text": "已达到轮次上限", "limit": True})`。

保存后检查自己写的循环：

```bash
uv run python -m lesson_01_agent.check 5
# 单独检查“没有工具请求就结束”与连续两轮消息保存：
uv run python -m lesson_01_agent.check chat
# 第 5 步也可以使用这个名字：
uv run python -m lesson_01_agent.check loop
```

这一步会检查工具结果是否送回模型、多工具请求是否全部执行、参数错误和工具异常是否送回、轮数上限是否生效，以及停止是否能退出。可以让 Chat 调用 `check_agent`，读取失败原因后陪你修改。

**只填四个辅助函数会显示 4/5，不能切换到“我的 Agent”。** 第 5 步和聊天检查也通过后，下一轮才会执行你们共同实现的 Agent loop。

最后检查全部内容：

```bash
uv run python -m lesson_01_agent.check
```

出现“待完成：TODO 1.x”表示对应函数还没填完；出现“检查未通过”则按提示核对该函数。两种情况都可以修改、保存后重新运行同一条命令，不需要重新安装依赖。

## 6. 跟着消息历史走一遍循环

把这张表与 `run_turn()` 对照，确认你能解释每次追加的内容：

| 时刻 | `messages` 中依次有哪些角色 |
| --- | --- |
| 用户刚提问 | `system → user` |
| 模型要求调用计算器 | `system → user → assistant`（内含 `tool_calls`） |
| 计算器执行完 | `system → user → assistant → tool`（对应 `tool_call_id`） |
| 模型看到结果并回答 | `system → user → assistant → tool → assistant` |
| 用户继续追问 | 保留以上内容，再追加一条 `user` |

工具结果必须放在提出该请求的 `assistant` 消息后面；同一回复中有多个工具请求时，所有结果都写回后再问模型。在自己写的循环里保持这个顺序，每个辅助函数只负责自己的事情。

想一想：

1. 删除工具结果那条消息，第二次请求模型时会少什么信息？
2. 每次都清空 `messages`，用户的第二句话还能接着聊吗？
3. 工具报错为什么也要交给模型？
4. 如果模型一直要求调用工具，哪一行代码会让它停止？

## 7. 在网页里运行自己的 Agent

如果前面还没有打开网页，在项目根目录启动：

```bash
uv run mini-agent --lesson 1 --open
```

1. 在左下角设置中填写 Base URL、API Key，保存后拉取模型，搜索并添加。
2. 点击“测试 LLM”确认接口连接。这个按钮直接调用已提供的客户端，**不检查你写的辅助函数和循环**。
3. 确认顶部为“我的 Agent”，然后新建对话，普通发送“你好”，然后追问“我上一句说了什么”。
4. 新建对话，发送“请使用 calculate 工具计算 6 × 7，再告诉我结果”。
5. 看右侧是否出现工具调用、返回结果和模型最终回复。模型口头说“我调用了工具”不能代替实际记录。

真实模型调用可能产生 API 费用。计算与时间查询适合起步；`bash` 会执行真实本机命令，A5 的文件编辑工具修改每轮的练习副本。

如果顶部还是“教学 Chat”，展开检查结果，继续让 Chat 读取、讨论并用已接通的 Edit 修改未完成的函数。

聊天和计算跑通后，再做 [作业说明](../docs/student/ASSIGNMENT.md) 中的 A1—A5 模型比较。更多接口细节在 [接口契约](../docs/student/CONTRACT.md)，第一遍可以先不读。

## 下一课

第二课 [Computer Use](../lesson_02_computer_use/README.md) 保留同一套函数与循环，提供辅助函数与 `run_turn()` 的标准实现，只需要再接入 Cua 工具。也可以把自己完成的 `agent.py` 带过去；图片和错误处理的现成代码请保留。
