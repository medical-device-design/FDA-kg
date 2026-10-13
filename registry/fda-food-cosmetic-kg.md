---
template: overrides/kg.html
shortname: fda-food-cosmetic-kg
title: FDA Food and Cosmetic Knowledge Graph
description: FDA adverse event reports for foods, dietary supplements and cosmetics (CAERS and the cosmetic event reports) as RDF, with products, industry codes, outcomes and reporter demographics.
stats: https://registry.okn.us/kg-stats/fda-food-cosmetic-kg
homepage: https://github.com/medical-device-design/FDA-kg
funding: https://www.nsf.gov/awardsearch/showAward?AWD_ID=2535091
license: "https://creativecommons.org/publicdomain/zero/1.0/"
frink-options:
  lakefs-repo: fda-food-cosmetic-kg
  documentation-path: fda-food-cosmetic-kg
  kgf:
    semantics:
      prefixes:
        fdafood: "https://bmedesign.org/fda-food-cosmetic-kg/ns/"
        fdafood-id: "https://bmedesign.org/fda-food-cosmetic-kg/id/"
      roles:
        label:
          - "http://www.w3.org/2000/01/rdf-schema#label"
      authoritative_namespaces:
        - fdafood
        - fdafood-id
contacts:
  - email: roche0619@outlook.com
    github: Roche619
    label: "Roche de Guzman"
---
The FDA Food and Cosmetic Knowledge Graph publishes the U.S. Food and Drug Administration's consumer adverse event reports for foods, dietary supplements and cosmetics as linked data. Every source field is kept, and every report carries its source dataset, report number, source URL and download date. Reports are de-identified by FDA before release; the graph adds no identifying data.

**Main classes.**
- `fdafood:CaersReport`: one CFSAN Adverse Event Reporting System report (151,589 in the first release), IRI `https://bmedesign.org/fda-food-cosmetic-kg/id/caers-report/<report number>`. Properties: `fdafood:dateCreated` and `fdafood:dateStarted` (xsd:date), `fdafood:outcomes` (one value per outcome, for example Hospitalization, Visited a Health Care Provider), the consumer's age and gender as a child node, and one `fdafood:CaersProducts` child per product with `fdafood:role` (SUSPECT or CONCOMITANT), `fdafood:nameBrand`, `fdafood:industryCode` and `fdafood:industryName` (FDA's food industry codes, for example 54 Vit/Min/Prot/Unconv Diet).
- `fdafood:CosmeticEvent`: one cosmetic adverse event report (85,511), IRI `.../cosmetic-event/<report number>`, with `fdafood:reportType` (Pre-MoCRA or MoCRA), received and event dates, outcomes, patient gender and age, and one `fdafood:CosmeticProducts` child per product (`fdafood:role`, `fdafood:productName`).

**Reaction terms.** Both sources code reactions with MedDRA preferred terms. The published graph carries the reaction terms only if the MedDRA licence allows it; until that is settled, reaction text is withheld from the published files and the outcomes and product fields are published in full.

**Planned additions.** Food and cosmetic recalls are in `fda-compliance-kg`. GRAS notices, Substances Added to Food, the food contact notification inventory, colour and indirect additives and NDI notifications are planned for the next release; they will link ingredients to `fda-substance-kg` by CAS number and UNII.

**Source and licence.** openFDA food/event and cosmetic/event: public domain U.S. government works. Funded under NSF award 2535091 (Proto-OKN Theme 2: OKN-Fabric) through subaward 5136002. The graph is released under CC0 1.0.


```
provenance:
  - derivedFrom:
      label: openFDA food/event (CAERS)
      uri: https://open.fda.gov/apis/food/event/
      kind: Database
      license:
        data:
          label: Public Domain
          spdx: CC0-1.0
          uri: https://open.fda.gov/license/
  - derivedFrom:
      label: openFDA cosmetic/event
      uri: https://open.fda.gov/apis/cosmetic/event/
      kind: Database
      license:
        data:
          label: Public Domain
          spdx: CC0-1.0
          uri: https://open.fda.gov/license/
```
