# Lesson 02 · Computer Use

目标：把 Agent 的工具接到学生自己的 macOS / Windows 桌面，支持截图、可访问性树与混合观察。

## 文件与任务

- `common/core/llm.py`：教师提供的公共 LLM 客户端。
- `agent.py`：第一课四个辅助函数和 run_turn 的标准实现，保留可选的 `compact_history` 入口，接口与第一课一致。
- `tools.py`：已完成的工具声明与执行分发，接入通用文件搜索、读取和编辑；不依赖第一课作业是否完成。
- `cua.py`：本阶段作业；实现 MCP 工具列表转换与调用，完整保留文本、图片和错误。

LLM、Agent 与文件工具已完成，启动后即可使用对话、计算、时间查询、通用文件编辑和本机命令。框架自动尝试接入 Cua；未完成或驱动不可用时显示提示，并保留已有工具。没有阶段切换器。公共层负责 MCP 进程生命周期和观察模式隔离。

## 普通对话中的文件编辑

无需进入固定实验，直接告诉 Agent 要修改的文件和内容。例如：

> 读取 lesson_02_computer_use/cua.py 和 README，解释 MCP 工具声明与调用，并按我的要求用 edit 修改 cua.py。

文件工具适用于已有的 UTF-8 文本文件，包括 Python、Markdown、JSON 等，不限制为某几个课程文件。`path` 支持绝对路径、`~` 和相对于项目根目录的路径；最大文件大小为2MiB。操作会直接保存到该文件。需要创建文件时可使用已有的 `bash` 工具。

| 工具 | 用法 |
| --- | --- |
| `search_file(path, query, after_line=0)` | 搜索字面文本，返回带行号的上下文和版本，每页最多20处 |
| `read_file(path, start_line=1, end_line=...)` | 默认读取120行，最多160行；短文件自动读到末尾，`next_start_line` 表示后续页 |
| `edit(path, base_version, edits)` | 用读取结果的 `version`，提交1—12处 `{old_text, new_text}` 精确替换 |

编辑前先读取当前文件；原文不能带行号，必须唯一匹配且各处互不重叠。版本冲突或任一替换无效时整批不写入；成功返回新版本和 diff，保留文件的换行符和权限。不限定 Python 语法，也不自动执行作业检查；修改 Cua 后使用下方检查命令验证。

「长文件局部编辑」仍使用本轮的 `course_page.py` 实验副本和固定验收，文件工具在该实验中只访问这一副本。

`compact_history` 延续第一课的可选扩展，默认留空，不修改历史或额外请求模型；装饰器负责显示压缩进度。第二课仍只需完成 `cua.py`。

## 运行

在项目根目录：

```bash
uv run mini-agent --lesson 2 --open
uv run python scripts/check_student.py cua --lesson 2
```

在本目录：`uv run --project .. mini-agent --lesson 2 --open`。

先按根目录 README 安装并授权 Cua Driver，再在普通对话中给已打开的本机应用下达操作指令。固定实验只保留「长文件局部编辑」。

演示前确认应用初始状态，并选择适合的观察方式。电脑动作可能已经生效，即使点击停止也不会撤销；模型自报成功不能替代独立检查。

完成后提交操作记录、失败分析及浏览器工作台与目标应用同时可见的录屏。当前作业目录不含本阶段 Cua 标准答案。
