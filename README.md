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

| Shortname | Built at L1 (2026-10-13) | Still to source | Triples | Status |
|---|---|---|---|---|
| `fda-substance-kg` | GSRS (full), UNII list | | 53.7 M | built, not yet published |
| `fda-compliance-kg` | drug and food enforcement (recalls), warning-letter index, historical documents | Data Dashboard (inspections, compliance actions, import refusals; needs an OII API key) | 1.7 M | built, not yet published |
| `fda-drug-biologic-kg` | Drugs@FDA (openFDA and data files), NDC Directory, Orange Book (openFDA and files), Purple Book, NSDE, shortages, complete response letters | drug/label (SPL) and FAERS, deferred until the new data volume | 36.5 M | built, not yet published |
| `fda-food-cosmetic-kg` | CAERS, cosmetic adverse events | GRAS, food substances, FCN, additives, NDI inventories | 6.3 M | built, not yet published |
| `fda-animal-health-kg` | animal adverse events | Animal Drugs @ FDA | 148.0 M | built, not yet published |
| `fda-tobacco-kg` | problem reports, four research datasets | tobacco products database, marketing orders | 0.2 M | built, not yet published |

All files pass `riot --validate`. Details and counts: `docs/CHANGES_2026-10-12.md`,
`docs/CHANGES_2026-10-13.md`. Nothing is uploaded to lakeFS yet; registry entries are drafts
in `registry/` until the lakeFS repositories exist.

## Layout

```
pipeline/   fda_iri.py (every IRI), mapper.py (record to Turtle), l1_*.py (source converters).
            common.py is copied unchanged from the medical-device-kg pipeline at build time.
scripts/    build-VM helpers (bash). Paths use /srv/fda-products-kg; hosts are placeholders.
registry/   draft entries for frink-okn/okn-registry (docs/registry/kgs/<shortname>.md)
docs/       decisions and change logs
```

## Data layers

- **L0 raw**: dated openFDA and fda.gov bulk snapshots with SHA-256 manifests. Never edited,
  never published, never in git.
- **L1 source**: one Turtle file per source, every field kept. Only patient or reporter
  identities, contact persons and licensed text (MedDRA, VeDDRA terms) are filtered, and
  only in the published copy (`--publish`).
- **L2 unified**: firms (FEI), substances, products and recalls resolved across sources.

## Licence

Graph data: CC0 1.0. Source data are public domain U.S. government works from openFDA and fda.gov.
