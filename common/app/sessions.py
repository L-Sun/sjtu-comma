"""Local chat sessions and presentation state, independent of the HTTP/UI layer."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from common.app.runtime import Runtime
from common.app.trace import TraceState, replay_trace, short
from common.core.records import redact

RUN_ID = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{8}$')


def now():
    return datetime.now(timezone.utc).isoformat()


def messages_from(record):
    return [{'role': e['kind'], 'text': e['data']['text']}
            for e in record.get('events', []) if e['kind'] in {'user', 'assistant'}]


class Session:
    def __init__(self, service, settings, *, record=None):
        self.settings = settings
        self.id = 'run-' + record['id'] if record else uuid.uuid4().hex
        self.created_at = record['started_at'] if record else now()
        self.title = '新对话'
        self.messages = []
        self.trace = TraceState()
        self.runtime = Runtime(service.backend, root=service.root, lesson=service.config.lesson)
        self.task = None
        self.busy = False
        self.readonly = record is not None
        self.records = [record] if record else []
        self.status = record['status'] if record else 'ready'
        if record:
            self.messages = messages_from(record)
            self.title = short(next((m['text'] for m in self.messages if m['role'] == 'user'), '历史记录'), 46)
            self.trace = replay_trace(record)

    @property
    def record(self):
        return self.runtime.last_record.data if self.runtime.last_record else self.records[-1] if self.records else None

    def metadata(self):
        return {'id': self.id, 'title': self.title, 'created_at': self.created_at,
                'settings': self.settings, 'status': self.status, 'busy': self.busy,
                'readonly': self.readonly, 'grade': (self.record or {}).get('grade')}

    def public(self):
        record = self.record
        images = []
        if record:
            for event in record.get('events', []):
                if event['kind'] == 'tool_end':
                    images.extend(event['data'].get('result', {}).get('images', []))
        result = {**self.metadata(), 'messages': self.messages, 'trace': self.trace.public(),
                  'run_id': record['id'] if record else None,
                  'images': [{'name': name, 'url': f"/api/runs/{record['id']}/files/{name}"} for name in images],
                  'elapsed_seconds': (record or {}).get('elapsed_seconds'),
                  'code_file': (record or {}).get('code_file')}
        return result


class SessionService:
    def __init__(self, backend, config, root: Path):
        self.backend, self.config, self.root = backend, config, root.resolve()
        self.sessions = {}
        self.history = {}
        self.active_id = None
        self.revision = 0
        self.changed = asyncio.Event()
        # Old runs are read-only views. Never pretend their model context survived a restart.
        for path in sorted(self.root.glob('*/run.json'), reverse=True):
            if not RUN_ID.fullmatch(path.parent.name) or path.is_symlink() or path.parent.is_symlink():
                continue
            try:
                record = self.read_record(path.parent.name)
                if record.get('mode') not in ['chat', 'tools', 'computer'][:self.config.lesson]:
                    continue
                settings = {key: record.get(key) for key in ('model', 'perception', 'task_id')}
                settings['perception'] = settings['perception'] or 'vision'
                message = next((e['data']['text'] for e in record.get('events', []) if e['kind'] == 'user'), '历史记录')
                self.history['run-' + record['id']] = {
                    'id': 'run-' + record['id'], 'title': short(message, 46),
                    'created_at': record['started_at'], 'settings': settings,
                    'status': record['status'], 'busy': False, 'readonly': True, 'grade': record.get('grade')}
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def publish(self):
        self.revision += 1
        self.changed.set()

    def list(self):
        values = {**self.history, **{key: value.metadata() for key, value in self.sessions.items()}}
        return sorted(values.values(), key=lambda item: item['created_at'], reverse=True)

    def create(self, settings):
        session = Session(self, settings)
        self.sessions[session.id] = session
        self.publish()
        return session

    def get(self, session_id):
        if session_id in self.sessions:
            return self.sessions[session_id]
        if session_id in self.history:
            metadata = self.history[session_id]
            session = Session(self, metadata['settings'], record=self.read_record(session_id[4:]))
            self.sessions[session.id] = session
            return session
        raise KeyError('会话不存在。')

    def snapshot(self, session):
        return redact({**session.public(), 'active_id': self.active_id, 'revision': self.revision}, self.config.api_key)

    def read_record(self, run_id):
        if not RUN_ID.fullmatch(run_id):
            raise FileNotFoundError('记录不存在。')
        path = self.root / run_id / 'run.json'
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
            raise FileNotFoundError('记录不可用。')
        record = json.loads(path.read_text(encoding='utf-8'))
        if record.get('id') != run_id:
            raise ValueError('记录 ID 不一致。')
        return redact(record, self.config.api_key)

    def start(self, session, text, *, llm_only=False):
        if session.readonly:
            raise ValueError('这是历史记录；请新建对话后运行。')
        if self.active_id is not None:
            raise ValueError('已有会话正在执行；请等待完成或先停止。')
        session.busy = True
        session.status = 'running'
        self.active_id = session.id
        if not session.messages:
            session.title = short(redact(text, self.config.api_key), 46)
        session.messages.append({'role': 'user', 'text': redact(text, self.config.api_key)})
        session.trace.begin(redact(text, self.config.api_key))
        config = self.config.copy(**{key: session.settings[key] for key in ('model', 'perception')})
        self.publish()

        def emit(event):
            session.trace.feed(event)
            if event.kind == 'assistant':
                session.messages.append({'role': 'assistant', 'text': event.data['text']})
            self.publish()

        async def run():
            try:
                await session.runtime.run(text, config, emit, session.settings['task_id'], llm_only=llm_only)
            except asyncio.CancelledError:
                pass
            finally:
                record = session.runtime.last_record
                if record:
                    if not session.records or session.records[-1]['id'] != record.id:
                        session.records.append(record.data)
                    session.trace.finish(record.data)
                    session.status = record.data['status']
                else:
                    session.status = 'cancelled'
                    session.trace.finish({'status': 'cancelled'})
                session.busy = False
                self.active_id = None
                self.publish()

        session.task = asyncio.create_task(run())

    async def stop(self, session):
        if session.task and not session.task.done():
            session.task.cancel()
            try:
                await session.task
            except asyncio.CancelledError:
                pass
            # A task cancelled before its coroutine started does not execute finally.
        if session.busy:
            session.busy = False
            session.status = 'cancelled'
            session.runtime.reset()
            session.trace.finish({'status': 'cancelled'})
            self.active_id = None
            self.publish()

    async def close(self):
        tasks = [session.task for session in self.sessions.values() if session.task and not session.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
