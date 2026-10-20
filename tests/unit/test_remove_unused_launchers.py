import importlib.util
from pathlib import Path
from types import ModuleType

from company_analysis.settings import PROJECT_ROOT


def load_script() -> ModuleType:
    path = PROJECT_ROOT / "scripts" / "remove_unused_launchers.py"
    spec = importlib.util.spec_from_file_location("remove_unused_launchers", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_the_used_executables_are_kept(tmp_path: Path) -> None:
    for name in (
        "python.exe",
        "pythonw.exe",
        "ruff.exe",
        "pytest.exe",
        "streamlit.exe",
        "activate",
    ):
        (tmp_path / name).write_bytes(b"x")
    removed = load_script().remove_unused_launchers(tmp_path)
    assert sorted(path.name for path in removed) == ["pytest.exe", "streamlit.exe"]
    remaining = sorted(path.name for path in tmp_path.iterdir())
    assert remaining == ["activate", "python.exe", "pythonw.exe", "ruff.exe"]
