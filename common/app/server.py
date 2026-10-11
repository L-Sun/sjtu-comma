"""Loopback HTTP API, live SSE snapshots, and buildless web assets."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
import json
import os
from pathlib import Path
import secrets

from jsonschema import validate, ValidationError
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, StreamingResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from common.app.sessions import SessionService
from common.core.config import ROOT, load_config
from common.core.experiments import TASKS
from common.core.shell_tools import select_shell
from common.core.settings_store import save_api_key

STATIC = Path(__file__).parent / 'static'


class LocalOnly(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        host = request.url.hostname
        if host not in {'127.0.0.1', 'localhost', '::1'}:
            return JSONResponse({'error': '只接受本机地址。'}, status_code=400)
        origin = request.headers.get('origin')
        if (request.headers.get('sec-fetch-site') == 'cross-site'
                or (origin and origin != f'{request.url.scheme}://{request.headers.get("host")}')):
            return JSONResponse({'error': '拒绝跨站请求。'}, status_code=403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            token = request.headers.get('x-comma-token', '')
            if not secrets.compare_digest(token, request.app.state.csrf_token):
                return JSONResponse({'error': '页面会话已过期，请刷新后重试。'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; "
            "connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        return response


async def payload(request):
    if not request.headers.get('content-type', '').lower().startswith('application/json'):
        raise HTTPException(415, '请使用 JSON 请求。')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 64 * 1024:
            raise HTTPException(413, '请求过长。')
    try:
        result = json.loads(body)
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, '请求必须是 JSON 对象。')


def session_for(request):
    try:
        return request.app.state.service.get(request.path_params['session_id'])
    except (KeyError, OSError, ValueError):
        raise HTTPException(404, '会话不存在或记录不可用。')


async def index(request):
    return FileResponse(STATIC / 'index.html')


def lesson_capabilities(service):
    return ['chat', 'tools', 'computer'][:service.config.lesson]


async def bootstrap(request):
    service = request.app.state.service
    return JSONResponse({'csrf_token': request.app.state.csrf_token, 'demo': service.backend == 'demo', 'lesson': service.config.lesson,
                         'lesson_capabilities': lesson_capabilities(service),
                         'models': list(service.config.models), 'default_model': service.config.model,
                         'api_configured': bool(service.config.api_key), 'tasks': [asdict(task) for task in TASKS if task.mode in lesson_capabilities(service)],
                         'shell': {'platform': select_shell().platform, 'name': select_shell().name}})


async def settings(request):
    service = request.app.state.service
    if request.method == 'POST':
        data = await payload(request)
        if set(data) != {'api_key'} or not isinstance(data['api_key'], str):
            raise HTTPException(400, '请填写 OpenRouter API Key。')
        try:
            key = save_api_key(request.app.state.env_path, data['api_key'])
        except (OSError, UnicodeError):
            raise HTTPException(500, '无法保存本机 .env，请检查文件权限后重试。')
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        # Running turns retain their config snapshot; subsequent turns use this key.
        service.config.api_key = key
        os.environ['OPENROUTER_API_KEY'] = key
    return JSONResponse({'api_configured': bool(service.config.api_key)})


async def sessions(request):
    service = request.app.state.service
    if request.method == 'GET':
        return JSONResponse({'sessions': service.list(), 'active_id': service.active_id})
    data = await payload(request)
    defaults = {'model': service.config.model, 'perception': 'vision', 'task_id': 'free'}
    try:
        validate(data, {'type': 'object', 'properties': {
            'model': {'enum': list(service.config.models)}, 
            'perception': {'enum': ['vision', 'tree', 'hybrid']}, 'task_id': {'enum': [task.id for task in TASKS]}},
            'additionalProperties': False})
    except ValidationError:
        raise HTTPException(400, '请选择有效的模型、题目和观察方式。')
    settings = {**defaults, **data}
    task = next(task for task in TASKS if task.id == settings['task_id'])
    if task.mode not in lesson_capabilities(service):
        raise HTTPException(400, '当前课时尚未开放这道练习。')
    result = service.create(settings)
    return JSONResponse(service.snapshot(result), status_code=201)


async def session_snapshot(request):
    return JSONResponse(request.app.state.service.snapshot(session_for(request)))


async def message(request):
    service, session = request.app.state.service, session_for(request)
    data = await payload(request)
    try:
        validate(data, {'type': 'object', 'properties': {
            'text': {'type': 'string', 'minLength': 1, 'maxLength': 24000},
            'llm_only': {'type': 'boolean'}}, 'required': ['text'], 'additionalProperties': False})
    except ValidationError:
        raise HTTPException(400, '请输入1—24000字符的消息。')
    if not data['text'].strip():
        raise HTTPException(400, '消息不能为空。')
    try:
        service.start(session, data['text'], llm_only=data.get('llm_only', False))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    return JSONResponse(service.snapshot(session), status_code=202)


async def stop(request):
    service, session = request.app.state.service, session_for(request)
    try:
        await service.stop(session)
    except asyncio.CancelledError:
        # The run may have been cancelled before its coroutine began.
        if session.busy:
            session.busy, session.status = False, 'cancelled'
            session.trace.finish({'status': 'cancelled'})
            service.active_id = None
            service.publish()
    return JSONResponse(service.snapshot(session))


async def events(request):
    service, session = request.app.state.service, session_for(request)

    async def stream():
        seen = -1
        while not await request.is_disconnected():
            if seen != service.revision:
                seen = service.revision
                yield f'id: {seen}\nevent: snapshot\ndata: {json.dumps(service.snapshot(session), ensure_ascii=False)}\n\n'
            service.changed.clear()
            if seen != service.revision:
                continue
            try:
                await asyncio.wait_for(service.changed.wait(), 10)
            except TimeoutError:
                yield ': heartbeat\n\n'

    return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})


async def export(request):
    try:
        record = request.app.state.service.read_record(request.path_params['run_id'])
    except (OSError, ValueError):
        raise HTTPException(404, '运行记录不存在。')
    return JSONResponse(record, headers={'Content-Disposition': f'attachment; filename="{record["id"]}.json"'})


async def file(request):
    service = request.app.state.service
    run_id, filename = request.path_params['run_id'], request.path_params['filename']
    try:
        record = service.read_record(run_id)
    except (OSError, ValueError):
        raise HTTPException(404, '运行记录不存在。')
    allowed = {'baseline.py', record.get('code_file', '')}
    for event in record.get('events', []):
        if event['kind'] == 'tool_end':
            allowed.update(event['data'].get('result', {}).get('images', []))
    directory = service.root / run_id
    path = directory / filename
    if (filename not in allowed or not path.is_file() or path.is_symlink()
            or not path.resolve().is_relative_to(directory)):
        raise HTTPException(404, '文件不存在。')
    return FileResponse(path, media_type='text/plain; charset=utf-8' if path.suffix == '.py' else None)


async def http_error(request, exc):
    return JSONResponse({'error': str(exc.detail)}, status_code=exc.status_code)


def create_app(backend='exercise', config=None, *, root=None, env_path=None):
    service = SessionService(backend, config or load_config(), Path(root) if root else ROOT / 'runs')

    @asynccontextmanager
    async def lifespan(app):
        yield
        await service.close()

    app = Starlette(routes=[
        Route('/', index), Route('/api/bootstrap', bootstrap),
        Route('/api/settings', settings, methods=['GET', 'POST']),
        Route('/api/sessions', sessions, methods=['GET', 'POST']),
        Route('/api/sessions/{session_id}', session_snapshot),
        Route('/api/sessions/{session_id}/messages', message, methods=['POST']),
        Route('/api/sessions/{session_id}/stop', stop, methods=['POST']),
        Route('/api/sessions/{session_id}/events', events),
        Route('/api/runs/{run_id}/export', export), Route('/api/runs/{run_id}/files/{filename:path}', file),
        Mount('/static', app=StaticFiles(directory=STATIC)),
    ], middleware=[Middleware(LocalOnly)], exception_handlers={HTTPException: http_error}, lifespan=lifespan)
    app.state.service = service
    app.state.env_path = Path(env_path) if env_path is not None else ROOT / '.env'
    app.state.csrf_token = secrets.token_urlsafe(32)
    return app
