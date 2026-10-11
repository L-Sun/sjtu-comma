"""教师参考答案。学生发布包不包含此目录。"""
import httpx
from common.core.types import ModelReply

_parameters = {}


async def model_parameters(client, model):
    if model not in _parameters:
        response = await client.get("https://openrouter.ai/api/v1/models")
        response.raise_for_status()
        _parameters.update({m["id"]: set(m.get("supported_parameters", [])) for m in response.json()["data"]})
    return _parameters.get(model)


def request_parameters(config, supported):
    # Strict provider routing refuses GPT-5.6 when temperature is supplied.
    # Do not silently drop required tools; adapt only optional generation knobs.
    result = {}
    if supported is None or "temperature" in supported:
        result["temperature"] = 0
    token_key = "max_tokens" if supported is None or "max_tokens" in supported else "max_completion_tokens"
    result[token_key] = config.max_tokens
    return result


async def complete(messages, tools, config):
    if not config.api_key:
        raise ValueError("未设置 OPENROUTER_API_KEY，请填写本地 .env。")
    body = {"model": config.model, "messages": messages, "provider": {"require_parameters": True}}
    if tools:
        body["tools"] = [tool.api_dict() for tool in tools]
        body["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=60) as client:
        options = request_parameters(config, await model_parameters(client, config.model))
        body.update(options)
        response = await client.post("https://openrouter.ai/api/v1/chat/completions", json=body,
                                     headers={"Authorization": f"Bearer {config.api_key}",
                                              "X-OpenRouter-Title": "COMMA Classroom"})
    if response.status_code != 200:
        # Provider response bodies can echo request content; don't print them.
        raise RuntimeError(f"OpenRouter HTTP {response.status_code}。检查模型、额度或 API Key。")
    data = response.json()
    if not data.get("choices"):
        raise RuntimeError("OpenRouter 未返回可用的模型消息。")
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型输出达到 token 上限，未执行可能不完整的工具调用。")
    if not choice["message"].get("content") and not choice["message"].get("tool_calls"):
        raise RuntimeError("模型返回了空回复，不能视为任务完成。")
    return ModelReply(choice["message"], {**data.get("usage", {}), "request_parameters": options})
