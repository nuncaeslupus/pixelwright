import numpy as np
import pytest

from pixelwright.cli.commands import region_mask
from pixelwright.workspace import Asset, Workspace
from pixelwright.workspace.files import write_yaml


@pytest.fixture
def asset(ws: Workspace) -> Asset:
    a = ws.new_asset("hero", "sprite")
    a.new_version("import", files={"image.png": b"png"})
    return a


def test_masks_v1_reads_as_open_issues(asset: Asset) -> None:
    entry = {"id": "old", "file": "masks/old.png", "rule": "", "note": "", "author": "human"}
    write_yaml(asset.masks_index, {"schema": "pixelwright/masks@1", "masks": [entry]})
    [got] = asset.issues()
    assert got["status"] == "open" and got["region"] == "mask" and got["version"] is None


def test_issue_on_box_and_image_and_resolve(asset: Asset) -> None:
    asset.add_issue("dock", box=(2, 3, 4, 5), version="v0001", rule="R-PIX-3", author="claude")
    asset.add_issue("whole", version="v0001", note="too dark")
    asset.resolve_issue("dock", "v0001")
    by_id = {i["id"]: i for i in asset.issues()}
    assert by_id["dock"]["box"] == [2, 3, 4, 5] and by_id["dock"]["status"] == "fixed"
    assert by_id["dock"]["fixed_in"] == "v0001" and by_id["whole"]["region"] == "image"
    events = [h["event"] for h in asset.history()]
    assert events.count("issue_add") == 2 and "issue_resolve" in events


def test_issue_rejects_mask_and_box_together(asset: Asset) -> None:
    with pytest.raises(ValueError):
        asset.add_issue("both", png=b"x", box=(0, 0, 1, 1))


def test_region_mask_box_covers_only_the_box(asset: Asset) -> None:
    entry = asset.add_issue("b", box=(1, 2, 3, 2))
    on = region_mask(asset, entry, (6, 6))
    assert on.sum() == 6 and on[2:4, 1:4].all()
    assert region_mask(asset, asset.add_issue("all"), (6, 6)).all()
    assert isinstance(on, np.ndarray)
