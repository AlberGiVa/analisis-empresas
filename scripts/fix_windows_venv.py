"""Repair the uv virtual environment on Windows machines whose antivirus blocks unknown executables.

uv creates ``.venv/Scripts/python.exe`` as a small launcher. Endpoint-protection products that
only allow executables they already know (such as Panda Adaptive Defense in lock mode) block it,
so nothing in the environment can run. This script replaces the launcher with byte-identical
copies of the base interpreter, which the antivirus already allows, plus the DLLs it needs.
CPython still detects the virtual environment through ``.venv/pyvenv.cfg``.

Usage from the project folder (PowerShell), after ``uv sync`` has created ``.venv``::

    & (uv python find --system 3.12) scripts/fix_windows_venv.py
"""

import shutil
import sys
from pathlib import Path

RUNTIME_FILES = (
    "python.exe",
    "pythonw.exe",
    "python3.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll",
)


def read_home(venv_dir: Path) -> Path:
    """Return the base interpreter folder recorded in ``pyvenv.cfg``."""
    config = venv_dir / "pyvenv.cfg"
    for line in config.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip().lower() == "home":
            return Path(value.strip())
    raise ValueError(f"{config} no indica la carpeta 'home' del intérprete base")


def runtime_files(home: Path) -> list[Path]:
    """Executables and DLLs that must sit next to a copied ``python.exe``."""
    files = [home / name for name in RUNTIME_FILES if (home / name).is_file()]
    files.extend(sorted(home.glob("python3??.dll")))  # versioned runtime, e.g. python312.dll
    return files


def repair(venv_dir: Path) -> list[Path]:
    """Copy the base interpreter files into the environment's ``Scripts`` folder."""
    scripts_dir = venv_dir / "Scripts"
    copied = []
    for source in runtime_files(read_home(venv_dir)):
        target = scripts_dir / source.name
        shutil.copy2(source, target)
        copied.append(target)
    return copied


def main() -> int:
    venv_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".venv")
    if not (venv_dir / "pyvenv.cfg").is_file():
        print(f"No hay un entorno virtual en {venv_dir}; ejecuta antes 'uv sync'.")
        return 1
    for path in repair(venv_dir):
        print(f"Copiado: {path}")
    print("Entorno reparado. Comprueba con: uv run python --version")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
