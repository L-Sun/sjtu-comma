"""Local chat sessions and presentation state, independent of the HTTP/UI layer."""
from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from common.app.runtime import Runtime
from common.app.trace import TraceState, replay_trace, replay_records, short
from common.core.records import redact
from common.core.config import ROOT
from common.core.experiments import TASKS
from common.core.learning_workspace import LearningWorkspace
from common.core.runtime_diagnostics import failure_context
from common.core.edit_tools import FILENAME

RUN_ID = re.compile(r'^\d{8}T\d{6}-[a-f0-9]{8}$')
SESSION_ID = re.compile(r'^[a-f0-9]{32}$')


def now():
    return datetime.now(timezone.utc).isoformat()


def messages_from(record):
    return [{'role': e['kind'], 'text': e['data']['text']}
            for e in record.get('events', []) if e['kind'] in {'user', 'assistant'}]


class Session:
    def __init__(self, service, settings, *, record=None, experiment=None):
        self.settings = settings
        self.experiment = experiment
        self.id = 'run-' + record['id'] if record else uuid.uuid4().hex
        self.created_at = record['started_at'] if record else now()
        self.title = '新对话'
        self.messages = []
        self.trace = TraceState()
        self.runtime = Runtime(root=service.root, lesson=service.config.lesson, learning=service.learning)
        self.task = None
        self.busy = False
        self.readonly = record is not None
        self.legacy = record is not None and not record.get('session_id')
        self.records = [record] if record else []
        self.status = record['status'] if record else 'ready'
        if experiment:
            self.id = f'experiment-{service.config.lesson}-{experiment.id}'
            self.title = experiment.title
            self.runtime.experiment_id = self.id
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
                'readonly': self.readonly, 'grade': (self.record or {}).get('grade'),
                'awaiting_continue': self.runtime.awaiting_continue and not self.busy and not self.readonly,
                'legacy': self.legacy,
                'experiment': self.experiment.id if self.experiment else None}

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
                  'code_file': (record or {}).get('code_file'),
                  'runner': (record or {}).get('runner'), 'source_version': (record or {}).get('source_version'),
                  'runs': [{'id': item['id'], 'title': short(next((m['text'] for m in messages_from(item)
                            if m['role'] == 'user'), '继续下一步' if item.get('continuation') else '运行记录'), 36)} for item in self.records],
                  'initial_prompt': self.experiment.prompt if self.experiment else '',
                  'experiment_note': self.experiment.note if self.experiment else ''}
        return result


