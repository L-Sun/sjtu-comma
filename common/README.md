# 公共框架

三个 lesson 共用这一目录，不需要把 Web 页面或工具实现复制到作业中。

- `app/main.py`：启动本机 HTTP 服务；`--lesson 1/2/3` 选择加载哪个目录。
- `app/server.py`：HTTP 接口、SSE 实时事件、静态资源与本机访问限制。
- `app/sessions.py`：会话生命周期、停止、历史记录恢复。
- `app/runtime.py`：接入当前课时的模块、注册工具、保存记录与验收。
- `app/trace.py`：把真实工具事件转换成简短步骤。
- `app/static/`：浏览器工作台、深浅主题、图标及 MIT 授权。
- `core/`：消息类型、配置、题目、命令/编辑工具、Cua 观察策略及记录格式。

学生主要修改当前 lesson 的 TODO，不需要修改本目录。Computer Use 的观察模式由公共策略层强制执行；不要通过改策略绕过实验条件。

从项目根目录运行 `uv run mini-agent --lesson 1 --open`。每个 lesson 的 README 给出自己的目标和检查命令。
