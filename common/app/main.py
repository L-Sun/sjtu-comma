import argparse
import threading
import webbrowser

import uvicorn
from common.app.server import create_app
from common.core.config import load_config


def main(lesson=None):
    parser = argparse.ArgumentParser(description="COMMA Mini Agent Lab · 本机 Web 界面")
    parser.add_argument('--lesson', type=int, choices=[1, 2], default=lesson or 1,
                        help='课时：1 Agent 循环；2 Computer Use')
    parser.add_argument('--demo', action='store_true', help='模拟界面，不调用模型或电脑')
    parser.add_argument('--port', type=int, default=8766, help='本机端口（默认 8766）')
    parser.add_argument('--open', action='store_true', help='自动打开浏览器')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口必须在 1—65535 之间。')
    url = f'http://127.0.0.1:{args.port}'
    print(f'\nCOMMA · Lesson {args.lesson:02d} → {url}\n按 Ctrl+C 停止服务。\n', flush=True)
    if args.open:
        timer = threading.Timer(1, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()
    config = load_config().copy(lesson=args.lesson)
    uvicorn.run(create_app('demo' if args.demo else 'exercise', config),
                host='127.0.0.1', port=args.port, log_level='warning', timeout_graceful_shutdown=3)


if __name__ == '__main__':
    main()
