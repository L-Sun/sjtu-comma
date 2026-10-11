"""Read an OpenAI-compatible model catalog from the configured endpoint."""
import json
import httpx

from common.core.settings_store import validate_models


async def fetch_models(config):
    headers = {'Authorization': f'Bearer {config.api_key}'} if config.api_key else {}
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream('GET', config.base_url.rstrip('/') + '/models', headers=headers) as response:
                if response.status_code != 200:
                    raise ValueError(f'拉取失败（HTTP {response.status_code}），请检查 Base URL、API Key 和接口权限。')
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 4 * 1024 * 1024:
                        raise ValueError('模型列表过大，请检查接口地址。')
        result = json.loads(body)
        rows = result.get('data') if isinstance(result, dict) else None
        if not isinstance(rows, list):
            raise ValueError('接口未返回有效的模型列表（需要 data 数组）。')
        models = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                model_id = validate_models([row.get('id')])[0]
            except ValueError:
                continue
            name = row.get('name')
            models[model_id] = {'id': model_id, 'name': name[:200] if isinstance(name, str) else model_id}
        return sorted(models.values(), key=lambda model: model['id'].lower())
    except httpx.TimeoutException:
        raise ValueError('拉取超时，请检查接口地址或稍后重试。') from None
    except httpx.HTTPError:
        raise ValueError('无法连接模型接口，请检查 Base URL 和网络连接。') from None
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('接口返回的内容不是有效 JSON，请检查 Base URL。') from None
