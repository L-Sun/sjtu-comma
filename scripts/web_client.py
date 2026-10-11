"""Teacher HTTP-contract runner. Uses the same routes as the browser, without UI automation."""
import asyncio
from contextlib import asynccontextmanager

import httpx
from common.app.server import create_app
from common.core.experiments import task_by_id


class WebRunner:
    def __init__(self, app, client, config):
        self.app, self.client, self.config = app, client, config
        self.session_id = None

    async def new(self, model, task_id='free', *, perception='vision'):
        task = task_by_id(task_id)
        response = await self.client.post('/api/sessions', json={
            'model': model, 'task_id': task_id, 'perception': perception})
        response.raise_for_status()
        self.session_id = response.json()['id']

    async def submit(self, text, *, llm_only=False):
        response = await self.client.post(f'/api/sessions/{self.session_id}/messages',
                                          json={'text': text, 'llm_only': llm_only})
        response.raise_for_status()
        task = self.app.state.service.get(self.session_id).task
        await asyncio.wait_for(asyncio.shield(task), self.config.turn_timeout + 10)
        snapshot = (await self.client.get(f'/api/sessions/{self.session_id}')).json()
        response = await self.client.get(f"/api/runs/{snapshot['run_id']}/export")
        response.raise_for_status()
        return response.json()


@asynccontextmanager
async def web_runner(config):
    app = create_app('exercise', config)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1') as client:
            client.headers['X-Comma-Token'] = (await client.get('/api/bootstrap')).json()['csrf_token']
            yield WebRunner(app, client, config)
