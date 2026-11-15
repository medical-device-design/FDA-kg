# Query validation on FRINK, November 15, 2026

First run of the query battery against the live FRINK endpoints. FRINK converted five of the
seven graphs on November 13 (`stable_v0_0_1`), and they were tagged `v0.0.1` on November 15,
2026. This run answers the question "do the released graphs return the same answers on FRINK
as on our local store?" The local results are in QUERY_RESULTS_2026-11-05.md and
QUERY_RESULTS_2026-11-09_gaps.md.

## Release

| Graph | `v0.0.1` commit | Endpoint total | VoID data triples | Distinct triples in our files |
|---|---|---|---|---|
| fda-tobacco-kg | 01dfca23 | 429,627 | 424,964 | 424,964 |
| fda-food-cosmetic-kg | c101274b | 7,931,139 | 7,921,509 | 7,921,509 |
| fda-substance-kg | b08c82ca | 53,088,197 | 53,082,763 | 53,082,763 |
| fda-compliance-kg | dd4e1919 | 79,554,005 | 79,548,836 | 79,548,836 |
| fda-animal-health-kg | 2c6d91f2 | 148,251,828 | 148,241,988 | 148,241,988 |

Each `stable_v0_0_1` branch was built from the current `main` of its repository, and the source
files are the same. The distinct-triple count was computed on the build VM (riot to N-Triples,
`sort -u`) from the files on `main`. It equals FRINK's VoID count for all five graphs. The
earlier "triples in files" numbers were sums of per-file counts, so a triple repeated across files
(L2 stub files repeat some L1 triples) was counted more than once. The endpoint total is higher
than the data count by FRINK's VoID metadata, which is loaded into the same index (4,663 triples
for tobacco, checked by query).

The compliance distinct count was first run against an old local copy of the import alerts file
and came out 10,864 short. Rerun against `import_alerts_v2.ttl`, the file uploaded to lakeFS as
`import_alerts.ttl` on November 8, it matches exactly.

## Battery

29 queries, all returned rows, none errored: Q0 (nodes per class) and Q0b (records per source
dataset and retrieval date) for each graph, the 15 graph-specific queries in `queries/<graph>/`
for these five graphs, and the four import alert checks in `queries/gaps/i*.rq`. Each per-graph
endpoint (`https://apps.okn.us/<shortname>/sparql`) serves one graph as its default graph, so
the queries run unchanged. Runner: `scripts/run_frink.py`. Most queries returned in under 0.5 s,
the slowest in 4.5 s (animal-health q1), against 17 to 426 s on the local TDB2 store.

The endpoints rate-limit parallel requests (HTTP 429 from frink-throttle). The runner sends one
query at a time with a 3 s pause and retries a 429 with backoff.

## Checks against the November 5 results

| Query | FRINK | November 5 (local store) | Reading |
|---|---|---|---|
| tobacco Q0b, tobacco/problem | 1,383 | 1,383 | exact |
| tobacco q1, top five problems | 773, 215, 110, 106, 80 | 773, 215, 110, 106, 80 | exact |
| food-cosmetic Q0b, food/event | 151,589 | 151,589 | exact |
| food-cosmetic q3, reports with reactions | CAERS 151,589, cosmetic 85,511 | same | exact |
| substance Q0b | GSRS 167,385, UNII 173,130 | 167,385, 173,130 | exact |
| compliance q1, drug recalls I / II / III / not yet classified | 1,750 / 14,534 / 1,716 / 2 | same | exact |
| compliance q1, food recalls I / II / III / not yet classified | 12,968 / 14,739 / 1,762 / 2 | same | exact |
| compliance Q0b, Data Dashboard | 308,281 firms, 277,629 inspections, 282,639 citations, 344,801 classifications, 178,208 compliance actions, 211,920 import refusals | same | exact |
| compliance Q0b, other sources | 3,041,333 product codes, 157 debarments, 232 disqualifications, 2,658 warning letters | same | exact |
| gaps i1, import alert classes | 154 alerts, 580 scope rows, 24,164 firms, 128,106 products | same (November 9) | exact |
| gaps i2, repeat listings | 265 firms, 1,261 products | same (November 9) | exact |
| gaps i3, products with two codes | 0 | 0 (November 9) | exact |
| animal-health Q0b | 1,378,854 events, 2,428 Green Book applications | same | exact |
| animal-health q2, top reaction | Vomiting (VeDDRA 334), 216,021 | same | exact |

## Not yet tested on FRINK

- Cross-graph joins (`queries/cross/x1` to `x9`). They need the federated endpoint, which did
  not include the five graphs on November 15 (a scoped count returned 0). Most of them also use
  fda-drug-biologic-kg.
- fda-drug-biologic-kg and fda-drug-event-kg. Both are on `main`, but FRINK's convert-to-hdt
  webhook returned HTTP 500 on their merges (November 9 and November 8), and no
  `stable_v0_0_1` branch exists yet. A restart was requested from FRINK.

## Files

- `scripts/run_frink.py` (runner, one query at a time, 429 backoff)
- VM: `work/frinkq/results_fda-compliance-kg_fda-animal-health-kg.md`, `work/voidcheck/result.tsv`,
  `work/voidcheck/c2.count`