class SessionService:
    def __init__(self, config, root: Path, *, lesson_root=None):
        self.config, self.root = config, root.resolve()
        self.learning = LearningWorkspace(lesson_root or ROOT) if config.lesson == 1 else None
        self.sessions = {}
        self.history = {}
        self.active_id = None
        self.revision = 0
        self.changed = asyncio.Event()
        for task in TASKS:
            if task.id != 'free' and task.mode in ['chat', 'tools', 'computer'][:config.lesson + 1]:
                session = Session(self, {'model': config.model, 'perception': 'vision', 'task_id': task.id}, experiment=task)
                self.sessions[session.id] = session
        conversations = {}
        # New runs carry stable conversation IDs and a final model-history checkpoint.
        # Legacy runs cannot safely be grouped by timestamps or similar text.
        for path in sorted(self.root.glob('*/run.json'), reverse=True):
            if not RUN_ID.fullmatch(path.parent.name) or path.is_symlink() or path.parent.is_symlink():
                continue
            try:
                record = self.read_record(path.parent.name)
                if record.get('mode') not in ['chat', 'tools', 'computer'][:self.config.lesson + 1]:
                    continue
                if not isinstance(record.get('started_at'), str) or not isinstance(record.get('status'), str):
                    continue
                # Retired experiments must not reappear as ordinary conversations.
                if record.get('task_id', 'free') not in {task.id for task in TASKS}:
                    continue
                if record.get('experiment_id') and record['experiment_id'] not in self.sessions:
                    continue
                messages_from(record)  # Validate visible events before grouping them.
                experiment = self.sessions.get(record.get('experiment_id'))
                if experiment is not None:
                    experiment.records.append(record)
                    continue
                conversation_id = record.get('session_id')
                if isinstance(conversation_id, str) and SESSION_ID.fullmatch(conversation_id):
                    if record.get('lesson') == config.lesson:
                        conversations.setdefault(conversation_id, []).append(record)
                    continue
                settings = {key: record.get(key) for key in ('model', 'perception', 'task_id')}
                settings['perception'] = settings['perception'] or 'vision'
                message = next((e['data']['text'] for e in record.get('events', []) if e['kind'] == 'user'), '历史记录')
                self.history['run-' + record['id']] = {
                    'id': 'run-' + record['id'], 'title': short(message, 46),
                    'created_at': record['started_at'], 'settings': settings,
                    'status': record['status'], 'busy': False, 'readonly': True, 'legacy': True,
                    'grade': record.get('grade')}
            except (OSError, ValueError, KeyError, TypeError):
                continue

        for session in self.sessions.values():
            if not session.records:
                continue
            session.records.sort(key=lambda record: record['started_at'])
            session.messages = [message for record in session.records for message in messages_from(record)]
            session.trace = replay_records(session.records)
            session.settings.update({key: session.records[-1][key] for key in ('model', 'perception')})
            session.status = session.records[-1]['status']
            session.readonly = not self.restore_runtime(session)

        for conversation_id, records in conversations.items():
            records.sort(key=lambda record: (record['started_at'], record['id']))
            first, latest = records[0], records[-1]
            settings = {key: latest.get(key) for key in ('model', 'perception', 'task_id')}
            settings['perception'] = settings['perception'] or 'vision'
            session = Session(self, settings)
            session.id = conversation_id
            session.created_at = first.get('session_created_at', first['started_at'])
            session.records = records
            session.messages = [message for record in records for message in messages_from(record)]
            session.title = first.get('session_title') or short(next(
                (m['text'] for m in session.messages if m['role'] == 'user'), '历史对话'), 46)
            session.status = 'cancelled' if latest['status'] == 'running' else latest['status']
            session.trace = replay_records([*records[:-1], {**latest, 'status': session.status}])
            self.restore_runtime(session)
            self.sessions[session.id] = session

    def restore_runtime(self, session):
        records = session.records
        latest = records[-1]
        # A crash or failed turn may leave unmatched tool calls. Never resume those.
        recoverable = latest['status'] in {'completed', 'limit', 'waiting'} or (
            latest['status'] == 'error' and latest.get('context_recovered') is True)
        restored = recoverable and isinstance(latest.get('model_messages'), list)
        if restored:
            session.runtime.state.messages = deepcopy(latest['model_messages'])
            session.runtime.awaiting_continue = bool(latest.get('awaiting_continue') and
                session.runtime.state.messages and session.runtime.state.messages[-1].get('role') == 'tool')
        if latest['status'] not in {'running', 'cancelled', 'timeout'}:
            failed = next((record for record in reversed(records) if record['status'] == 'error'), None)
            session.runtime.last_failure = failure_context(failed) if failed else None
        previous = next((record for record in reversed(records) if record.get('code_file')), None)
        if previous:
            path = self.root / previous['id'] / 'code' / FILENAME
            if path.is_file() and not path.is_symlink() and not path.parent.is_symlink():
                session.runtime.edit_path = path
            else:
                # Do not silently replace a missing edited file with the baseline.
                session.readonly = True
                restored = False
        return restored

    def publish(self):
        self.revision += 1
        self.changed.set()

    def list(self):
        values = {**self.history, **{key: value.metadata() for key, value in self.sessions.items()}}
        fixed = [item for item in values.values() if item.get('experiment')]
        history = sorted((item for item in values.values() if not item.get('experiment')), key=lambda item: item['created_at'], reverse=True)
        return [*fixed, *history]

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
        return redact({**session.public(), 'active_id': self.active_id, 'revision': self.revision,
                       'learning': self.learning.public() if self.learning else None,
                       'removed': session.id not in self.sessions and session.id not in self.history}, self.config.api_key)

    def read_record(self, run_id):
        if not RUN_ID.fullmatch(run_id):
            raise FileNotFoundError('记录不存在。')
        path = self.root / run_id / 'run.json'
        if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size > 32 * 1024 * 1024:
            raise FileNotFoundError('记录不可用。')
        record = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or record.get('id') != run_id:
            raise ValueError('记录 ID 不一致。')
        return redact(record, self.config.api_key)

    def start(self, session, text, *, llm_only=False, continuation=False, expected_run_id=None):
        if session.readonly:
            raise ValueError('这是历史记录；请新建对话后运行。')
        if self.active_id is not None:
            raise ValueError('已有会话正在执行；请等待完成或先停止。')
        if continuation and (not session.runtime.awaiting_continue or not session.record or
                             session.record['id'] != expected_run_id):
            raise ValueError('这一步已继续或没有待处理的工具结果，请刷新会话。')
        session.busy = True
        session.status = 'running'
        self.active_id = session.id
        if not session.messages and not session.experiment:
            session.title = short(redact(text, self.config.api_key), 46)
        if not session.experiment:
            session.runtime.conversation = {'session_id': session.id, 'session_created_at': session.created_at,
                                            'session_title': session.title}
        if not continuation:
            session.messages.append({'role': 'user', 'text': redact(text, self.config.api_key)})
        session.trace.begin('继续下一步' if continuation else redact(text, self.config.api_key))
        config = self.config.copy(**{key: session.settings[key] for key in ('model', 'perception')})
        self.publish()

        def emit(event):
            session.trace.feed(event)
            if event.kind == 'assistant':
                session.messages.append({'role': 'assistant', 'text': event.data['text']})
            self.publish()

        async def run():
            try:
                await session.runtime.run(text, config, emit, session.settings['task_id'],
                                          llm_only=llm_only, continuation=continuation)
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

    def clear_history(self, keep_id=None):
        protected = {value for value in (keep_id, self.active_id) if value is not None}
        protected.update(key for key, session in self.sessions.items() if session.experiment)
        if keep_id is not None:
            self.get(keep_id)  # Reject a stale selection before touching history.
        removed_ids = (set(self.history) | set(self.sessions)) - protected
        run_ids = {key[4:] for key in self.history if key in removed_ids}
        protected_runs = set()
        for key, session in self.sessions.items():
            ids = {record['id'] for record in session.records}
            if session.runtime.last_record:
                ids.add(session.runtime.last_record.id)
            (protected_runs if key in protected else run_ids).update(ids)
        run_ids -= protected_runs
        self.archive_runs(run_ids)
        for key in removed_ids:
            self.history.pop(key, None)
            session = self.sessions.pop(key, None)
            if session:
                session.runtime.reset()
                session.runtime.last_record = None
                session.messages = []
                session.records = []
                session.trace = TraceState()
        self.publish()
        return len(removed_ids)

    def reset_experiment(self, session):
        if not session.experiment:
            raise ValueError('只有固定实验可以重置。')
        if session.busy:
            raise ValueError('请先停止实验，再重置。')
        ids = {record['id'] for record in session.records}
        if session.runtime.last_record:
            ids.add(session.runtime.last_record.id)
        self.archive_runs(ids)
        session.runtime.reset(clear_workspace=True)
        session.runtime.last_record = None
        session.messages = []
        session.records = []
        session.trace = TraceState()
        session.status = 'ready'
        session.readonly = False
        session.task = None
        self.publish()

    def archive_runs(self, run_ids):
        # Archive as one batch, so a failed move leaves the entire list intact.
        moved = []
        if run_ids:
            trash = self.root / '.trash'
            if trash.is_symlink():
                raise OSError('回收目录不可用。')
            destination = trash / uuid.uuid4().hex
            destination.mkdir(parents=True)
            try:
                for run_id in sorted(run_ids):
                    if not RUN_ID.fullmatch(run_id):
                        raise OSError('运行记录 ID 无效。')
                    source = self.root / run_id
                    if source.is_symlink():
                        raise OSError('运行记录目录不可用。')
                    if source.exists():
                        target = destination / run_id
                        source.rename(target)
                        moved.append((source, target))
            except OSError:
                for source, target in reversed(moved):
                    target.rename(source)
                raise

    async def close(self):
        tasks = [session.task for session in self.sessions.values() if session.task and not session.task.done()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
