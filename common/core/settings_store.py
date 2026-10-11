"""Persist local credentials without exposing saved values to the browser."""
from pathlib import Path
import re

from dotenv import set_key


def save_api_key(path: Path, value: str) -> str:
    key = value.strip()
    if not re.fullmatch(r'[A-Za-z0-9_-]{8,512}', key):
        raise ValueError('请输入完整的 OpenRouter API Key，不要包含空格或换行。')
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise OSError('配置文件不是普通文件。')
    if path.exists():
        path.chmod(0o600)
    # python-dotenv updates only this entry, preserving the remaining settings.
    # Its temporary file is in the same directory and replaced atomically.
    set_key(path, 'OPENROUTER_API_KEY', key)
    return key
