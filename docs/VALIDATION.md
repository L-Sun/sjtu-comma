# 当前 Web 与分阶段目录验收（2026-10-11）

后续调整：移除阶段选择器及会话 API 的 mode 参数。能力由 lesson 累加：第一课 LLM，第二课加入工具，第三课保留工具并加入 Cua。Cua 未完成时保留前置能力并显示明确提示。54项回归通过；额外验证了真实 Driver 连接清理后已有工具仍可运行，Edge 中切题不会切换能力。当前截图为 `artifacts/web-lessons-only.jpg`。

当前实现已迁移为 Starlette/Uvicorn 本机 HTTP 服务与原生 HTML/CSS/JS 工作台，Textual 及教师模式入口已移除。下方旧 TUI 测试是历史证据，不代表当前界面。

- `uv run pytest -q`：51项通过，覆盖分阶段模块加载、当前 TODO、独立前置答案、HTTP 会话、SSE 实时 pending/完成事件、重连快照、取消、历史只读、下载、参数验证与本机访问限制，以及原有工具/编辑/观察策略回归。
- `uv run python scripts/check_student.py agent --lesson 3` 通过：第三课携带的 Agent 标准实现完成工具循环。
- Edge 实际验证：发送、实时步骤、模型与任务切换、新会话、深浅主题、记录下载、刷新恢复、只读历史及截图弹窗；实际中断了正在执行的 sleep 30，并显示已停止；390×844布局无横向溢出。截图：`artifacts/web-edit-dark.jpg`、`web-edit-light.jpg`、`web-mobile.jpg`。
- 真实 Web + GPT‑3.5 调用一次本机 bash：打印 `COMMA_WEB_OK`，退出码0。
- 重组为 lesson 目录后，通过 Edge 第三课调用 GPT‑5.6 Sol 执行 A5：run `20261011T030847-519c5a74`，17.0秒、11次工具调用、0次工具错误、三处一次写入、8/8验收通过。运行经浏览器 → HTTP → 第三课 LLM/Agent → 公共工具 → SSE 返回界面。
- `uv build` 成功；wheel 包含静态资源、5,000行基线与三个 lesson。学生 ZIP 包含70个文件（前置标准答案有意提供），不含 `.env`、密钥、运行记录或当前 Cua 作业的测试辅助答案。
- Web迁移没有重新运行本机 Cua 桌面操作；此前的原生画布点击兼容性问题仍见下方。Windows/Linux仍未进行原生系统端到端验收。

## 历史 TUI 与模型实验记录

# 验收记录 · 2026-10-11

环境：macOS 26.6.2，Python 3.12，Cua Driver 0.34.0，OpenRouter 真实 API。Agent 界面为 Textual Terminal UI；电脑操作发生在本机。Windows 安装路径已提供，但未进行 Windows 实机验收。

## 框架检查

- `uv run pytest -q`：28 项通过。覆盖 TUI 三阶段、停止/超时、新对话、模型切换、记录导出、小窗口布局、三种观察隔离、工具批次与图片历史、长文件搜索/分段读取、批量补丁原子写入、版本冲突、误改/漏改检测与模型参数兼容。
- 通过 PTY 启动真实 Terminal UI 演示版，输入消息、收到回复并正常退出。真实模型流程通过 Textual Pilot 点击发送按钮，经过完整 TUI、Runtime 和参考 Agent。
- 「单独测试 LLM」真实请求通过，记录 `20261011T021740-7b75c87d`。
- 学生发布包保留三个 TODO，不包含 instructor、教师测试答案、`.env` 或 API Key；包含教师预定义的 Edit 工具。

## 指令遵循与多轮聊天

| 模型 | 精确 JSON | 多重约束 | 引用指令 | 两步工具 | 多轮记忆 |
| --- | --- | --- | --- | --- | --- |
| google/gemini-2.5-flash | 失败：多加 Markdown 代码围栏 | 通过 | 通过 | 通过 | 通过 |
| google/gemini-3.8-flash | 通过 | 通过 | 通过 | 通过 | 通过 |

