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

| Shortname | Contents | Status |
|---|---|---|
| `fda-substance-kg` | GSRS and UNII substances with CAS, PubChem, DSSTox, RxCUI and other cross-references | Phase 1 built, not yet published |
| `fda-compliance-kg` | Recalls and enforcement reports for all product types; later inspections, compliance actions, warning letters (FEI) | Phase 1 built, not yet published |
| `fda-drug-biologic-kg` | Drugs@FDA, NDC, Orange Book, Purple Book, SPL, NSDE, FAERS | Planned |
| `fda-food-cosmetic-kg` | Food and cosmetic enforcement, CAERS, GRAS, food substances, FCN, additives | Planned |
| `fda-animal-health-kg` | Animal drugs, animal adverse events | Planned |
| `fda-tobacco-kg` | Tobacco products database, marketing orders, problem reports | Planned |

## Layout

```
pipeline/   fda_iri.py (every IRI), l1_*.py (source converters). common.py is copied
            unchanged from the medical-device-kg pipeline at build time.
scripts/    build-VM helpers (bash). Paths use /srv/fda-products-kg; hosts are placeholders.
registry/   draft entries for frink-okn/okn-registry (docs/registry/kgs/<shortname>.md)
docs/       decisions and change logs
```

## Data layers

- **L0 raw**: dated openFDA bulk snapshots with SHA-256 manifests. Never edited, never published, never in git.
- **L1 source**: one Turtle file per source, every field kept. Only patient or reporter
  identities, contact persons and licensed text are filtered.
- **L2 unified**: firms (FEI), substances, products and recalls resolved across sources.

## Licence

Graph data: CC0 1.0. Source data are public domain U.S. government works from openFDA.
