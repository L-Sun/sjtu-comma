# Lesson 01 · 用 Python 拼出一个 Agent

你已经会写 Python 的函数、列表、字典和 `for` 循环，就可以开始这一课。不需要有 Web、网络接口或大型项目的开发经验。

本课的目标是：**让模型提出工具调用，由 Python 执行工具，再把结果交给模型，直到模型给出回答。**

你要和教学 Chat 一起完成 [agent.py](agent.py) 中的 **6 个辅助函数，以及第 7 步 `run_turn()`：真正的 Agent loop**。函数名称和参数固定，循环体由你们一起实现。模型接口、工具、网页和图片转换已提供，不需要自己设计工程框架。

## 先打开 Chat，边问边写

不用等 Agent loop 写完。现在就在项目根目录运行：

```bash
uv run mini-agent --lesson 1 --open
```

在网页左下角设置 Base URL、API Key 和模型。顶部显示 **教学 Chat · 0/7**，说明当前使用的是课程提供的助教。它已经能调用三个工具：

| 工具 | 能帮你做什么 | 可以直接发的消息 |
| --- | --- | --- |
| `list_files` | 列出目录里的文件，确认路径 | “列出课程根目录和 lesson_01_agent 里的文件。” |
| `read_course_file` | 读取你最新保存的代码和讲义 | “读 agent.py 和 README，解释第一个函数，给我可以粘贴的代码。” |
| `check_agent` | 用假模型、假工具检查辅助函数与你写的循环 | “我保存好了，检查一下，还差哪一步？” |

按这个节奏完成作业：

1. 让 Chat 列文件、读代码，再一起讨论当前函数。
2. Chat 返回完整函数和粘贴位置。你在编辑器中替换对应函数，保存 `lesson_01_agent/agent.py`。
3. 网页自动检查已保存的版本，也可以点击“检查我的代码”或让 Chat 调用 `check_agent`。
4. 看逐项结果，修复一个函数，再继续下一个。下面的讲义解释每一步为什么这样写。
5. 六个辅助函数、你实现的 `run_turn()` 和两轮聊天全部通过后，顶部变为 **我的 Agent**。**下一条消息开始真正执行你保存的 `run_turn()`**，继续使用这段对话。
6. 对它说：“调用 check_agent 检查你自己，再使用 calculate 计算 6×7。”从右侧记录确认它真的执行了工具。

教学 Chat 只列文件、读文件和运行检查，不会替你改作业；你要亲自粘贴和保存。普通对话依然会使用真实模型接口，检查器本身不产生 API 费用。

**第一课修改 `agent.py` 后不需要重启服务。** 检查和加载使用同一个已保存的代码版本；正在执行的回合不切换实现。通过检查只代表基础行为符合要求，还要观察真实模型是否正确使用工具。后续修改有语法错误、未完成步骤或检查超时，会回到教学 Chat 帮你修复。修改公共框架或第二课代码仍需重启。

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

`context.emit(...)` 负责让网页显示进度，已在固定流程中写好，本课无需实现。

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

先在 `agent.py` 中找到 `run_turn()` 的 TODO。这张图是实现指引，**它描述了你和 Chat 要写出来的流程，不是已经提供的代码**：

```text
用户发来一条消息
        │
        ▼
add_user_message()             TODO 1：准备消息
        │
        ▼
┌─→ ask_model()                TODO 2：问模型
│       │
│       ▼
│   remember_assistant_message()  TODO 3：存下完整回复
│       │
│       ├─ 没有 tool_calls → 结束本轮
│       │
│       └─ 有 tool_calls → 逐个处理：
│               parse_tool_arguments()  TODO 4：把参数变成字典
│               execute_tool()          TODO 5：真正执行工具
│               make_tool_message()     TODO 6：把结果包装成消息
│               messages.append(...)    第 7 步：自己放回历史
│       │
└───────┘  带着新结果，再问一次模型
```

在你要写的 `run_turn()` 中，用外层 `for` 控制模型请求次数，内层的 `for` 处理这一条回复中提出的所有工具调用。**不是执行完一个工具就结束，也不是有回复文字就一定结束：判断条件是 `reply.tool_calls` 是否为空。**

你还要在循环中实现两个结束条件：模型没有请求工具，或达到轮数上限。工具报错要交回模型，停止信号则要向外传递。第 7 步会指导你和 Chat 一起完成这些分支。

## 4. 只需要知道的 `async` / `await`

模型请求和工具执行可能要等待，因此它们是异步函数。本课只需要按现成写法调用：

```python
async def some_function(...):
    result = await another_function(...)
    return result
```

`await` 表示等这次调用完成，再把结果赋给 `result`。少写它，得到的就不是实际结果。

`ask_model()`、`execute_tool()` 和 `run_turn()` 使用 `async def`，内部调用时要写 `await`。保留函数定义即可；不需要自己写 `asyncio.run()`、线程或并发逻辑。

函数定义中的 `: str`、`: dict`、`-> None` 等是类型提示，分别告诉你参数和返回值是什么。`-> None` 表示只修改列表，不需要返回东西。

## 5. 按顺序填写，每一步都可以单独检查

第一次使用，在**项目根目录**打开终端，即能看到 `pyproject.toml`、`common/` 和 `lesson_01_agent/` 的目录，运行：

```bash
uv sync --python 3.12
```

