from types import SimpleNamespace
import os
import stat

from dotenv import dotenv_values
import httpx
import pytest

from common.app.server import create_app
from common.app.runtime import Runtime
from common.core.config import Config
from common.core.settings_store import save_api_key
from common.core.types import ModelReply


def test_key_persistence_preserves_other_settings_and_private_permissions(tmp_path):
    path = tmp_path / '.env'
    path.write_text('# local configuration\nOPENROUTER_MODEL=example/model\nOPENROUTER_API_KEY=previous-key\nMAX_ROUNDS=17\n')
    path.chmod(0o644)
    assert save_api_key(path, '  test-openrouter-new-key  ') == 'test-openrouter-new-key'
    values = dotenv_values(path)
    assert values['OPENROUTER_API_KEY'] == 'test-openrouter-new-key'
    assert values['OPENROUTER_MODEL'] == 'example/model' and values['MAX_ROUNDS'] == '17'
    assert path.read_text().startswith('# local configuration\n')
    if os.name != 'nt':
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob('.tmp_*'))


@pytest.mark.parametrize('key', ['', 'short', 'test key with spaces', 'test-key\nOTHER=bad', '${PASSWORD}', 'x'*513])
def test_invalid_key_never_changes_file(tmp_path, key):
    path = tmp_path / '.env'
    path.write_text('OPENROUTER_API_KEY=original-key\n')
    with pytest.raises(ValueError):
        save_api_key(path, key)
    assert path.read_text() == 'OPENROUTER_API_KEY=original-key\n'


async def test_settings_save_is_private_persistent_and_applies_without_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'initial-env-key')
    config = Config(api_key='previous-key', lesson=1)
    app = create_app('exercise', config, root=tmp_path/'runs', env_path=tmp_path/'.env')
    seen = []

    async def complete(messages, tools, config):
        seen.append(config.api_key)
        return ModelReply({'role':'assistant','content':'ready'})

    monkeypatch.setattr(Runtime, 'module', lambda self, name: SimpleNamespace(complete=complete))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
            boot = (await client.get('/api/bootstrap')).json()
            initial = await client.get('/api/settings')
            assert initial.json() == {'api_configured': True} and 'previous-key' not in initial.text
            assert (await client.post('/api/settings',json={'api_key':'unauthorized-key'})).status_code == 403
            assert not (tmp_path/'.env').exists()
            client.headers['X-Comma-Token'] = boot['csrf_token']
            response = await client.post('/api/settings',json={'api_key':'test-openrouter-new-key'})
            assert response.status_code == 200
            assert response.json() == {'api_configured': True}
            assert 'test-openrouter-new-key' not in response.text
            assert dotenv_values(tmp_path/'.env')['OPENROUTER_API_KEY'] == 'test-openrouter-new-key'
            assert os.environ['OPENROUTER_API_KEY'] == 'test-openrouter-new-key'
            sid = (await client.post('/api/sessions',json={})).json()['id']
            await client.post(f'/api/sessions/{sid}/messages',json={'text':'hello'})
            await app.state.service.get(sid).task
            assert seen == ['test-openrouter-new-key']
            snapshot = (await client.get(f'/api/sessions/{sid}')).json()
            assert snapshot['status'] == 'completed'
            exported = await client.get(f"/api/runs/{snapshot['run_id']}/export")
            assert 'test-openrouter-new-key' not in exported.text
            assert 'test-openrouter-new-key' not in (await client.get('/api/bootstrap')).text
            # Blank input never removes or replaces an existing credential.
            assert (await client.post('/api/settings',json={'api_key':''})).status_code == 400
            assert config.api_key == 'test-openrouter-new-key'


async def test_settings_write_failure_keeps_active_key(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY','unchanged-key')
    config = Config(api_key='unchanged-key')
    path = tmp_path / '.env'
    path.mkdir()
    app = create_app(config=config, root=tmp_path/'runs', env_path=path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
        client.headers['X-Comma-Token']=(await client.get('/api/bootstrap')).json()['csrf_token']
        response=await client.post('/api/settings',json={'api_key':'replacement-key'})
        assert response.status_code == 500 and 'replacement-key' not in response.text
        assert config.api_key == 'unchanged-key'
        assert os.environ['OPENROUTER_API_KEY'] == 'unchanged-key'
