import importlib
import json

import httpx
import pytest
from dotenv import dotenv_values

from common.app.server import create_app
from common.core.config import Config, load_config
from common.core.model_catalog import fetch_models
from common.core.settings_store import validate_base_url, save_values


@pytest.mark.parametrize('value', ['ftp://example.com', 'https://user:password@example.com/v1', 'https://example.com/v1?key=secret', 'https://example.com/#x', 'http://', 'https://example.com/\nbad', 'https://example.com:bad', 'https://example.com\\@evil.test'])
def test_invalid_base_urls(value):
    with pytest.raises(ValueError):
        validate_base_url(value)


def test_base_url_accepts_compatible_paths():
    assert validate_base_url(' https://example.com/custom/v1/ ') == 'https://example.com/custom/v1'
    assert validate_base_url('http://localhost:1234/v1/') == 'http://localhost:1234/v1'


def test_atomic_settings_failure_preserves_original(tmp_path, monkeypatch):
    import common.core.settings_store as store
    path = tmp_path / '.env'
    path.write_text('OPENROUTER_API_KEY=original-key\nMAX_ROUNDS=17\n')
    original = path.read_bytes()
    real_set_key = store.set_key
    def fail_second(path, key, value):
        if key == 'OPENROUTER_BASE_URL':
            raise OSError('disk full')
        return real_set_key(path, key, value)
    monkeypatch.setattr(store, 'set_key', fail_second)
    with pytest.raises(OSError):
        save_values(path, {'OPENROUTER_API_KEY':'replacement-key', 'OPENROUTER_BASE_URL':'https://example.test/v1'})
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


async def test_base_url_models_and_restart_persistence(tmp_path, monkeypatch):
    for key in ('OPENROUTER_API_KEY','OPENROUTER_BASE_URL','OPENROUTER_MODELS','OPENROUTER_MODEL'):
        monkeypatch.delenv(key, raising=False)
    path=tmp_path/'.env'
    path.write_text('OPENROUTER_API_KEY=original-key\nMAX_ROUNDS=17\n')
    config=Config(api_key='original-key')
    app=create_app(config=config,root=tmp_path/'runs',env_path=path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
        assert (await client.post('/api/models',json={})).status_code == 403
        assert (await client.post('/api/settings/models',json={'models':['custom/model']})).status_code == 403
        client.headers['X-Comma-Token']=(await client.get('/api/bootstrap')).json()['csrf_token']
        result=await client.post('/api/settings',json={'base_url':'http://localhost:1234/v1/'})
        assert result.status_code == 200
        assert result.json()['base_url'] == 'http://localhost:1234/v1'
        assert config.api_key == 'original-key' and 'original-key' not in result.text
        for bad in ({'base_url':'ftp://example.com','api_key':'replacement-key'}, {'base_url':42}, {'unexpected':'value'}):
            assert (await client.post('/api/settings',json=bad)).status_code == 400
        assert config.api_key == 'original-key' and config.base_url == 'http://localhost:1234/v1'
        result=await client.post('/api/settings/models',json={'models':['custom/model','custom/model']})
        assert result.status_code == 200 and result.json()['models'].count('custom/model') == 1
        assert (await client.post('/api/settings/models',json={'models':['bad,model']})).status_code == 400
        assert (await client.post('/api/settings/models',json={'models':[]})).status_code == 400
        assert (await client.post('/api/sessions',json={'model':'custom/model'})).status_code == 201
        assert (await client.get('/api/bootstrap')).json()['models'][-1] == 'custom/model'
    values=dotenv_values(path)
    assert values['OPENROUTER_API_KEY']=='original-key' and values['MAX_ROUNDS']=='17'
    # Reload from the persisted file, independently of process environment updates.
    for key in ('OPENROUTER_API_KEY','OPENROUTER_BASE_URL','OPENROUTER_MODELS'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr('common.core.config.ROOT',tmp_path)
    restored=load_config()
    assert restored.base_url=='http://localhost:1234/v1' and restored.models[-1]=='custom/model'


def mock_client(monkeypatch, handler):
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx,'AsyncClient',lambda **kwargs: original(**kwargs,transport=httpx.MockTransport(handler)))


async def test_catalog_routes_authenticated_endpoint_deduplicates_and_sanitizes(monkeypatch, tmp_path):
    config=Config(base_url='https://custom.test/compatible/v1',api_key='test-private-key')
    app=create_app(config=config,root=tmp_path/'runs',env_path=tmp_path/'.env')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://127.0.0.1') as client:
        client.headers['X-Comma-Token']=(await client.get('/api/bootstrap')).json()['csrf_token']
        def handler(request):
            assert str(request.url)=='https://custom.test/compatible/v1/models'
            assert request.headers['Authorization']=='Bearer test-private-key'
            return httpx.Response(200,json={'data':[{'id':'z/model','name':'Z Model'},{'id':'a/model'}, {'id':'z/model','name':'Z Model'},None,{'id':'bad\nmodel'}]})
        mock_client(monkeypatch,handler)
        result=await client.post('/api/models',json={})
        assert result.status_code==200
        assert result.json()['models']==[{'id':'a/model','name':'a/model'},{'id':'z/model','name':'Z Model'}]
        assert 'test-private-key' not in result.text


@pytest.mark.parametrize('response', [httpx.Response(401,text='test-private-key'), httpx.Response(302,headers={'Location':'https://other.test/models'}), httpx.Response(200,text='not json test-private-key'),httpx.Response(200,json={'unexpected':[]})])
async def test_catalog_errors_do_not_echo_secrets_or_follow_redirects(monkeypatch,response):
    seen=[]
    def handler(request):
        seen.append(str(request.url));return response
    mock_client(monkeypatch,handler)
    with pytest.raises(ValueError) as error:
        await fetch_models(Config(api_key='test-private-key'))
    assert 'test-private-key' not in str(error.value) and len(seen)==1


async def test_catalog_timeout_and_empty_list(monkeypatch):
    def handler(request):
        raise httpx.ReadTimeout('test-private-key',request=request)
    original=httpx.AsyncClient
    mock_client(monkeypatch,handler)
    with pytest.raises(ValueError,match='超时'):
        await fetch_models(Config())
    monkeypatch.setattr(httpx,'AsyncClient',original)
    mock_client(monkeypatch,lambda request: httpx.Response(200,json={'data':[]}))
    assert await fetch_models(Config())==[]


async def test_actual_llm_uses_custom_url_and_selected_model_without_openrouter_fields(monkeypatch):
    llm=importlib.import_module('common.core.llm')
    seen=[]
    def handler(request):
        seen.append(str(request.url))
        assert str(request.url)=='https://custom.test/v1/chat/completions'
        assert request.headers['Authorization']=='Bearer custom-private-key'
        body=json.loads(request.content)
        assert body['model']=='custom/model' and 'provider' not in body
        assert 'X-OpenRouter-Title' not in request.headers
        return httpx.Response(200,json={'choices':[{'message':{'role':'assistant','content':'connected'},'finish_reason':'stop'}]})
    mock_client(monkeypatch,handler)
    result=await llm.complete([{'role':'user','content':'hello'}],[],Config(base_url='https://custom.test/v1/',api_key='custom-private-key',model='custom/model'))
    assert result.message['content']=='connected' and len(seen)==1
