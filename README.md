# COMMA · Mini Agent Lab

从 LLM API、Agent 工具循环到本机 Computer Use 的三个递进练习。使用**本机 HTTP 服务 + Web 工作台**，不需要 Node.js，也没有教师模式。

## 项目结构

```text
common/                       公共 Web、运行时、工具、实验题与记录
lesson_01_llm/                 作业：LLM API 调用
lesson_02_agent/               LLM 标准答案 + Agent 循环作业
lesson_03_computer_use/        LLM/Agent 标准答案 + Cua 接入作业
docs/student/                 作业说明与接口契约
scripts/                      检查器、练习页、验收与打包
tests/                        框架与标准实现回归测试
```

每个 lesson 都包含 README。前置标准答案是实际代码副本，可以在当前目录阅读和修改；不会暗中引用上一课时的未完成作业。

| 阶段 | 当前作业 | 已提供的标准实现 | 开放能力 |
| --- | --- | --- | --- |
| [01 · LLM](lesson_01_llm/README.md) | `llm.py` | 公共 Web 和消息契约 | 对话、A1—A3 |
| [02 · Agent](lesson_02_agent/README.md) | `agent.py` | 同目录 `llm.py` | 对话、工具、A4/A5、bash |
| [03 · Computer Use](lesson_03_computer_use/README.md) | `cua.py` | 同目录 `llm.py`、`agent.py` | 前两阶段 + 本机电脑操作 |

## 启动

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，复制 `.env.example` 为 `.env` 并填写 OpenRouter Key。

```bash
uv sync --python 3.12
uv run mini-agent --lesson 1 --open
```

浏览器地址 **http://127.0.0.1:8766**。`--lesson 2`、`--lesson 3` 切换课时，`--port` 更换端口，`--open` 自动打开浏览器。停止旧服务后再启动另一课时，或使用不同端口。默认第一课；未补完时显示对应 TODO 提示。

想先体验已完成的聊天、工具与代码编辑，可以直接启动第三课；该课只把 Cua 接入留空。仅预览界面用 `uv run mini-agent --lesson 3 --demo --open`，模拟模式不调用模型或操作电脑。终端按 Ctrl+C 停止服务。

```bash
uv run python scripts/check_student.py llm --lesson 1    # 真实 API，会产生费用
uv run python scripts/check_student.py agent --lesson 2  # 假模型，无费用
uv run python scripts/check_student.py cua --lesson 3    # 本机 Cua，只读检查
```

阅读 [接口契约](docs/student/CONTRACT.md)、[作业说明](docs/student/ASSIGNMENT.md) 和 [公共框架说明](common/README.md)。

## Web 工作台

能力由启动的 lesson 自动累加，页面没有阶段或能力切换器。题目只选择实验内容，A5 额外挂载本轮练习文件副本。

左侧是可搜索的会话，中间是对话与模型/实验设置，右侧「执行过程」实时展示工具动作、结果、错误和重复调用。只显示已发生的操作，不生成额外的模型思考摘要；完整参数与代码 diff 可导出。

Enter 发送，Shift+Enter 换行，点击方形按钮停止，⌘/Ctrl+K 新对话。顶部下载按钮导出运行记录；面板按钮展开/收起执行过程。支持深浅主题与窄屏抽屉。视觉参考 [still.fail](https://github.com/AFK-surf/still.fail)，图标 MIT 授权见 [第三方声明](THIRD_PARTY_NOTICES.md)。

刷新页面会重新连接当前会话，不重复执行。服务重启后，磁盘记录显示为只读历史；可用相同设置新建。切换模型或观察方式会新建会话并保留旧会话。同一服务一次执行一个任务；切换会话不会自动停止正在运行的任务。

浏览器不接收 API Key，服务端从 `.env` 读取。服务只监听 `127.0.0.1`，接口限制本机 Host、拒绝跨站访问并校验写操作 token。它是本机课堂工具，不提供公网账户服务。

## 两组实验

**模型指令遵循与代码修改**：固定框架与题目，比较较早和较新的模型。默认提供 Gemini 2.5 Flash 与 Gemini 3.8 Flash，可通过 `.env` 的 `OPENROUTER_MODELS` 修改，例如 GPT‑3.5 Turbo 与 GPT‑5.6 Sol。名称可用性和费用以 OpenRouter 为准；两次实验不足以代表整体能力排序。

**Computer Use**：固定模型和任务，比较纯视觉、Accessibility Tree、混合模式。公共层强制限制输入信息和可用定位参数；每次比较前需手动恢复电脑应用状态。当前比较同时涉及观察信息与定位方式，不是严格的纯输入消融。

A5 的 [course_page.py](common/core/fixtures/course_page.py) 有5,000行。A/B/C 均有同名方法，只改课程 B 第1808、2060、3100行的定义和两处调用。框架提供 `search_file`、分段 `read_file`、`edit(path, base_version, edits)`；版本、唯一匹配和不重叠校验全部通过才原子写入，失败整批不改。

每轮重建独立副本，保存在 `runs/<run-id>/code/course_page.py`，不修改基线。验收三处改名、无关字节不变、语法与行为，共8项。只有与已知补丁一致的程序才运行行为检查。当前实时更新工具步骤，模型回复整条返回，不包含 token 级流式输出。

## 本机命令工具

Lesson 02 起自动提供 `bash(command, cwd?, timeout_seconds=30)`：macOS 使用 zsh，Linux 使用 Bash，Windows 使用 PowerShell 7（没有则使用 Windows PowerShell）。实际 shell 会写入工具说明，无需在 Windows 安装 Bash 或 WSL。

每次调用启动新的非交互进程；`cd` 和变量不延续到下次。默认目录是项目根目录，A5 默认本轮代码副本目录。返回退出码、stdout/stderr、耗时、超时与截断标记；每个输出流最多16KiB，超时最多120秒。

这是真实本机命令，按当前用户权限访问文件，不是沙箱。子进程不直接继承模型 API Key，但仍可访问文件。停止或超时清理 POSIX 进程组，Windows 用 `taskkill /T /F` 尝试清理进程树；脱离进程组的常驻服务不保证回收。Lesson 03 在保留这些工具的基础上加入 Cua。电脑观察实验要求模型仅用 Cua 操作目标窗口；验收需核对实际工具调用，不能把提示约束视为沙箱隔离。

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

发布包包含 `common/`、三个 lesson 及前置标准答案，不包含 `.env`、运行记录或当前 Cua 作业的测试辅助答案。开发工作区的验收说明见 [VALIDATION.md](docs/VALIDATION.md)（不放入学生包）。
