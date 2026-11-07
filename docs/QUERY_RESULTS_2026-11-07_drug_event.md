# Query validation of fda-drug-event-kg (FAERS sample), November 7, 2026

Follow-up to `QUERY_RESULTS_2026-11-05.md`, which covered the six smaller graphs. This run puts a
contiguous FAERS sample into the same TDB2 dataset as the named graph
`https://purl.org/okn/frink/kg/fda-drug-event-kg` and runs the first queries against it, including
joins into fda-drug-biologic-kg, fda-substance-kg and fda-compliance-kg. VAERS was not loaded in
this first pass; it was loaded and queried in full later the same day (see the addendum). Script: `scripts/test_drug_event.sh` (VM only); queries: `queries/fda-drug-event-kg/`.

## Sample

The first 7.0 GB of the uncompressed `drug_event.ttl.gz` stream (the file is written one report at
a time, so this is 187,643 complete reports, receive dates 2001 to 2012, mostly 2004 and 2005),
cut at the last record boundary, plus the reaction text for exactly those reports filtered out of
`l2_term_text_faers.ttl.gz` (624,521 texts for 623,962 FaersReaction nodes). 122.9 M triples,
44 GB in TDB2 (0.36 GB per million triples, as on November 5; the 20 GB estimate was wrong).
Nodes: 187,642 AdverseEventReport, 187,642 FaersPatient, 630,032 FaersDrug, 623,962 FaersReaction,
362,850 FaersOpenfda, 13,983 FaersPatientdeath. Provenance: `drug/event`, retrieved 2026-10-27.

## Results

| Query | Result | Time |
|---|---|---|
| q1 reports by receive year | 2001 1, 2002 6, 2003 6, 2004 154,693, 2005 29,219, 2006 1,825 ... 2012 38 | 18 s |
| q2 top reaction terms (restored text) | NAUSEA 9,006, DRUG INEFFECTIVE 7,573, DIZZINESS 6,801, HEADACHE 6,354, VOMITING 6,028, DYSPNOEA 5,942, DEATH 5,526 | 22 s |
| q3 report structure, three reports | report -> patient -> drug and reaction nodes resolve; reaction text attached; serious flag and dates typed | 6 s |
| q4 FAERS to Drugs@FDA application | NDA021318 (Lilly) 6,558 reports, NDA016273 5,547, BLA125057 (AbbVie) 5,350; a run of ANDAs at 5,026 each are the prednisone applications: openFDA's harmonized block lists every application for a generic, so one report links to all of them, which is faithful to the source | 49 s |
| q5 link rates | application: 138,454 reports, 8,511 targets, all typed DrugApplication. package NDC: 140,318 reports, 89,849 targets, 89,847 typed (2 package NDCs have no node). substance (UNII): 137,843 reports, 1,773 targets, all typed Substance | 564 s |
| q6 three hops FAERS -> substance -> recalls | aspirin 7,615 reports, 5 recalls; furosemide 5,547, 7; levothyroxine 5,378, 108; acetaminophen 4,980, 52; atorvastatin 4,824, 46 | 89 s |
| Q0 class counts, Q0b provenance | as above | 51 s, 28 s |

Three sampled reports (first, middle, last) against the live openFDA API on November 7: receive
date, serious flag, drug count, reaction count and the reaction terms are identical for all three
(3749714: 3 drugs, 6 reactions, "Gastric cancer; Lethargy; Rash; Weight decreased; Autoimmune
disorder; Depression"; 4437265-6: 6 drugs, 1 reaction "DYSPHAGIA"; 8473122-6: 1 drug, 2 reactions
"PHARYNGEAL OEDEMA; CHEST DISCOMFORT"). Safety report ids with a suffix ("4437265-6") are slugged
to "4437265_6" in the IRI and kept verbatim in `ex:safetyreportid`.

## What this shows

- The FAERS L1 structure queries correctly: report, patient, drug, reaction and openfda nodes,
  typed dates, serious flags, and the restored MedDRA PT text on the reaction nodes.
- FAERS joins to the other graphs through the three keys the L1 pass lifted from the openfda
  block: application IRIs (100 % resolve to Drugs@FDA nodes), package NDCs (99.998 %), UNIIs
  (100 % resolve to GSRS substances). From a substance the compliance recalls are one more hop.
- Answers match the live API record for record.

## Caveats and lessons

