# Lesson 02 · Computer Use

目标：把 Agent 的工具接到学生自己的 macOS / Windows 桌面，比较截图、可访问性树与混合观察。

## 文件与任务

- `common/core/llm.py`：教师提供的公共 LLM 客户端。
- `agent.py`：第一课六个辅助函数和 run_turn 的标准实现，接口与第一课一致。
- `cua.py`：本阶段作业；实现 MCP 工具列表转换与调用，完整保留文本、图片和错误。

LLM 与 Agent 已完成，启动后即可使用对话、计算、长文件编辑和本机命令。框架自动尝试接入 Cua；未完成或驱动不可用时显示提示，并保留已有工具。没有阶段切换器。公共层负责 MCP 进程生命周期和观察模式隔离。

## 运行

在项目根目录：

```bash
uv run mini-agent --lesson 2 --open
uv run python scripts/check_student.py cua --lesson 2
```

在本目录：`uv run --project .. mini-agent --lesson 2 --open`。

先按根目录 README 安装并授权 Cua Driver，打开计算器，再运行 B1。B2/B3 需要另外启动 `uv run python scripts/practice_server.py`，在浏览器打开 `http://127.0.0.1:8765`。

每次比较前恢复应用初始状态，固定模型和任务，仅切换观察方式。电脑动作可能已经生效，即使点击停止也不会撤销；模型自报成功不能替代独立检查。

完成后提交三种观察方式的记录、失败分析及浏览器工作台与目标应用同时可见的录屏。当前作业目录不含本阶段 Cua 标准答案。
