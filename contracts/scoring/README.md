# contracts/scoring/

Owner: Person 3 (horizon matcher and location quality).

The shared scorer (P3-09, reviewed by Person 2): position error in ground metres, heading error wrapping at 360°, median, and the share within 1, 5 and 10 m (exactly 5 m counts as within 5 m), split by terrain type. Every test summary is written through it.

```python
from contracts.scoring import score_fix, write_test_summary

scored = [
    score_fix(fix, true_position, true_heading_deg) for fix, true_position, true_heading_deg in ...
]
write_test_summary(scored, test="horizon-gale", script=Path(__file__), inputs=[answer_key, ...])
```

- `score_fix` fills a fix result's `truth` with the answer-key position and heading and the errors. Position error is rounded to the millimetre, so floating-point noise at large map coordinates can't push a fix that is exactly on a limit outside it.
- `write_test_summary` writes `results/<method>/<test>.json`, with the median and within-1/5/10 m numbers overall, for each terrain type, and for any `extra_groups` (a name and its photo ids, e.g. `{"hard_mode": [...]}` for P2-06 or `{"hollow": [...]}` for P3-03), and `provenance` (the script, the commit, and the SHA-256 of every input). Input paths are recorded relative to the repo, or to `REDMARK_DATA` for data files.
- It refuses unscored fixes, a mix of sites, methods or simulated and real fixes, and a test with no fixes of one terrain type (the schema needs both groups).
- A simulated summary has no time per fix (`null`), as the schema says.

Tests: `uv run pytest contracts/scoring`.
