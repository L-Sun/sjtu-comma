from __future__ import annotations
import base64
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import uuid

from common.core.types import ToolResult


def redact(value, secret=""):
    if isinstance(value, str):
        if secret:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"sk-or-v1-[A-Za-z0-9_-]+", "[REDACTED]", value)
        return re.sub(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", "[image omitted]", value)
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in {"api_key", "authorization"} else redact(v, secret)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v, secret) for v in value]
    return value


class Record:
    def __init__(self, config, backend, task_id, root=Path("runs")):
        self.id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        self.path = root / self.id
        self.secret = config.api_key
        self.data = {"id": self.id, "started_at": datetime.now(timezone.utc).isoformat(),
                     "model": config.model, "backend": backend, "mode": config.mode,
                     "perception": config.perception if config.mode == "computer" else None,
                     "task_id": task_id, "max_rounds": config.max_rounds,
                     "temperature": None, "max_tokens": config.max_tokens,
                     "observation_policy": "window-v1", "framework_version": "0.1.0",
                     "input_addressing": ("pixels+keys" if config.perception == "vision" else "element_token+pixels+keys") if config.mode == "computer" else None,
                     "events": [], "status": "running"}
        self.last_image: Path | None = None

    def add(self, kind, data):
        data = dict(data)
        result = data.get("result")
        if isinstance(result, ToolResult):
            pictures = []
            for im in result.images:
                try:
                    content = base64.b64decode(im.data, validate=True)
                    if len(content) > 15 * 1024 * 1024:
                        continue
                    self.path.mkdir(parents=True, exist_ok=True)
                    ext = "png" if im.mime_type == "image/png" else "jpg"
                    p = self.path / f"observation-{len(self.data['events'])}-{len(pictures)}.{ext}"
                    p.write_bytes(content)
                    self.last_image = p.resolve()
                    pictures.append(p.name)
                except ValueError:
                    pass
            data["result"] = {"text": result.text, "is_error": result.is_error,
                              "images": pictures, "image_count": len(result.images)}
        self.data["events"].append({"kind": kind, "data": redact(data, self.secret)})

    def save(self) -> Path:
        self.path.mkdir(parents=True, exist_ok=True)
        p = self.path / "run.json"
        p.write_text(json.dumps(redact(self.data, self.secret), ensure_ascii=False, indent=2), encoding="utf-8")
        return p.resolve()
