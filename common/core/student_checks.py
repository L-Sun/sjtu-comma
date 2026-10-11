"""Run a saved-source exercise check in a cancellable child process."""
import asyncio
import json
import subprocess
import sys

from common.core.shell_tools import child_environment, ShellRunner


async def run_student_check(root, module, source, timeout, not_ready):
    options = {'start_new_session': True} if sys.platform != 'win32' else {
        'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', module, '--json', '--source-stdin',
            cwd=root, env=child_environment(), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options)
    except OSError:
        return not_ready("无法启动检查进程，请运行离线检查查看详情。")
    async def read_limited(stream):
        data = bytearray()
        while chunk := await stream.read(8192):
            if len(data) < 64 * 1024:
                data.extend(chunk[:64 * 1024-len(data)])
        return bytes(data)
    async def communicate():
        async def send_source():
            try:
                process.stdin.write(source.encode('utf-8'))
                await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                process.stdin.close()
        _, stdout, _ = await asyncio.gather(send_source(), read_limited(process.stdout), read_limited(process.stderr))
        await process.wait()
        return stdout
    try:
        output = await asyncio.wait_for(communicate(), timeout)
        result = json.loads(output)
        if not isinstance(result, dict) or not isinstance(result.get('checks'), list):
            raise ValueError()
        result['ready'] = result.get('ready') is True and process.returncode == 0
        return result
    except asyncio.CancelledError:
        await ShellRunner(root)._stop(process)
        raise
    except TimeoutError:
        await ShellRunner(root)._stop(process)
        return not_ready('检查超时，请检查是否有无限循环或未结束的等待。教学 Chat 仍可使用。')
    except (ValueError, OSError):
        await ShellRunner(root)._stop(process)
        return not_ready('检查未能完成，请检查作业文件的导入或运行错误，或运行离线检查查看详情。')
