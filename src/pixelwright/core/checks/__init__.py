"""Pixel-fact detectors. Each returns a `CheckResult`; Claude interprets them."""

from pixelwright.core.checks.base import CheckResult, read_report, write_report
from pixelwright.core.checks.focal_contrast import check_focal_contrast
from pixelwright.core.checks.grid import check_grid
from pixelwright.core.checks.orphans import check_orphans
from pixelwright.core.checks.palette import check_palette
from pixelwright.core.checks.value_groups import check_value_groups

__all__ = [
    "CheckResult",
    "check_focal_contrast",
    "check_grid",
    "check_orphans",
    "check_palette",
    "check_value_groups",
    "read_report",
    "write_report",
]
