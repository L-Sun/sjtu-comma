from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import shutil

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Config:
    api_key: str = field(default="", repr=False)
    lesson: int = 3
    model: str = "google/gemini-2.5-flash"
    models: tuple[str, ...] = ("google/gemini-2.5-flash", "google/gemini-3.8-flash")
    max_rounds: int = 24
    max_tokens: int = 2048
    turn_timeout: float = 180
    perception: str = "vision"  # vision, tree, hybrid
    driver: str = "cua-driver"
    target_pid: int | None = None
    target_window: int | None = None

    @property
    def mode(self):
        # Legacy record label, derived solely from the selected lesson.
        return ('chat', 'tools', 'computer')[self.lesson - 1]

    def copy(self, **kwargs):
        return replace(self, **kwargs)


def load_config() -> Config:
    load_dotenv(ROOT / ".env", override=False)
    defaults = Config()
    model = os.getenv("OPENROUTER_MODEL", defaults.model)
    models = tuple(dict.fromkeys([model, *os.getenv(
        "OPENROUTER_MODELS", ",".join(defaults.models)).split(",")]))
    driver = os.getenv("CUA_DRIVER_COMMAND") or shutil.which("cua-driver")
    if not driver:
        candidate = Path.home() / ".local/bin/cua-driver"
        driver = str(candidate) if candidate.exists() else "cua-driver"
    return Config(
        api_key=os.getenv("OPENROUTER_API_KEY", ""), model=model,
        models=tuple(x.strip() for x in models if x.strip()),
        max_rounds=int(os.getenv("MAX_ROUNDS", "24")),
        turn_timeout=float(os.getenv("TURN_TIMEOUT_SECONDS", "180")), driver=driver,
    )
