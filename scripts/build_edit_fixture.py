"""Build the deterministic 5,000-line classroom example (teacher utility)."""
from pathlib import Path


def build():
    lines = ['# 长文件局部编辑实验：课程页面内容与渲染方法\n',
             '# 合成的 5,000 行教学样例；A/B/C 有同名函数，避免全局替换。\n']
    lines.extend(f'# 页面配置说明 {i:04d}：保留本行原样。\n' for i in range(3, 20))
    for number in range(20, 5001):
        course = 'A' if number < 1700 else 'B' if number < 3600 else 'C'
        lines.append(f'    section_{number:04d} = ("课程 {course}", "第 {number:04d} 节的页面正文与练习说明。")\n')

    def put(number, *content):
        for index, line in enumerate(content, number - 1):
            lines[index] = line + '\n'

    for course, start, definition, card, outline in [
        ('A', 20, 108, 360, 1400), ('B', 1700, 1808, 2060, 3100),
        ('C', 3600, 3808, 4060, 4800),
    ]:
        put(start, f'class Course{course}:')
        put(start + 1, f'    """课程 {course} 的页面定义；同名方法属于各自课程。"""')
        put(definition - 1, f'    # 课程 {course}：标题格式化，供卡片和目录共同使用。',
            '    def format_title(self, title):', f'        return f"课程 {course} · {{title.strip()}}"')
        put(card - 2, f'    # 课程 {course}：卡片标题入口。', '    def render_card(self, title):',
            '        return self.format_title(title)')
        put(outline - 2, f'    # 课程 {course}：目录标题入口。', '    def render_outline(self, title):',
            '        return self.format_title(title)')
        put(start + 8, '    # 文档中的 format_title 是历史说明，本次不改这段文字。')
    return ''.join(lines)


if __name__ == '__main__':
    target = Path(__file__).resolve().parents[1] / 'common/core/fixtures/course_page.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(build().encode('utf-8'))
    print(target)
