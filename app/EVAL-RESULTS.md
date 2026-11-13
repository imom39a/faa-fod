# Evaluation summary (full pipeline)

Run at 2026-11-13T13:29:35-0800 on 30 Inspection(s) from `/Users/vinothshanmugam/code/anthropic-basecamp/faa-fod/app/data`. Scored: Findings.

## Targets

| Target | Bound | Measured | Met |
|---|---|---|---|
| NF-1 cost per Inspection (USD) | <= 0.05 | 0.00828 | yes |
| NF-2 seconds per Inspection | <= 20.0 | 8.7 | yes |
| NF-3 recall overall | >= 0.9 | 1.0 | yes |
| NF-3 recall in Critical zones | >= 0.95 | 1.0 | yes |
| NF-3 false alarms per clean Angle | <= 0.5 | 0.0956 | yes |

## Detection

| Angles | n | Recall (Findings) | Recall, Critical zones | False alarms on clean Angles (per Angle) |
|---|---|---|---|---|
| All | 180 | 42/42 (100.0%) | 23/23 (100.0%) | 13 on 136 (0.0956) |
| Native | 22 | 6/6 (100.0%) | 0/0 (n/a) | 0 on 16 (0.0) |
| Mirrored or cropped | 158 | 36/36 (100.0%) | 23/23 (100.0%) | 13 on 120 (0.1083) |

## Other measures

- Severity agreement on matched Findings: 90.5% of 42.
- Unusable Angles detected: 2/2; usable Angles wrongly marked unusable: 0.
- Inspections whose list of missing Angles is exactly right (INCOMPLETE correctness): 100.0%.
- Equipment staging (FOD-R9): 2/2 located, 2 reported as equipment staging.
- Latency per Inspection: mean 8.7 s, median 8.79 s, max 13.92 s.
- Verdict correct: 93.3%.
- Cost per Inspection: mean $0.00828, max $0.01573 (uncached price). Actually spent in this run: $0.24272 (cache hits are free).

## Missed objects

None.

## False alarms on clean Angles

- pa-001 WIDE: passenger stairs inside the equipment restraint line before arrival at [343, 1121, 797, 1725]
- pa-001 WIDE: safety cone inside the equipment restraint line before arrival at [2636, 1288, 2698, 1395]
- pa-001 WIDE: marker cone inside the equipment restraint line before arrival at [1907, 1080, 1963, 1172]
- pa-001 WIDE: marker cone inside the equipment restraint line before arrival at [2222, 1082, 2267, 1179]
- pa-001 WIDE: yellow ground hose reel inside the equipment restraint line before arrival at [720, 1380, 936, 1461]
- pa-003 WIDE: safety cone inside the equipment restraint line before arrival at [1163, 592, 1180, 636]
- pa-003 WIDE: safety cone inside the equipment restraint line before arrival at [1181, 600, 1200, 662]
- pa-003 WIDE: wheel chock or small equipment inside the equipment restraint line before arrival at [1130, 626, 1182, 665]
- pa-006 WIDE: passenger stairs inside the equipment restraint line before arrival at [343, 1121, 797, 1725]
- pa-006 WIDE: safety cone inside the equipment restraint line before arrival at [2636, 1288, 2698, 1395]
- pa-006 WIDE: marker cone inside the equipment restraint line before arrival at [1907, 1080, 1963, 1172]
- pa-006 WIDE: marker cone inside the equipment restraint line before arrival at [2222, 1082, 2267, 1179]
- pa-006 WIDE: yellow ground hose reel inside the equipment restraint line before arrival at [720, 1380, 936, 1461]

## Limits to state with these results

- Debris is composited, and reference frames are simulated with nothing moving between frames.
- No Concourse T imagery: the photos are stand-ins.
- Detector thresholds were fixed on the 22-frame spike set and not re-tuned here.
