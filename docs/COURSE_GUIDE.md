# 课程运行与发布

```bash
uv sync --python 3.12
uv run mini-agent --lesson 2 --open
uv run pytest -q
uv run python scripts/live_edit_verify.py --model openai/gpt-3.5-turbo --model openai/gpt-5.6-sol
uv run python scripts/export_student.py
```

没有独立教师模式。LLM 客户端在公共框架直接提供；两个 lesson 分别保留 Agent 和 Cua 作业。第二课已提供 Agent 标准实现，可直接验收工具链；Cua 仍需完成。发布使用 `dist/comma-mini-agent-student.zip`。

学生包采用显式白名单：包含 common、两个 lesson、各课前置标准答案、文档、检查器和依赖锁。排除 `.env`、当前 Cua 练习的测试辅助实现、真实运行记录与缓存。

默认模型为 `openai/gpt-6.1-sol`，模型列表还保留两代 Gemini Flash。真实 API 可用性需每次开课前预跑；这些是代际样本，不代表所有老、新模型。

固定实验仅保留「长文件局部编辑」，两个课时一致。Computer Use 能力仍可在普通对话中使用，不再附带计算器、表单或画布实验。

运行时中断会清空模型历史，防止遗留未配对的 tool_call；学生模块需协作式响应取消。已经执行的桌面动作不会回滚。

各课提供的前置标准答案是用于验证框架的最小实现，未加入长对话压缩或重试优化。这样模型对比共享相同框架行为。

「长文件局部编辑」的 `search_file`/`read_file`/`edit` 是教师提供的普通 function tools，和学生 Agent 循环解耦。每轮保存 `baseline.py`、`code/course_page.py`、编辑 diff 和验收结果。原始合成文件为5,000行，可用 `scripts/build_edit_fixture.py` 确定性重建。B 的三处目标在1808、2060、3100行，A/C和文档文字提供同名干扰。

批量补丁全部匹配同一版本并互不重叠后，通过同目录临时文件与 `os.replace` 原子回写；不会把一半工具参数或一半补丁写进长文件。模型修改后的代码先做静态和逐字节检查，只有与教师已知三处改名完全一致才执行页面方法，避免执行任意生成代码。

`live_edit_verify.py` 将 API 接通、工具循环完成、编辑尝试、文件写入与代码正确性分开记录；不要求模型改对才能算接口接入完成。Web 工作台 当前实时显示简化的工具步骤与结果，原始参数和实际 diff 保留在 run.json；未实现模型 token 级流式输出。摘要由 common/app/trace.py 按事件确定性生成，不增加 API 请求，不推断隐藏思考。

GPT‑5.6 在此次 OpenRouter 目录中带有 Sol/Terra/Luna 后缀；本次验收明确使用 `openai/gpt-5.6-sol`。它不接受 `temperature` 参数；参考客户端根据模型目录省略不支持的可选参数，记录真正发送的配置。不要将该条件描述成与 GPT‑3.5 相同温度的严格对照。


## 跨平台命令工具

`common/core/shell_tools.py` 提供统一 `bash` function tool：macOS 用 zsh、Linux 用 Bash、Windows 用 PowerShell 7 或 Windows PowerShell。从 Lesson 01 起自动注册，Lesson 02 继续保留，包括「长文件局部编辑」（默认进入本轮副本目录）。不依赖用户默认登录 shell 或 Windows 上的 WSL；模型从工具 description 获取实际环境。

命令在本机当前用户权限下执行，允许 cwd 指向其他目录，不是安全沙箱。环境变量只传基础运行所需项目，避免直接继承 API Key；文件系统仍然可访问。超时/取消时清理 POSIX 进程组，Windows 用 taskkill 清理进程树；脱离进程组的服务不保证回收。任务若需常驻服务应由教师另外启动。原始 stdout/stderr 保存在 run.json，默认 trace 只显示摘要、退出码和错误。

验收脚本经 Web 使用的 HTTP API 发送任务与导出结果，不声称这些脚本完成了浏览器点击验收。

## 第一课授课节奏

面向有 Python 基础、没有工程经验的学生，只分三个阶段：

1. 接入 Edit：学生与 Chat 一起声明工具、连接执行，初次接入手动保存。
2. 一起完成四个辅助函数：沿消息数据流说明，一批编辑，不逐函数拆成多轮。
3. 实现核心 Loop：学生写请求模型、遍历工具、回传结果和继续/结束条件；保留提供的消息准备与 lesson_io。

教学 Chat 仍然每次只请求一次模型，工具返回后由学生点击继续。Edit 保存后直接返回离线 checks，失败时汇总循环多个分支的问题；避免额外的“现在检查一下”回合。lesson_io 负责网页事件、用量、错误转换、取消传播和图片，不增加模型调用，也不会代替学生执行循环。全部通过后下一轮加载学生自己的 Agent，再进入模型比较实验。第二课提供同一套标准循环，仅接入 Cua。
