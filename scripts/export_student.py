"""Build a student distribution from an explicit allowlist (progressive answers included, no secrets)."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]


def export(destination=None):
    destination = destination or ROOT / "dist/comma-mini-agent-student.zip"
    destination.parent.mkdir(parents=True, exist_ok=True)
    paths = [ROOT / x for x in ["README.md", "THIRD_PARTY_NOTICES.md", "pyproject.toml", "uv.lock", ".env.example", ".gitignore",
                              "scripts/practice_server.py", "scripts/check_student.py"]]
    for folder in ["common", "lesson_01_agent", "lesson_02_computer_use", "docs/student"]:
        paths.extend(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    paths.extend(ROOT / x for x in ["tests/__init__.py", "tests/test_policy.py"])
    with ZipFile(destination, "w", ZIP_DEFLATED) as z:
        for path in sorted(set(paths)):
            if not path.exists():
                raise FileNotFoundError(path)
            z.write(path, "comma-mini-agent/" + path.relative_to(ROOT).as_posix())
    return destination


if __name__ == "__main__":
    print(export())