## 当前：5,000 行长文件与 GPT 端到端验收

样例为 `core/fixtures/course_page.py`，CourseA/B/C 均有同名方法。只改 B 的第1808、2060、3100行标识符；其他字节不变。目标是分别验收接口调用链与修改正确性，两者不混淆。

| 模型 | API与工具循环 | edit尝试 | 文件写入 | 工具次数 | 耗时 | 代码验收 |
| --- | --- | --- | --- | --- | --- | --- |
| openai/gpt-3.5-turbo | 通过 | 是 | 否 | 23 | 34.0s | 3/8 |
| openai/gpt-5.6-sol | 通过 | 是 | 是 | 11 | 17.0s | 8/8 |

GPT‑3.5 Turbo 共尝试7次 edit；因旧文本不唯一或未精确匹配（包括换行转义问题）被工具拒绝。每次错误均回传模型，最终正常回复；没有异常崩溃。3/8 是未修改基线的语法与 A/C 不变检查得分，**不表示完成了部分编辑**。

GPT‑5.6 Sol 先前因请求包含不支持的 temperature 参数而 HTTP404，记录为 `20261011T023556-ceb782c1`。修复客户端参数兼容后，模型搜索、分段读取，一次 edit 提交三处替换，再读取确认，8/8通过。修复前失败没有删除。新请求未设置 temperature；GPT‑3.5 请求使用 temperature=0。

- [GPT‑3.5 完整记录](../runs/20261011T023522-ccef44cb/run.json)
- [GPT‑5.6 完整记录](../runs/20261011T023657-8264076d/run.json)
- [GPT‑5.6 修改后的5,000行文件](../runs/20261011T023657-8264076d/code/course_page.py)
- [首次双模型验收](../artifacts/live-long-edit-20261011T023521.json)
- [修复后的 GPT‑5.6 验收](../artifacts/live-long-edit-20261011T023657.json)

两个模型均经 Textual Pilot 点击发送，经过 TUI → Runtime → 真实 OpenRouter → 参考 Agent → 本机文件工具 → 结果回传 → 最终回复。max_rounds=24，max_tokens=2048。不是仅调用一次 API 的烟雾测试。

开发过程中也对两代 Gemini 运行了新长文件题：2.5 达到循环上限，3.8通过8/8。历史短函数题的8/8结果不代表长文件题结果。

## 历史：短函数 Edit 题（现已被长文件题替换）

每个模型均从同一份缺陷文件开始，执行 read_file → edit → read_file。下面的分数来自修改后的文件实际执行结果，未使用模型自报。

| 模型 | 测试 | 耗时 | 工具调用 | 记录 |
| --- | --- | --- | --- | --- |
| google/gemini-2.5-flash | 8/8 | 6.3s | 3 | [20261011T022109-6004e610](../runs/20261011T022109-6004e610/run.json) |
| google/gemini-3.8-flash | 8/8 | 16.5s | 3 | [20261011T022116-bc431d19](../runs/20261011T022116-bc431d19/run.json) |

每轮 `baseline.py` 保存初始代码，`code/normalize_tags.py` 保存最终代码，编辑 diff 在 `run.json` 的工具结果中。

## 本机 Computer Use

计算器统一清零并独立确认初始显示为 0，再固定模型 google/gemini-3.8-flash 比较观察模式。

| 模式 | 实际显示 | 状态 | 截图数 | 记录 |
| --- | --- | --- | --- | --- |
| vision | 4736 | 通过 | 2 | [20261011T021612-bdc6c7b5](../runs/20261011T021612-bdc6c7b5/run.json) |
| tree | 4736 | 通过 | 0 | [20261011T021656-a52c91ce](../runs/20261011T021656-a52c91ce/run.json) |
| hybrid | 0 | 失败：模型输出达到 token 上限 | 1 | [20261011T021806-6ea0906f](../runs/20261011T021806-6ea0906f/run.json) |

