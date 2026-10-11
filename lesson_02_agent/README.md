# Lesson 02 · Agent 与工具循环

目标：连接模型、历史消息和工具，让 Agent 根据结果继续行动。

## 文件与任务

- `llm.py`：Lesson 01 的标准答案，已完成，可直接使用。
- `agent.py`：本阶段作业，实现 `run_turn()`；保留多轮历史，配对工具调用与结果，处理失败、取消和轮次上限。

Web、实时步骤和工具由 `common/` 提供。此阶段开放对话与工具调用；可运行 A4 工具顺序、A5 长文件编辑，以及 `bash` 本机命令实验。无需自己写 Web、shell 或文件编辑器。

## 运行

在项目根目录：

```bash
uv run mini-agent --lesson 2 --open
uv run python scripts/check_student.py agent --lesson 2
```

在本目录：`uv run --project .. mini-agent --lesson 2 --open`。

「测试 LLM」可以验证已有的 LLM 实现；正常发送会走待实现的 Agent 循环。尚未完成时出现 TODO 2。命令工具会真实操作本机；A5 只修改每轮创建的文件副本。

接口与事件契约见根目录 `docs/student/CONTRACT.md`。工具失败后应将错误交给模型继续处理，不得伪装成功。

## 下一阶段

`lesson_03_computer_use/llm.py` 和 `agent.py` 包含前两阶段标准答案。后续只需专注 Cua 接入。
