"""Generation commands (M3): cost, and later generate, regen-region, doctor, next, tour."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pixelwright.cli.registry import Outcome, Param, PwError, command
from pixelwright.workspace import Workspace
from pixelwright.workspace.budget import Ledger, monthly_limit


@command(
    "cost",
    "money spent on providers this month, against the workspace budget",
    Param("month", help="month YYYY-MM (default: this month)"),
    Param("by", help="group rows by", choices=("provider", "asset")),
)
def cmd_cost(root: Path, a: dict[str, Any]) -> Outcome:
    ws = Workspace.open(root)
    month = a["month"] or datetime.now(UTC).strftime("%Y-%m")
    if len(month) != 7 or month[4] != "-":
        raise PwError("invalid", f"month must be YYYY-MM, got {month!r}")
    ledger = Ledger(ws.root)
    rows = ledger.rows(month)
    data: dict[str, Any] = {
        "month": month,
        "spent_usd": ledger.spent(month),
        "limit_usd": monthly_limit(ws.config),
        "calls": len(rows),
        "cache_hits": sum(1 for r in rows if r["cache_hit"]),
    }
    if a["by"]:
        groups: dict[str, float] = defaultdict(float)
        for r in rows:
            groups[str(r[a["by"]] or "-")] += float(r["cost_usd"])
        data["rows"] = [{a["by"]: k, "cost_usd": round(v, 6)} for k, v in sorted(groups.items())]
    else:
        data["rows"] = rows
    return Outcome(data=data)
