"""Teacher-provided prompts and transparent, narrow grading rules."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    mode: str
    prompt: str
    note: str


TASKS = [
    Task("free", "自由探索", "chat", "", "自由输入指令；不同模型比较时请恢复相同初始状态。"),
    Task("code-edit", "长文件局部编辑", "tools",
    '本轮 course_page.py 有5,000行，包含课程A、B、C。请用 search_file 和分段 read_file 定位代码，'
    '再用 edit 实际修改：仅将 CourseB 的 format_title 方法重命名为 format_course_title，'
    '同步修改课程B的 render_card 和 render_outline 中各一处调用。课程A、C也有同名方法，但本次不改。'
    '除了课程B这三处标识符，其他代码、空白、注释和文档文字必须保持原样。'
    '不要重写整份文件，不要做全局替换；建议将三处替换作为同一次 edit 的 edits 数组提交。'
    '修改后分段读取检查，最终简述修改。独立验收会检查三处修改、无关内容逐字节不变及运行行为。',
    '5,000行 · 同名干扰 · 三处远距离修改。续聊保留修改；点击“重置实验”才恢复基线。原始文件和补丁随记录保存。')
]


def task_by_id(value: str) -> Task:
    return next(t for t in TASKS if t.id == value)


def grade(task_id: str, answer: str, calls: list[dict]) -> dict:
    # The edit experiment is graded from its actual file by CodeEditor.
    return {"status": "manual", "reason": "请独立核对任务结果；模型自报不作为成功判据。"}
