import tomllib
from pathlib import Path

import pixelwright

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_import_version_matches_pyproject() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert pixelwright.__version__ == project["version"]


def test_no_workspace_package() -> None:
    """The M0-M3 workspace is gone; `pw migrate` reads old folders on its own."""
    assert not (Path(pixelwright.__file__).parent / "workspace").exists()
