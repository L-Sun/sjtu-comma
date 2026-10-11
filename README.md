# COMMA · Mini Agent Lab

从 Agent 工具循环到本机 Computer Use 的两个递进练习。**LLM 客户端直接提供**，学生专注 Agent 与电脑操作。使用本机 HTTP 服务 + Web 工作台，不需要 Node.js，也没有教师模式。

## 项目结构

```text
common/                       公共 Web、运行时、工具、实验题与记录
  core/llm.py                 已完成的 LLM 客户端，两节课共用
lesson_01_agent/              先接入 Edit + 4 个辅助函数 + 学生实现 Agent loop
lesson_02_computer_use/       Agent 标准实现 + Cua 接入作业
docs/student/                作业说明与接口契约
scripts/                     检查器、练习页、验收与打包
tests/                       框架与标准实现回归测试
```

每个 lesson 都包含 README。第二课的 Agent 标准实现是独立代码副本，不依赖第一课是否完成。LLM 客户端由公共框架提供，不作为作业。

| 课时 | 当前作业 | 已提供 | 开放能力 |
| --- | --- | --- | --- |
| [01 · Agent](lesson_01_agent/README.md) | `tools.py` 接入 Edit；`agent.py` 实现辅助函数与 Loop | 函数接口、LLM 客户端、Web、基础工具 | 对话、A1—A5、bash |
| [02 · Computer Use](lesson_02_computer_use/README.md) | `cua.py` | 以上内容、同目录 `agent.py` 标准实现 | 第一课能力 + 本机电脑操作 |

只需要 Python 基础即可开始第一课：[和 Chat 一起实现函数与 Agent loop](lesson_01_agent/README.md)。先与教学 Chat 完成 `tools.py` 的工具声明与执行分发；Edit 接通后，用它协助编辑后续作业。每个函数有单独的离线检查，全部通过后同一对话交给你自己的 Agent。函数接口和流程图已提供；学生与 Chat 直接实现 `run_turn()` 的“模型 → 工具 → 模型”循环，普通聊天是其中的退出分支。

## 启动

