# FDA-kg

FDA regulated-products knowledge graphs for the NSF Open Knowledge Network ([okn.us](https://okn.us)):
everything FDA regulates except medical devices, which live in
[medical-device-kg](https://github.com/medical-device-design/medical-device-kg-pipeline).

PI: Roche de Guzman (roche0619@outlook.com). Funded under NSF award 2535091
(Proto-OKN Theme 2: OKN-Fabric) through subaward 5136002.

## Graph family

One okn.us shortname = one lakeFS repo = one registry entry. Each graph has its own
namespace, `https://bmedesign.org/<shortname>/ns/` (vocabulary) and `/id/` (instances),
following the medical-device-kg pattern.

| Shortname | Sources at L1 | Triples | Status (November 3, 2026) |
|---|---|---|---|
| `fda-substance-kg` | GSRS (full), UNII list; L2 substance stubs | 53.7 M | built, shapes pass, not yet published |
| `fda-compliance-kg` | drug and food enforcement recalls, warning letters (with firm nodes), historical documents, recall announcements, debarment list, investigator disqualification proceedings, Import Alerts, FDA Data Dashboard (inspections, classifications, citations, compliance actions, import refusals, FEI-keyed firms), Product Code Builder taxonomy (3.04 M product codes); L2 links from refusals and alert rows to the taxonomy, L2 firm stubs | 79.6 M | built, shapes pass, not yet published |
| `fda-drug-biologic-kg` | Drugs@FDA (openFDA and data files), NDC Directory and companion files, Orange Book (openFDA and files), Purple Book, NSDE, shortages, complete response letters, DECRS, CBER eBER and eHCTERS establishments, SPL drug labels, Inactive Ingredient Database, Drug Master File list, 503B outsourcing facilities, licensed vaccines, cellular and gene therapy products; L2 stubs | 59.4 M | built, shapes pass, not yet published |
| `fda-food-cosmetic-kg` | CAERS, cosmetic adverse events, 14 fdcc inventories (Substances Added to Food, GRAS, FCNs, SCOGS, 21 CFR food-contact, color additives and others), NDI notifications, Total Diet Study results; L2 MedDRA code links for CAERS and cosmetic reactions (held back, see below) | 7.9 M | built, shapes pass, not yet published |
| `fda-animal-health-kg` | animal adverse events, Animal Drugs @ FDA (Green Book) | 148.2 M | built, shapes pass, not yet published |
| `fda-tobacco-kg` | problem reports, marketing orders, four research datasets, Searchable Tobacco Products Database; L2 product-to-order links | 0.4 M | built, shapes pass, not yet published |
| `fda-drug-event-kg` | VAERS (3.6 M reports) and FAERS (20.7 M reports, two files), both in publish mode with MedDRA term text stripped; MedDRA 29.1 hierarchy (SOC to LLT, SMQs, history) and L2 term-to-code links for every FAERS reaction and VAERS symptom, both held back on the VM under the MedDRA license (docs/CHANGES_2026-11-03.md) | 19,460.6 M public | built; VAERS full Jena pass, FAERS streaming full-coverage check plus sampled Jena chunks (docs/CHANGES_2026-10-29.md); not yet published |

About 19.81 billion public triples in all. Every file passes `riot --validate`; every cross-reference
(application, package NDC, firm, substance, product code) resolves to a node after the L2 stub
pass (`pipeline/l2_stubs_all.py`). Details and counts: `docs/CHANGES_2026-10-12.md` through
`docs/CHANGES_2026-11-03.md`. Nothing is uploaded to lakeFS yet; registry entries are drafts in
`registry/` until the lakeFS repositories exist.

MedDRA: Hofstra holds a non-profit MedDRA subscription (internal use). The hierarchy file
(`pipeline/l1_meddra.py`) and the term-to-code link files (`pipeline/l2_meddra_terms.py`) are
built and validated on the VM but are not published, committed or uploaded until the MSSO gives a
written answer on what may be redistributed. The converters are in git; the MedDRA release and
every file derived from it are not.

## Layout

```
pipeline/   fda_iri.py (every IRI), mapper.py (record to Turtle), l1_*.py (source converters),
            fetch_l0_*.py (API snapshots), l2_stubs_all.py (stub nodes for referenced-but-undeclared
            IRIs, written into the owning graph), l2_product_code_links.py, l2_meddra_terms.py
            (MedDRA term text to PT/LLT code links), link_report.py (cross-graph link resolution),
            gen_shapes.py (SHACL), chunk_ttl.py (chunked or sampled validation), stream_check.py
            (full-coverage rule check for files too big for Jena), sample_ttl.py, xlsx_min.py.
            common.py is copied unchanged from the medical-device-kg pipeline at build time.
shapes/     generated SHACL shapes, one file per graph
queries/    SPARQL query battery (smoke tests for the joins)
scripts/    build-VM helpers (bash). Paths use /srv/fda-products-kg; hosts are placeholders.
registry/   draft entries for frink-okn/okn-registry (docs/registry/kgs/<shortname>.md)
docs/       decisions, the shared-VM workflow, and change logs
```

## Data layers

- **L0 raw**: dated openFDA, fda.gov and OII API snapshots with SHA-256 manifests. Never edited,
  never published, never in git. API keys live in env files outside the repo and are never logged.
  Licensed inputs (the MedDRA release) sit under `raw/licensed/` on the VM only.
- **L1 source**: one Turtle file per source, every field kept. Only patient or reporter
  identities, contact persons and licensed text (MedDRA, VeDDRA terms) are filtered, and
  only in the published copy (`--publish`).
- **L2 unified**: stub nodes for referenced entities no source lists, links from import
  refusals and Import Alert rows to the product code taxonomy, and MedDRA code links for
  reported reaction terms. Firms (FEI), substances, products and recalls are already shared
  IRIs across sources.

## Licence

Graph data: CC0 1.0. Source data are public domain U.S. government works from openFDA and fda.gov.
MedDRA is a registered trademark of ICH; MedDRA-derived files are not part of the public graphs.
