import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from company_analysis.settings import PROJECT_ROOT


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "fix_windows_venv.py"
    spec = importlib.util.spec_from_file_location("fix_windows_venv", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_install(tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "base-python"
    home.mkdir()
    for name in ("python.exe", "pythonw.exe", "python3.dll", "python312.dll", "vcruntime140.dll"):
        (home / name).write_bytes(f"original {name}".encode())
    venv = tmp_path / ".venv"
    (venv / "Scripts").mkdir(parents=True)
    (venv / "Scripts" / "python.exe").write_bytes(b"blocked launcher")
    (venv / "pyvenv.cfg").write_text(f"home = {home}\nversion_info = 3.12\n", encoding="utf-8")
    return home, venv


def test_repair_replaces_launcher_with_base_interpreter_files(
    fake_install: tuple[Path, Path],
) -> None:
    home, venv = fake_install
    copied = load_script().repair(venv)
    names = sorted(path.name for path in copied)
    assert names == [
        "python.exe",
        "python3.dll",
        "python312.dll",
        "pythonw.exe",
        "vcruntime140.dll",
    ]
    assert (venv / "Scripts" / "python.exe").read_bytes() == (home / "python.exe").read_bytes()


def test_read_home_requires_the_home_key(tmp_path: Path) -> None:
    (tmp_path / "pyvenv.cfg").write_text("version_info = 3.12\n", encoding="utf-8")
    with pytest.raises(ValueError, match="home"):
        load_script().read_home(tmp_path)