先安装 uv，用它管理本项目的 Python 环境和依赖。按操作系统选择一条安装命令，来源见 [uv 官方安装文档](https://docs.astral.sh/uv/getting-started/installation/)。

macOS / Linux，在终端运行：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Windows，在 PowerShell 运行：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

安装完成后关闭并重新打开终端，确认命令可用：

```bash
uv --version
```

进入项目根目录（包含 `pyproject.toml` 的目录），安装依赖并启动：

```bash
uv sync --python 3.12
uv run mini-agent --lesson 1 --open
```

启动后点击左下角齿轮，在设置面板填写 API Key 和 Base URL（默认 OpenRouter，也可使用 OpenAI 兼容接口）。也可以复制 `.env.example` 为 `.env` 手动配置。

浏览器地址 **http://127.0.0.1:8766**。`--lesson 1`、`--lesson 2` 切换课时，`--port` 更换端口，`--open` 自动打开浏览器。停止旧服务后再启动另一课时，或使用不同端口。默认第一课；作业尚未完成时使用教学 Chat，可列目录、读文件、讨论实现并检查代码。先手动保存 Edit 的接入代码；接通后 Chat 可以实际修改作业并检查。Loop 全部通过后下一轮切换到自己的 Agent，无需重启。「测试 LLM」直接使用已提供的客户端。

想先体验已完成的聊天、工具与代码编辑，可以直接启动第二课；该课只把 Cua 接入留空。终端按 Ctrl+C 停止服务。

```bash
uv run python scripts/check_student.py llm --lesson 1    # 真实 API，会产生费用
uv run python scripts/check_student.py agent --lesson 1  # 假模型，无费用
uv run python scripts/check_student.py cua --lesson 2    # 本机 Cua，只读检查
```

阅读 [接口契约](docs/student/CONTRACT.md)、[作业说明](docs/student/ASSIGNMENT.md) 和 [公共框架说明](common/README.md)。

## Web 工作台

能力由启动的 lesson 自动累加，页面没有阶段、能力或题目切换器。左侧「固定实验」列出当前课时的实验：第一课 A1—A5，第二课另有 B1—B3。点击实验会打开专属会话，并在输入框预填可编辑的提示词；A5 额外挂载本轮练习文件副本。

左侧是可搜索的固定实验和普通会话，中间是对话与模型设置，右侧「执行过程」实时展示工具动作、结果、错误和重复调用。只显示已发生的操作，不生成额外的模型思考摘要；完整参数与代码 diff 可导出。

Enter 发送，Shift+Enter 换行，点击方形按钮停止，⌘/Ctrl+K 新对话。顶部下载按钮导出运行记录；面板按钮展开/收起执行过程。支持深浅主题与窄屏抽屉。视觉参考 [still.fail](https://github.com/AFK-surf/still.fail)，图标 MIT 授权见 [第三方声明](THIRD_PARTY_NOTICES.md)。

点击左侧「会话记录」旁的「清空历史」，清理普通历史对话，保留全部固定实验、当前打开的对话及正在执行的任务。清理后的记录移入本机 `runs/.trash/`，重启后不会重新出现在列表；保留对话的消息、模型上下文和设置保持不变。

固定实验不会被清理。点击顶部「重置实验」会清空该实验的消息、模型上下文和执行过程，将运行记录移入 `runs/.trash/`，恢复原始提示词并保留当前模型与观察方式；重做前请先导出需要提交的记录。实验开始后如需换模型或观察方式，先重置再选择。重置不会撤销模型对本机文件或应用的操作；电脑实验仍需手动恢复应用初始状态。

刷新页面会重新连接当前会话，不重复执行。普通会话按稳定 ID 保存，多轮消息只占一个侧栏入口；服务重启后恢复问答、模型消息和工具结果，可以直接续聊。每轮运行仍独立留档，在执行过程下方“导出各轮记录”中下载。旧版缺少会话 ID 的逐轮记录保留在默认折叠的“旧版逐轮记录”中，无法自动恢复原会话归属与完整上下文。固定实验重启后仍需重置再做；普通会话切换模型或观察方式会新建会话。同一服务一次执行一个任务；切换会话不会自动停止正在运行的任务。

续聊保存的模型上下文会脱敏；先前截图替换为文字占位，原始观察图片仍在对应运行记录中。恢复后如需操作电脑，应重新观察。中断、取消或失败的回合保留可见消息，但不恢复可能不完整的工具调用上下文。

设置面板支持配置 Base URL 和 API Key：先保存接口配置，再点「拉取模型」，按名称或 ID 搜索、勾选后点「添加选中」，模型会立即加入对话顶部的菜单。配置保存到本机 `.env`（`OPENROUTER_BASE_URL`、`OPENROUTER_API_KEY`、`OPENROUTER_MODELS`），后续运行生效，重启保留。Base URL 需包含接口前缀（例如 `https://openrouter.ai/api/v1` 或本机服务的 `http://localhost:1234/v1`），列表和对话分别请求其 `/models` 与 `/chat/completions`。已有 Key 只显示“已配置”，不会回传浏览器，也不会写进 localStorage；留空保持原值。正在执行的任务继续使用启动时的配置。深浅主题和跟随系统也在设置面板中。服务只监听 `127.0.0.1`，接口限制本机 Host、拒绝跨站访问并校验写操作 token。它是本机课堂工具，不提供公网账户服务。

## 两组实验

**模型指令遵循与代码修改**：固定框架与题目，比较较早和较新的模型。初始模型列表包含 Gemini 2.5 Flash、Gemini 3.8 Flash 和 GPT‑6.1 Sol（`openai/gpt-6.1-sol`），可在设置中搜索并添加其他模型，也可通过 `.env` 的 `OPENROUTER_MODELS` 修改。已有 `.env` 中的模型列表优先于初始列表。名称可用性和费用以所配置的接口为准；两次实验不足以代表整体能力排序。

**Computer Use**：固定模型和任务，比较纯视觉、Accessibility Tree、混合模式。公共层强制限制输入信息和可用定位参数；每次比较前需手动恢复电脑应用状态。当前比较同时涉及观察信息与定位方式，不是严格的纯输入消融。

A5 的 [course_page.py](common/core/fixtures/course_page.py) 有5,000行。A/B/C 均有同名方法，只改课程 B 第1808、2060、3100行的定义和两处调用。框架提供 `search_file`、分段 `read_file`、`edit(path, base_version, edits)`；版本、唯一匹配和不重叠校验全部通过才原子写入，失败整批不改。

每轮重建独立副本，保存在 `runs/<run-id>/code/course_page.py`，不修改基线。验收三处改名、无关字节不变、语法与行为，共8项。只有与已知补丁一致的程序才运行行为检查。当前实时更新工具步骤，模型回复整条返回，不包含 token 级流式输出。

## 本机命令工具

Lesson 01 起自动提供 `bash(command, cwd?, timeout_seconds=30)`：macOS 使用 zsh，Linux 使用 Bash，Windows 使用 PowerShell 7（没有则使用 Windows PowerShell）。实际 shell 会写入工具说明，无需在 Windows 安装 Bash 或 WSL。

每次调用启动新的非交互进程；`cd` 和变量不延续到下次。默认目录是项目根目录，A5 默认本轮代码副本目录。返回退出码、stdout/stderr、耗时、超时与截断标记；每个输出流最多16KiB，超时最多120秒。

这是真实本机命令，按当前用户权限访问文件，不是沙箱。子进程不直接继承模型 API Key，但仍可访问文件。停止或超时清理 POSIX 进程组，Windows 用 `taskkill /T /F` 尝试清理进程树；脱离进程组的常驻服务不保证回收。Lesson 02 在保留这些工具的基础上加入 Cua。电脑观察实验要求模型仅用 Cua 操作目标窗口；验收需核对实际工具调用，不能把提示约束视为沙箱隔离。

## 本机 Cua

电脑操作发生在学生自己的 macOS / Windows 桌面，不需要 Linux 沙箱。按 [Cua Driver Quickstart](https://cua.ai/docs/cua-driver/quickstart) 安装；本项目验收使用0.34.0。

macOS：

```bash
/bin/bash -c "$(curl -fsSL https://cua.ai/driver/install.sh)"
open -n -g -a CuaDriver --args serve
cua-driver permissions grant
cua-driver permissions status
```

在系统设置授权辅助功能和屏幕录制。Windows 原生 PowerShell：

```powershell
irm https://cua.ai/driver/install.ps1 | iex
```

Python 与 Driver 应处于同一个登录桌面会话，不通过 WSL 控制 Windows 应用。必要时在 `.env` 设置 `CUA_DRIVER_COMMAND` 绝对路径。

先手动打开计算器再做 B1。B2/B3 另启动 `uv run python scripts/practice_server.py`，浏览器打开 `http://127.0.0.1:8765`；工作台仍在8766端口。

云端模型会收到目标窗口的截图或可访问性信息。停止不会撤销已完成的点击。电脑任务需独立核对应用状态，模型自报不能作为成功判据。

## 记录与检查

每轮自动保存 `runs/<run-id>/run.json` 和截图，包含模型、课时、题目、动作、耗时与用量；API Key 会被脱敏。提交录屏和记录前自行检查界面内容。

```bash
uv run pytest -q
uv run python scripts/export_student.py
```

发布包包含 `common/`、两个 lesson 及前置标准答案，不包含 `.env`、运行记录或当前 Cua 作业的测试辅助答案。开发工作区的验收说明见 [VALIDATION.md](docs/VALIDATION.md)（不放入学生包）。
