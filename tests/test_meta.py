import tomllib
from pathlib import Path

import pixelwright

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def test_package_import_version_matches_pyproject() -> None:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert pixelwright.__version__ == project["version"]
