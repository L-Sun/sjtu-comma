"""Validate and atomically persist local connection settings."""
from pathlib import Path
import os
import re
import tempfile
from urllib.parse import urlsplit

from dotenv import set_key


def validate_api_key(value: str) -> str:
    key = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_.-]{8,512}', key):
        raise ValueError('请输入完整的 API Key，不要包含空格或换行。')
    return key


def validate_base_url(value: str) -> str:
    value = value.strip().rstrip('/')
    try:
        url = urlsplit(value)
        valid = (url.scheme in {'http', 'https'} and url.hostname and url.port != 0
                 and not url.username and not url.password and not url.query and not url.fragment)
    except ValueError:
        valid = False
    if not valid or len(value) > 2048 or re.search(r'[\s\\\x00-\x1f\x7f]', value):
        raise ValueError('Base URL 需为完整的 http:// 或 https:// 地址，不含账号、参数或片段。')
    return value


def validate_models(values) -> tuple[str, ...]:
    if not isinstance(values, list) or not 1 <= len(values) <= 200:
        raise ValueError('请选择 1—200 个模型。')
    if any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_./:@+-]{1,256}', x) for x in values):
        raise ValueError('模型 ID 无效。')
    return tuple(dict.fromkeys(values))


def save_values(path: Path, values: dict[str, str]):
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError('配置文件不是普通文件。')
    # Stage all entries before replacing the original, retaining comments and other settings.
    content = path.read_text() if path.exists() else ''
    fd, name = tempfile.mkstemp(prefix='.comma-settings-', dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
        for key, value in values.items():
            set_key(staged, key, value)
        staged.chmod(0o600)
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


def save_api_key(path: Path, value: str) -> str:
    key = validate_api_key(value)
    save_values(path, {'OPENROUTER_API_KEY': key})
    return key
