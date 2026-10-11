# Lesson 01 · 调用 LLM

目标：把一组消息发送到 OpenRouter，解析文本、用量和工具调用结构。

## 需要完成

只修改 `llm.py` 中的 `complete()`。消息、工具定义、返回类型见 `common/core/types.py`；遵循根目录 `docs/student/CONTRACT.md` 的接口契约。

此阶段由公共框架直接调用 LLM，不要求先实现 Agent。Web 中开放对话与 A1—A3 指令遵循实验。

## 运行

在项目根目录配置 `.env` 后：

```bash
uv sync --python 3.12
uv run mini-agent --lesson 1 --open
uv run python scripts/check_student.py llm --lesson 1
```

也可以在本目录执行 `uv run --project .. mini-agent --lesson 1 --open`。浏览器地址是 `http://127.0.0.1:8766`。尚未实现时显示 TODO 1，属于练习提示。

先确认简单文本可以返回，再比较两个模型的精确格式、多重约束和引用文本处理。保存运行记录，区分接口出错与模型没有遵循指令。

## 下一阶段

`lesson_02_agent/llm.py` 包含本阶段的标准实现。下一阶段可以直接使用它，也可以把自己已验证的实现带过去。
