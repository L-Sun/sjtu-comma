"""Load the saved exercise directly, without stale Python bytecode caches."""
import hashlib
from pathlib import Path
import sys
from types import ModuleType


def load_student_agent(source: str, path: Path):
    name = 'lesson_01_agent._saved_agent'
    module = ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = 'lesson_01_agent'
    module.source_version = hashlib.sha256(source.encode('utf-8')).hexdigest()
    sys.modules[name] = module
    exec(compile(source, str(path), 'exec'), module.__dict__)
    return module