- This is 0.9 % of FAERS (187,643 of 20.7 M reports), the oldest reports in file order. The
  structure is the same throughout (the streaming full-coverage check of November 3 covered every
  block), but counts here are not FAERS counts.
- Two package NDC IRIs referenced by sampled reports have no NdcPackage node; the stub pass was
  run on the full file, so these two are worth a look (probably a formatting variant).
- Two queries (q3, q10) failed on the first pass with "variable already in scope" because an
  aggregate reused its input variable name; fixed. q7 to q10 (VAERS) return no rows until VAERS
  is loaded.
- Disk: the device project's new dataset left 205 GB free on the shared volume on the morning of
  November 7, and the sample took 44 GB, so the volume ended at 152 GB free with our test store at
  186 GB. VAERS (about 80 GB) was not loaded for that reason. The test store can be deleted when
  the PI says so.
- Procedure: a second copy of the test was started by mistake and killed within a minute (nothing
  reached the store), and one run died after its load because the script file was replaced while
  it was executing. Both are in the logs (`logs/test_drug_event_run*.log`).

## Not done

- VAERS queries (q7 to q10): done at 11:21 after the six-graph store was deleted, see the addendum.
- The join to the Medical Device Design KG endpoint.

## Addendum, November 7, 2026, 11:21: VAERS queried in full

After the six-graph test store was archived (small files to the PI's archive drive) and deleted
with the PI's word, VAERS was loaded alone: `vaers.ttl.gz` plus `l2_term_text_vaers.ttl.gz`,
217,124,266 triples (exactly the two files' totals), 9 minutes, 56 GB (`scripts/test_vaers.sh`,
store `tdb2_vaers`). Six queries, all returned rows:

| Query | Result | Time |
|---|---|---|
| Q0 nodes per class | VaersVaccination 2,811,621, VaersSymptomSet 2,811,342, VaersReport 2,736,357 | 147 s |
| Q0b provenance | 114 source files (38 years x DATA, SYMPTOMS, VAX), all retrieved 2026-10-27 | 155 s |
| q7 reports by receive year | 1990 2,151 ... 2020 58,165, 2021 1,063,444, 2022 528,611, 2023 158,021, 2024 86,528, 2025 57,192, 2026 25,267 | 81 s |
| q8 top symptom text | Pyrexia 363,530, Headache 317,398, Fatigue 260,651, SARS-CoV-2 test 250,215, Pain 228,436, COVID-19 227,284 | 107 s |
| q9 vaccinations by manufacturer and type | PFIZER\BIONTECH COVID19 995,749, MODERNA COVID19 560,198, JANSSEN COVID19 102,550, MERCK VARCEL 89,051, GSK VARZOS 87,780 | 61 s |
| q10 three 2024 reports | report, age, state, vaccination count and symptom text all resolve through the `e:report` back-links | 34 s |

Check against the raw CSVs (`VAERSDATA.csv` in the two snapshot zips, read directly):

- Rows: 2,811,621 across the yearly files and the NonDomestic file. Distinct VAERS_IDs: 2,736,357,
  which is exactly the VaersReport node count. 51,278 rows repeat a VAERS_ID inside one file and
  23,628 ids appear in more than one file (127 NonDomestic ids also in a yearly file); the IRI is
  keyed by VAERS_ID, so these land on one node each, with every value kept.
- Per year, graph vs raw rows: 1990 2,151 vs 2,214 (2,102 distinct ids in the 1990 file plus 49
  reports from other files received in 1990), 2021 1,063,444 vs 768,704 domestic rows (the
  rest are NonDomestic reports received in 2021). Consistent once the two effects are allowed for.
- Correction to earlier documents: the "3,622,202 reports" figure was a row count that counted
  the NonDomestic CSV twice, because `NonDomesticVAERSDATA.csv` is inside both snapshot zips
  (`AllVAERSDataCSVS.zip` and `NonDomesticVAERSDATA.zip`) and the L1 build read both. The
  triples it produced are identical, so any store deduplicates them and the graph is unaffected,
  but the file total (200.9 M triples) includes that repeat and the next build should read the
  NonDomestic CSV once. The correct figures: 2,736,357 distinct VAERS reports, 2,811,621 vaccination
  rows, 2,811,342 symptom sets.

With this, every one of the seven graphs has been queried: six in full, FAERS on a 0.9 % sample,
VAERS in full. The VAERS store (56 GB) stays on the VM until the PI says otherwise.
