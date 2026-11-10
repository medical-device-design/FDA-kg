# Gap query results, November 9, 2026

Closes the three gaps left after the November 7 and 8 fixes: VAERS queried on the rebuilt files,
the rebuilt import alerts queried in a store, and the rewritten cross queries x3 and x7 run for the
first time. Each result is checked against the raw source or the published Turtle, not only against
the store.

Store: fresh TDB2 on the build VM with four named graphs loaded from the files now on lakeFS `main`
(fda-drug-event-kg VAERS part, fda-compliance-kg, fda-substance-kg, fda-food-cosmetic-kg),
257.5 M triples, 118 GB. Loaded counts equal the file totals (VAERS 169,488,056, compliance
79,552,561, food-cosmetic 8,481,045). 15 queries, all returned without error. Script and raw checks
on the VM under `work/gaps/`, log `logs/gaps_2026-11-09.log`.

## Verdict

| Check | Expected | Store | Raw source | Result |
|---|---|---|---|---|
| VaersVaccination nodes | one per VAX row | 3,444,928 | 3,444,928 VAX rows | pass |
| VaersSymptomSet nodes | one per SYMPTOMS row | 3,774,947 | 3,774,947 | pass |
| VaersReport nodes | distinct VAERS_ID | 2,736,357 | 2,736,357 | pass |
| Vaccination nodes with two vaccine types (collision symptom) | 0 | 0 | | pass |
| Symptom text on undeclared nodes | 0 | 0 of 3,774,947 | | pass |
| Report 0025006 | 4 vaccinations, each with its own lot | 4 nodes, TD lot 247953 on the TD rows only | | pass |
| q9 vaccinations by manufacturer and type, top 15 | equal to raw tallies | identical on all 15 rows | VAX CSVs read directly | pass |
| Import alert repeat listings now separate | 265 firms, 1,261 products | 265, 1,261 | | pass |
| Firm products with two product codes (collision symptom) | 0 | 0 of 128,106 | old file 164 of 127,010, new file 0 | pass |
| Import alert class counts | same as the file | 154 alerts, 580 scope rows, 24,164 firms, 128,106 products | | pass |
| x3 row 1 (Sodium Chloride, UNII 451W47IQ8X) | equal to Turtle recount | 113 drug recalls | 113 Recall blocks in the enforcement files | pass |
| x7 row 1 (Calcium Carbonate, UNII H0G9379FGK) | equal to Turtle recount | 5 inventories | the same 5 classes in the food-cosmetic files | pass |

## What changed in the answers

- **q9 (VAERS vaccinations by manufacturer)** now counts every vaccination row once. Under the old
  IRIs, collided rows merged onto one node, which undercounted some pairs and overcounted others
  (a merged node carrying two manufacturer and type pairs was counted under every combination of
  them). Pfizer-BioNTech COVID-19 was 995,749 and is now 1,027,101 (+3.1 %), Moderna 560,198 to
  583,644, Janssen 102,550 to 102,931, GSK Shingrix (VARZOS) 87,780 to 89,844, while Merck
  varicella (VARCEL) went down, 89,051 to 88,858. All 15 rows now equal the raw CSV counts exactly.
- **q7, q8, q10** give the same answers as on November 7. They count reports or symptom terms,
  which the collision did not change.
- **x3** (top substances in drug recalls): Sodium Chloride 113, Levothyroxine Sodium 108,
  Hydrochlorothiazide 53, Acetaminophen 52, Valsartan 48 (nitrosamine impurity recalls visible in
  the example reasons). One row per substance.
- **x7** (substances across food inventories): Calcium Carbonate and Ferric Oxide Red each appear
  in 5 inventories (CEDI, color additives, food substances, indirect additives, SCOGS).
- **Import alerts**: Fromagerie Delin under Import Alert 12-03 (green list) is now two entries,
  2022-04-21 with 6 products and 2009-09-18 with 1 product, where the old file merged them.

## Status of query validation after this run

| Graph | Queried | Against |
|---|---|---|
| fda-substance-kg, fda-compliance-kg, fda-drug-biologic-kg, fda-food-cosmetic-kg, fda-animal-health-kg, fda-tobacco-kg | in full, November 5, plus this run for compliance, substance, food-cosmetic | raw files and live openFDA |
| fda-drug-event-kg VAERS | in full, on the files now on `main` | raw VAERS CSVs |
| fda-drug-event-kg FAERS | 0.9 % sample in a store, all 20.7 M reports for link resolution | live openFDA, declared node lists |
| Cross-graph x1 to x9 | all run at least once, x3 and x7 in their current form | Turtle recounts |

Remaining before the tag: the same suite against FRINK's own endpoints once the build is up, which
also covers full FAERS and the federated join to medical-device-kg.
