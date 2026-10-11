# 公共框架

两个 lesson 共用这一目录，不需要把 Web 页面或工具实现复制到作业中。

- `app/main.py`：启动本机 HTTP 服务；`--lesson 1/2` 选择加载哪个目录。
- `app/server.py`：HTTP 接口、SSE 实时事件、静态资源与本机访问限制。
- `app/sessions.py`：会话生命周期、停止、历史记录恢复。
- `app/runtime.py`：接入当前课时的模块、注册工具、保存记录与验收。
- `app/trace.py`：把真实工具事件转换成简短步骤。
- `app/static/`：浏览器工作台、深浅主题、图标及 MIT 授权。
- `core/lesson_io.py`：提供网页事件、用量、工具错误转换与图片批次处理，不替学生实现循环。
- `core/llm.py`：已完成的 LLM 客户端，支持设置中的 Base URL、API Key 与模型，两节课共用。
- `core/`：消息类型、配置、题目、命令/编辑工具、Cua 观察策略及记录格式。

学生主要修改当前 lesson 的 TODO，不需要修改本目录。Computer Use 的观察模式由公共策略层强制执行；不要通过改策略绕过实验条件。

从项目根目录运行 `uv run mini-agent --lesson 1 --open`。每个 lesson 的 README 给出自己的目标和检查命令。

第一课预置助教在 `app/learning_chat.py`，初始使用 `core/learning_workspace.py` 的三个课程工具。学生完成 tools.py 的工具声明与执行分发后，`core/learning_edit.py` 检查并加载接入，才开放 Edit；底层读写、版本校验和备份由 `core/course_editor.py` 提供。检查器用独立进程和保存的源码快照运行；`core/student_loader.py` 加载通过检查的同一版本。教学 Chat 不导入未完成的作业，教学 Chat 每次只请求一次模型，结果保存后等待手动继续；学生 Agent 接手后才自动循环。

第一课仅三个教学阶段：Edit 接入、一起完成四个辅助函数、核心 Loop。Edit 保存后由 learning_workspace 在同一工具结果中附带离线 checks，不额外请求模型。学生只编写请求、工具遍历、结果回传和继续/结束的控制流程。
