"""Delete the launcher executables that uv generates in .venv/Scripts and the project never uses.

When uv installs packages on Windows it creates a small .exe for each of their command-line tools
(pytest.exe, mypy.exe, streamlit.exe…): a generic launcher with a few lines of Python appended.
Corporate antivirus software flags them as unknown programs. The project never runs them: every
command executes the Python code directly with ``python -m``. Run this script after ``uv sync``
installs or updates packages.

Usage: uv run python scripts/remove_unused_launchers.py
"""

import sys
from pathlib import Path

# Executables that are used and digitally signed: the interpreter (Python Software Foundation)
# and the linter.
KEEP = frozenset({"python.exe", "pythonw.exe", "ruff.exe"})


def unused_launchers(scripts_dir: Path) -> list[Path]:
    return sorted(path for path in scripts_dir.glob("*.exe") if path.name.lower() not in KEEP)


def remove_unused_launchers(scripts_dir: Path) -> list[Path]:
    removed = unused_launchers(scripts_dir)
    for path in removed:
        path.unlink()
    return removed


def main() -> int:
    scripts_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".venv") / "Scripts"
    if not scripts_dir.is_dir():
        print(f"No existe {scripts_dir} (solo hace falta en Windows).")
        return 0
    removed = remove_unused_launchers(scripts_dir)
    for path in removed:
        print(f"Borrado: {path.name}")
    print(
        f"{len(removed)} lanzadores sin uso borrados."
        if removed
        else "No había lanzadores sin uso."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