混合模式也曾在前轮得到 4,736；最后一次清零复测触发输出长度上限，框架将其标记为错误，不执行可能截断的调用。所有失败保留。

修复过验收脚本缺陷：macOS 计算器的第一个 AXStaticText 是算式，第二个才是结果。早期 `12837` 的失败判定无效，不应用于模型比较。已增加回归用例，并在修复后重新测试三种模式。旧记录在 `artifacts/live-results-second-invalid-verifier.json` 中保留，仅供调试。

## 本机浏览器练习

| 任务 | 观察模式 | 独立判定 | 耗时 |
| --- | --- | --- | --- |
| form | hybrid | 通过 | 145.6s |
| canvas | vision | 失败 | 157.9s |

表单由原生 Cua 完成，服务器状态为 `form_success=true`。画布原生 Cua 像素点击未触发页面反馈，模型如实报告未成功，服务器状态为 `canvas_success=false`。单独复现时 Driver 返回 `effect=unverifiable`；现已在工具结果中保留这种操作反馈。

为了排除练习页本身失效，另用独立浏览器控制器点击橙色圆形，页面出现“成功：已选中橙色圆形”。这个辅助检查**不算作 Agent / Cua 实验成功**。当前环境仍存在原生像素点击的兼容性问题，开课前需在学生操作系统与浏览器上预跑。

![独立浏览器检查后的成功反馈](../artifacts/practice-independent-check.png)

## 解释边界

这些是框架验收样本，不是完整模型评测。没有把失败删除后只报告成功。课堂要求学生按作业说明重复实验并报告所有试次；纯视觉/树/混合同时改变了信息和动作寻址方式，不是严格的输入单变量消融。


## 实时简化 Trace 界面

界面改为事件驱动的动作摘要：开始时显示进行中，结束时原位更新结果；保留执行顺序并标记相同参数的重复调用。原始 JSON 和代码 diff 继续保存在 run.json，不展示在默认 trace 中。Ctrl+T 可放大/还原面板。

验证结果：33 项回归测试通过，包含实时更新、重复调用、乱序返回、停止后的未知执行效果、编辑失败、电脑动作未验证的提示及清空界面。离线回放 GPT-3.5 实际记录 20261011T023522-ccef44cb，确认显示 23 次调用、7 次工具错误、最终验收未通过；此次界面验证没有重新调用付费模型。检查了 140×48 和 80×24 终端布局及紧凑模式的放大面板，输入与操作按钮可见。

预览保存在 artifacts/trace-gpt35-first-failures.svg.png、artifacts/trace-gpt35-complete.svg.png 和 artifacts/trace-compact.svg.png。SVG 导出预览已修正宽字符 textLength，避免中文被 Rich 的 SVG 字符计数压缩；不影响实际终端绘制。


## 跨平台 Bash 工具

新增统一 bash function tool，macOS 选择 zsh、Linux 选择 Bash、Windows 优先 pwsh 后备 powershell。Tools 阶段启用，A5 默认工作目录为当轮代码副本；Chat/Computer Use 不开放。支持目录参数、UTF-8 输出、退出码、超时、取消、每流16KiB输出上限；trace 显示命令摘要及结果，完整返回写入记录。

46 项回归测试通过，包含三平台 shell 选择和参数构造、PowerShell fallback/编码、环境与模型 API Key 脱敏、本机中文与双流输出、非零退出、输出上限、超时/取消的子进程清理、A5 默认目录、Agent 循环与真实 shell 集成。

另外通过真实 Textual TUI 调用 GPT-3.5 Turbo：run_id 为 20261011T025219-85ed0245，模型调用一次 bash，本机 zsh 打印 COMMA_SHELL_OK，exit_code=0，会话正常完成。证据为 artifacts/live-bash.json 和对应 run.json；并检查了 TUI 输出预览。Windows 和 Linux 仅验证 shell 分派及命令参数构造，尚未在对应原生系统执行；Windows 进程树清理需原生验收。
