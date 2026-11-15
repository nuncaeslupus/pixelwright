---
id: t-d46cbcb5
title: "T39: doctor"
label: "T39: doctor"
priority: 10
deps: [t-db735791]
tags: [m3]
status: merged
---

table output plus `--json`; each failing row says how to fix it.

## Acceptance gate
Gate metric (from the plan): `make_check_exit_code == 0`. The tests below assert that threshold; the block fails if it does not hold.

```bash
make check
uv run pytest tests/cli/test_doctor.py -q
```

## Tests
`test_doctor_reports_missing_key_with_env_var_name` in `tests/cli/test_doctor.py` — a provider without key shows `PW_<NAME>_KEY`

## Location
cli
