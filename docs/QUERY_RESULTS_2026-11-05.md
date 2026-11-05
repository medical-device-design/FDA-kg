# Query validation, November 5, 2026

First run of the SPARQL battery against the built graphs. Until today the seven graphs had been
checked for structure only (riot, Jena SHACL, triple counts). This run answers the question
"do the graphs return correct data when queried, and do they join to each other?" for six of the
seven graphs. fda-drug-event-kg (FAERS 19.26 B triples, VAERS 0.2 B) is not in this dataset and
is still untested by query (see "Not yet tested").

## Dataset

Local TDB2 dataset on the build VM (`scripts/load_tdb2_sized.sh 140 150`, Jena 5.2.0, JVM 4 GB
because the device project's two Fuseki servers share the machine), one named graph per
shortname, `https://purl.org/okn/frink/kg/<shortname>` as on FRINK, queried with
`tdb:unionDefaultGraph=true`. Loaded 13:32 to 15:19.

| Graph | Triples in TDB2 | Triples in files | On disk |
|---|---|---|---|
| fda-compliance-kg | 79,537,972 | 79,552,561 | 29 GB |
| fda-tobacco-kg | 424,964 | 425,054 | < 1 GB |
| fda-animal-health-kg | 148,241,988 | 148,247,141 | 58 GB |
| fda-food-cosmetic-kg | 7,921,509 | 7,921,509 | 4 GB |
| fda-substance-kg | 53,082,763 | 53,716,907 | 23 GB |
| fda-drug-biologic-kg | 55,352,190 | about 59.4 M | 21 GB |
| total | 344,561,386 | | 139 GB |

TDB2 stores each distinct quad once, so a graph whose L2 stub file repeats L1 triples counts
lower in TDB2 than in its files (substance and drug-biologic). The three graphs without that
overlap match within the duplicates riot already reports.

Sizing lesson for next time: TDB2 size is driven by triple count, not by text volume. Animal
health (148 M short triples) took 58 GB, more than compliance and substance together. The
November 4 estimate (3x gzipped source) was wrong in both directions; the loader now uses 5x
gzipped size and a resume marker per graph, and the budget was raised from 100 to 140 GB with
the PI's word (300 GB stays free on the shared volume).

## Battery

45 queries, all returned rows, none errored: per graph Q0 (nodes per class) and Q0b (records
per source dataset and retrieval date), the 24 graph-specific queries in `queries/<graph>/`,
and the nine cross-graph joins in `queries/cross/`. Full output with the first 25 rows of each
query: `work/query_results_2026-11-05.md` on the VM (82 KB, copied to the Project folder).
Timing: targeted queries 0 to 12 s. Whole-graph class counts 17 s (food) to 426 s (animal
health) at 4 GB heap. These counts are not what a user would run on FRINK, they are a
completeness check.

## Checks against the sources

Every source record count the graphs carry (Q0b) was compared with the build reports and, where
openFDA has the endpoint, with the live API on November 5 (`work/openfda_reference_2026-11-05.tsv`,
`work/openfda_spotcheck_2026-11-05.txt`).

| Source | In graph (snapshot date) | openFDA live, November 5 (last_updated) | Reading |
|---|---|---|---|
| animalandveterinary/event | 1,378,854 (Oct 13) | 1,378,854 (Oct 5) | exact |
| food/event (CAERS) | 151,589 (Oct 13) | 151,589 (Jul 7) | exact |
| tobacco/problem | 1,383 (Oct 13) | 1,383 (Jul 31) | exact |
| other/substance (GSRS) | 167,385 (Oct 12) | 167,385 (Sep 9) | exact |
| drug/enforcement | 18,002 (Oct 12) | 18,076 (Oct 28) | +74 weekly reports since snapshot |
| food/enforcement | 29,471 (Oct 12) | 29,586 (Oct 28) | +115 since snapshot |
| drug/drugsfda | 29,383 (Oct 13) | 29,439 (Nov 4) | +56 since snapshot |
| drug/label | 262,897 (Oct 27) | 262,907 (Nov 5) | +10 since snapshot |
| drug/ndc | 138,419 (Oct 13) | 138,229 (Nov 4) | NDC directory is a current list, 190 delisted |
| drug/shortages | 1,579 (Oct 13) | 1,597 (Nov 5) | +18 since snapshot |
| other/unii | 173,130 (Oct 12) | 176,976 (Nov 5) | UNII list refreshed Nov 5 |

Data Dashboard, Import Alert, Product Code Builder, debarment, disqualification, warning letter,
Green Book and fdcc inventory counts match the build reports exactly (for example 344,801
inspection classifications, 282,639 citations, 178,208 compliance actions, 211,920 import
refusals, 277,629 inspections, 3,041,333 product codes, 154 import alerts, 157 debarments,
232 disqualifications, 2,428 Green Book applications). Firm nodes: 317,864 = 308,281 Dashboard
firms + 9,583 stubs, exactly.

Spot checks of query answers against the live API (same snapshot differences as above):

| Query | Graph answer | Live openFDA | Reading |
|---|---|---|---|
| compliance q1, drug recalls by class | I 1,750 / II 14,534 / III 1,716 / not yet classified 2 | 1,753 / 14,602 / 1,720 / 1 | new reports since Oct 12 and one classified |
| compliance q1, food recalls by class | I 12,968 / II 14,739 / III 1,762 / 2 | 12,994 / 14,798 / 1,793 / 1 | same |
| drug-biologic q3, shortage package 62135-486-90 | ANDA076803 CHARTWELL RX, Quinapril | application_number ANDA076803, ChartwellRX LLC, Quinapril | exact |
| cross x8, CAERS reactions, industry 54 | CHOKING 4,095, Nausea 2,423, Diarrhoea 2,314, NAUSEA 2,231, DYSPNOEA 2,225, VOMITING 2,155, Vomiting 2,152, Choking 2,108 | identical eight terms and counts | exact, including FDA's own case variants |
| tobacco q1, product problems | No information provided 773, Other 215, Foreign material 110, Taste issue 106, Damaged 80 | identical | exact |

The case variants in CAERS ("CHOKING" and "Choking") are in FDA's data and are kept verbatim
(no lossy cleaning, PI rule). A user who wants one count uses `UCASE()` in the query.

## Cross-graph joins (new today, `queries/cross/`)

| Query | What it joins | Result |
|---|---|---|
| x1 FEI firm hub | compliance Firm (FEI) with drug-biologic establishments, inspections, compliance actions | works; e.g. Eli Lilly & Company FEI 1819470: 1 establishment, 34 inspections, 3 actions |
| x2 FEI join rates | DrugEstablishment, BloodEstablishment, HctpEstablishment to Firm | 100 % resolve (9,898 / 7,482 / 5,227); 35 to 48 % land on stub firms the Dashboard does not list |
| x3 recall to substance | compliance Recall to fda-substance-kg Substance (label, CAS) | works; sodium chloride 113 drug recalls, levothyroxine 108, hydrochlorothiazide 53 (NDEA impurity recalls) |
| x4 application hub | one application IRI seen from seven drug-biologic sources | Drugs@FDA 28,125, Orange Book 27,376, NDC package 19,554, NDC product 19,492, SPL label 12,166, Purple Book 864, CRL 338 |
| x5 one application end to end | top-5 applications by product count, with labels, packages, substances, recalls of their substances | works; NDA019630 (B. Braun): 53 products, 15 packages, 3 substances, 133 recalls touching those substances |
| x6 refusals by industry | import refusals through the Product Code Builder taxonomy | Human and Animal Drugs 40,057 refusals from 15,571 firms; Tobacco 37,795 from 676 |
| x7 food inventories by CAS | 14 fdcc inventories to one GSRS substance | calcium carbonate and iron oxides appear in five inventories each |
| x8 CAERS reaction text | restored term text (l2_term_text) for dietary supplements | see spot check above |
| x9 animal events by species | within-graph count (the join to the Green Book applications is still to be written) | Dog 1,001,380, Cat 151,164, Cattle 31,358, Horse 18,674 |

Observations for the next revision (query or documentation, no data change needed):

- x3 shows a substance twice when GSRS carries two preferred-name spellings ("SODIUM CHLORIDE",
  "Sodium Chloride"). Use `SAMPLE(?label)` or the UNII in the query.
- compliance q3 shows "Dole Fresh Vegetables Inc", "Inc." and ", Inc." as three firms with the
  same counts: name-keyed firm nodes are verbatim by design. Identity resolution across name
  variants is a later layer (the device graph's reified mapping approach), not a fix to L1.
- Recall nodes: 47,472, one fewer than the two enforcement feeds' records (18,002 + 29,471);
  one recall number appears in both feeds and lands on one node, which is the intended behavior.
- Drug labels: 262,897 nodes against 262,902 raw records (five repeated set_ids in the snapshot).
- "Not Yet Classified" recalls: 2 in the snapshot, 1 live; the graph is a snapshot and says so
  (`ex:retrievedAt` on every record).

## Not yet tested

- fda-drug-event-kg: FAERS (19.26 B triples) does not fit a local TDB2 under the shared VM's
  space rules; VAERS (201 M triples, about 80 GB by today's ratio) could be loaded in a second
  round if the PI raises the budget again. Both files pass riot and SHACL; the reaction-text
  restore was verified record by record (CHANGES_2026-11-04.md). Joins from FAERS drug entries
  to fda-drug-biologic-kg applications and NDCs are still to be run, on a sampled chunk.
- A join to the Medical Device Design KG (shared FEI firm keys, UNII) against its live SPARQL
  endpoint is planned next.
- Performance on FRINK's own store will differ from these TDB2 timings.

## Files

- `scripts/load_tdb2_sized.sh` (budget, reserve, 5x estimate, resume markers), `scripts/run_queries.sh`
- `queries/cross/x1..x9*.rq`
- VM: `logs/load_tdb2_sized_run1.log`, `logs/load_tdb2_sized.log`, `logs/run_queries.log`,
  `work/query_results_2026-11-05.md`, `work/openfda_reference_2026-11-05.tsv`,
  `work/openfda_spotcheck_2026-11-05.txt`
