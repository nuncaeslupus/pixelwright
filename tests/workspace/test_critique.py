import pytest

from pixelwright.workspace import critique
from pixelwright.workspace.critique import Complaint, Critique
from pixelwright.workspace.schema import SchemaError


def test_critique_roundtrip_keeps_verdict_and_issue_links() -> None:
    c = Critique(
        "v0004",
        "Better values; more noise on the dock.",
        "v0003",
        [
            Complaint("Dock edge orphans", "dock-orphans", "R-PIX-3", "Three 1-px clusters."),
            Complaint("Moon holds", rule="R-VAL-1"),
        ],
    )
    back = critique.parse(critique.render(c))
    assert back == c


def test_critique_without_front_matter_is_refused() -> None:
    with pytest.raises(SchemaError):
        critique.parse("## just text\n")
