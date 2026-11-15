from pathlib import Path

import pytest

from pixelwright.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    return Workspace.init(tmp_path / "ws")
