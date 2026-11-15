# The provider benchmark

Which painter is worth paying for? The benchmark answers it with your own briefs.

1. Edit `benchmarks/matrix.yaml`: providers, post-processing chains, briefs, samples.
2. `pw bench run --matrix benchmarks/matrix.yaml` prints the cost per brief and provider
   and sends nothing. Missing keys are flagged. Add `--yes` to run it; it stops before
   spending if the estimate is over the matrix cap (20 USD) or the month's budget.
3. Vote. Claude votes with `pw bench pair` and `pw bench vote` (it may see file names).
   You vote blind: `pw view`, then open `http://127.0.0.1:<port>/blind?b=<name>`. Two
   results of the same brief, no names; keys `1` left, `2` right, `0` about the same.
4. `pw bench rank` ranks each provider + chain with Bradley-Terry; `pw bench report`
   writes `benchmarks/<name>/report.html` with the human, Claude and combined rankings
   and the mean failing checks.
5. `pw bench apply` sets `[defaults]` in `pixelwright.toml` to the winner (your blind votes
   first, all votes when you have none), so `pw generate` uses it without `--provider`.