`uv` 的安装入口见 [项目 README](../README.md#启动)。后面的检查全部使用固定回复的假模型和假工具，**不需要 API Key、不联网、不执行本机命令，也不会产生 API 费用**。

每个函数里目前有一行 `raise ExercisePending(...)`。它表示“这一步还没有完成”。填写自己的代码时，删除或替换该行；保留函数名和参数。

### 第 1 步：`add_user_message()`

需要做两件事：

1. 如果 `messages` 是空列表，先追加一条 `system` 消息，内容使用 `system_prompt`。
2. 不论列表原来是否为空，都追加一条 `user` 消息，内容使用 `user_text`。

直接修改传入的列表，不需要 `return`。你会用到 `if not messages` 和 `list.append()`。

```bash
uv run python -m lesson_01_agent.check 1
```

检查器会测试空历史，以及已有历史时是否正确追加消息。

### 第 2 步：`ask_model()`

调用提供好的 `context.complete`，三个参数按顺序传入：`messages`、`context.tools`、`context.config`。等待调用完成，并返回它给你的 `ModelReply`。

这里只问一次模型，不要自己再写循环；你将在 `run_turn()` 中实现重复调用。

```bash
uv run python -m lesson_01_agent.check 2
```

### 第 3 步：`remember_assistant_message()`

把 `reply.message` 整条追加到 `messages`，无需返回值。

不要自己用 `reply.text` 重建一条消息。模型可能在同一个消息中放入 `tool_calls` 和其他需要保留的字段，丢掉它们会影响后续对话。

```bash
uv run python -m lesson_01_agent.check 3
```

前三个辅助函数写好后，还需要在 `run_turn()` 中把这些函数接起来，才能通过 `chat` 检查。继续完成工具相关函数，再在第 7 步把它们接成循环。普通聊天只是这个循环的无工具分支，教学 Chat 从一开始就可以使用。

### 第 4 步：`parse_tool_arguments()`

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
uv run python -m lesson_01_agent.check 4
```

### 第 5 步：`execute_tool()`

调用 `context.execute(name, arguments)`，等待完成后返回原来的 `ToolResult`。

工具名和参数是模型刚刚给出的。不要把函数限定为 `calculate`，也不要自己在这里写乘法；同一个函数随后还会执行时间查询、文件搜索等工具。

```bash
uv run python -m lesson_01_agent.check 5
```

### 第 6 步：`make_tool_message()`

工具结果不能只显示在网页上，还需要交给模型。返回一条有三个键的消息：

| 键 | 应填什么 |
| --- | --- |
| `role` | 固定为 `"tool"` |
| `tool_call_id` | 参数 `call_id`，原样保留 |
| `content` | 将 `{"is_error": result.is_error, "text": result.text}` 转为 JSON 字符串 |

转换字典为字符串使用 `json.dumps(..., ensure_ascii=False)`；`ensure_ascii=False` 让中文保持可读。它与第 4 步的 `json.loads()` 方向相反。

`tool_call_id` 把工具结果和原来的请求对应起来。请求叫 `call-1`，结果就要写 `call-1`，不要写成工具名 `calculate`。

成功与失败的结果都要返回。你写的 `run_turn()` 要把这条消息追加到历史；这个函数只负责创建并返回字典。

```bash
uv run python -m lesson_01_agent.check 6
```

### 第 7 步：和 Chat 一起实现 `run_turn()`

**Agent loop 就在这个函数里，这部分也属于作业。** 不要只完成前六个函数。函数中的 `raise ExercisePending(...)` 需要替换成你们共同写出的循环。

先对 Chat 说：

> 请读取 agent.py 中的 run_turn 和 README 第 7 步。和我一起推演“计算6×7”时，模型如何请求工具、工具结果如何回传、模型如何再回答。然后根据这个过程一起写循环，解释每个 for、if、return 的位置，保存后帮我检查。

#### 围绕工具调用，实现一个完整循环

直接实现 Agent loop。普通聊天对应其中的一个分支：模型没有提出工具请求，就显示回复并结束；不用另外写一个聊天程序，也不用先完成一个聊天阶段。

先讨论：为什么只问一次模型不够？工具返回结果后，谁来决定是否继续？用下面的伪代码作为思路，不要直接当作 Python 粘贴：

```text
把本轮用户输入放进历史（只做一次）
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
uv run python -m lesson_01_agent.check 7
# 单独检查“没有工具请求就结束”与连续两轮消息保存：
uv run python -m lesson_01_agent.check chat
# 第 7 步也可以使用这个名字：
uv run python -m lesson_01_agent.check loop
```

这一步会检查工具结果是否送回模型、多工具请求是否全部执行、参数错误和工具异常是否送回、轮数上限是否生效，以及停止是否能退出。可以让 Chat 调用 `check_agent`，读取失败原因后陪你修改。

**只填六个辅助函数会显示 6/7，不能切换到“我的 Agent”。** 第 7 步和聊天检查也通过后，下一轮才会执行你们共同实现的 Agent loop。

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

如果顶部还是“教学 Chat”，展开检查结果，先补齐未通过的函数；当前仍可让 Chat 读取代码、返回实现建议。

聊天和计算跑通后，再做 [作业说明](../docs/student/ASSIGNMENT.md) 中的 A1—A5 模型比较。更多接口细节在 [接口契约](../docs/student/CONTRACT.md)，第一遍可以先不读。

## 下一课

第二课 [Computer Use](../lesson_02_computer_use/README.md) 保留同一套函数与循环，提供辅助函数与 `run_turn()` 的标准实现，只需要再接入 Cua 工具。也可以把自己完成的 `agent.py` 带过去；图片和错误处理的现成代码请保留。
