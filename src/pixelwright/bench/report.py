"""`report.html`: the benchmark on one self-contained page (rankings and detector scores)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from pixelwright.bench.rank import items, votes

STYLE = """body{font:15px/1.5 system-ui,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;
color:#22262b;background:#f4f6f8}h1{font-size:22px}h2{font-size:17px;margin-top:28px}
table{border-collapse:collapse;width:100%;background:#fff;border-radius:10px;overflow:hidden}
th,td{padding:7px 10px;text-align:left;border-bottom:1px solid #e3e6ea}th{color:#6c737c;
font-weight:600}td.n{text-align:right;font-variant-numeric:tabular-nums}
@media (prefers-color-scheme:dark){body{background:#18191b;color:#e6e8eb}
table{background:#222427}th,td{border-color:#33363a}}"""

TITLES = {"human": "Blind human votes", "claude": "Claude's votes", None: "All votes"}


def _table(rows: list[dict[str, Any]]) -> str:
    head = "<tr><th>#</th><th>Provider</th><th>Chain</th><th>Strength</th><th>Votes</th>"
    head += "<th>Failing checks (mean)</th></tr>"
    body = "".join(
        f"<tr><td class=n>{i + 1}</td><td>{html.escape(r['provider'])}</td>"
        f"<td>{html.escape(r['chain'])}</td><td class=n>{r['strength']:.3f}</td>"
        f"<td class=n>{r['games']}</td><td class=n>{r['mean_fails']}</td></tr>"
        for i, r in enumerate(rows)
    )
    return f"<table>{head}{body}</table>"


def write_report(out: Path, tables: dict[str | None, list[dict[str, Any]]]) -> Path:
    rows = items(out)
    cost = sum(float(r.get("cost_usd", 0.0)) for r in rows)
    parts = [
        f"<h1>Benchmark {html.escape(out.name)}</h1>",
        f"<p>{len(rows)} results, {len(votes(out, 'human'))} human and "
        f"{len(votes(out, 'claude'))} Claude votes, {cost:.2f} USD. Strength is the "
        "Bradley-Terry share: the chance of winning against the field.</p>",
    ]
    for reader in ("human", "claude", None):
        parts.append(f"<h2>{TITLES[reader]}</h2>{_table(tables[reader])}")
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>Benchmark {html.escape(out.name)}</title><style>{STYLE}</style></head>"
        f"<body>{''.join(parts)}</body></html>"
    )
    path = out / "report.html"
    path.write_text(page, encoding="utf-8")
    return path
