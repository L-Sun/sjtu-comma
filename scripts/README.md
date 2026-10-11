# 辅助脚本

从项目根目录用 `uv run python scripts/<脚本>.py` 运行。

- `check_student.py llm|agent|cua --lesson N`：只检查指定课时模块；LLM 会调用真实 API，Agent 使用假模型，Cua 只读查询窗口。
- `build_edit_fixture.py`：确定性生成5,000行长文件编辑基线。
- `export_student.py`：按白名单构建课程发布包，包含前置标准答案但排除密钥、运行记录及 Cua 测试辅助实现。
- `live_edit_verify.py`：经 HTTP 接口验证真实模型调用链，会产生 API 费用；使用第二课已提供的 LLM/Agent。

`web_client.py` 是验收脚本共用的 HTTP 客户端，不是另一种产品模式。浏览器交互单独验收。

第一课支持逐步离线检查：`uv run python -m lesson_01_agent.check 1`（数字可换为1—6），`chat` 检查前三步聊天，`loop` 检查完整循环，省略参数检查全部。无需模型 Key，不调用网络或本机命令。
