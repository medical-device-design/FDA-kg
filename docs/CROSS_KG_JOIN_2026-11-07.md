# Join test against the Medical Device Design KG, November 7, 2026

Question: do the FDA regulated-products graphs connect to the medical-device-kg already live on
FRINK, and on which key? Answer: yes, on the FDA Establishment Identifier (FEI), with no
transformation needed on either side.

## Method

Live endpoint `https://apps.okn.us/medical-device-kg/sparql` (the device graph as served on
November 7, 2026: MAUDE 25.4 M reports, UDI 5.2 M device records, registration and listing
establishments) queried from the build VM with `curl`; our side read straight from the published
Turtle files (`fda-compliance-kg/data_dashboard.ttl`, `l2_stubs.ttl`,
`fda-drug-biologic-kg/drls_establishments.ttl`, `cber_establishments.ttl`). Lists compared with
`comm`. Script and lists: `work/device_join/` and `logs/device_join_2026-11-07.log` on the VM.

## Keys

| | medical-device-kg | fda-compliance-kg / fda-drug-biologic-kg |
|---|---|---|
| Predicate | `https://bmedesign.org/medical-device-kg/ns/feiNumber` | `https://bmedesign.org/fda-compliance-kg/ns/feiNumber` |
| Literal | `xsd:string` (51,404 values on 25,695 distinct FEIs) | `xsd:string` (e.g. `"1012133"`) |
| Node | `id/establishment/<registration number>` and `id/manufacturer/<fei>` (classes RegistrationListingRecord, Manufacturer, Facility) | `id/firm/<fei>` (class Firm, 308,281 Dashboard firms + 9,583 stubs) |

Same datatype, same digits, so `?a dev:feiNumber ?fei . ?b c:feiNumber ?fei` joins directly on
FRINK's federated endpoint. No STR() or casting.

## Overlap

| Measure | Count |
|---|---|
| Distinct FEIs in the device graph | 25,695 |
| Distinct FEIs on our Firm nodes | 317,864 |
| FEIs in both | 9,715 (37.8 % of the device graph's establishments) |
| Of those, with inspections, compliance actions or import refusals in fda-compliance-kg | about 9,600 FEIs carrying about 112,300 `hasFirm` links |
| Device FEIs that are also drug or biologic establishments (DECRS, CBER) in fda-drug-biologic-kg | 835 |

Examples, device side then ours: FEI 1000016009 "POST MEDICAL, INC." / "Post Medical, Inc." with
inspection 653219 of 2010-03-23 (VAI). FEI 1000022662 "GRACE MEDICAL, INC." / inspection 642818
of 2010-01-08 (NAI). FEI 1000027288 "BENZ RESEARCH AND DEVELOPMENT LLC" / inspection 737518 of
2011-08-03 (NAI).

What this gives a user on FRINK: for a device establishment, its FDA inspection history and
classifications, compliance actions, import refusals and Import Alert listings from
fda-compliance-kg, and for the 835 dual establishments, its drug and biologic registrations too.
In the other direction, a drug firm's device registrations, product codes, MAUDE reports and
recalls.

## Other candidate keys

- Product codes: the device graph's three-letter device product codes and the Product Code
  Builder taxonomy in fda-compliance-kg are different code systems (device classification vs
  the import product code), so no join by equality.
- Recall numbers: fda-compliance-kg holds drug and food enforcement recalls only (device
  enforcement is the device graph's), so the two recall sets are disjoint by design.
- UNII: not present in the device graph.
- Names and addresses: joinable only through an identity layer (the device graph's reified
  mapping approach), not at L1.

So FEI is the one exact cross-graph key for Peter Rose's crosswalk between the two families, and
it is ready as published.

## Also done today (steps 6 and 7 of the November 7 plan)

- `pipeline/l1_vaers.py`: a zip member name is read once even when it sits in both snapshot
  zips (the NonDomestic CSV did, which doubled its blocks; identical triples, deduplicated by
  every store, so the published graph is unaffected by that one). The same full run exposed the
  vaccination and symptom child-IRI collision, which does affect the published file; see
  `CHANGES_2026-11-07.md`.
- `queries/cross/x3` and `x7` are keyed by the substance IRI instead of its label (one row per
  substance even when GSRS carries two spellings).
- `queries/cross/x9` documents why there is no identifier join from animal events to Green Book
  applications: the openFDA animal event drug block has brand name, active ingredient names and
  manufacturer name, no application number.
- The two package NDC IRIs referenced by sampled FAERS reports without a node remain to be
  looked at in the next build (the sample store is gone).
- VM: the VAERS test store (56 GB) and all test scratch deleted, 349 GB free; small outputs
  archived on the PI's archive drive under `_shared/vm-archive/query-tests-2026-11/`.
