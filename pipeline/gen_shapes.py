#!/usr/bin/env python3
"""
gen_shapes.py -- writes one SHACL shapes file per graph into <out_dir>/<graph>.shapes.ttl.

The shapes state what every L1 record promises, no more:
  * every top-level record has an rdfs:label and a provenance block
    (ex:sourceDataset, ex:sourceRecordId, ex:sourceUrl, ex:retrievedAt as xsd:date);
    a node that the same IRI gets from two sources has two provenance blocks, so these
    are minCount 1, and an L2 stub (ex:isStub true) is exempt
  * every cross-reference predicate points at an IRI in the right namespace
  * every date predicate is an xsd:date or, when the source value was not a real
    date, the original string (never any other datatype)
  * a few value lists FDA guarantees (recall classification, UNII shape)
Shapes are generated, not hand-written, so the record list below is the single source.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fda_iri  # noqa: E402

B = "https://bmedesign.org/"
D, C, S, F, A, T = ("fda-drug-biologic-kg", "fda-compliance-kg", "fda-substance-kg",
                    "fda-food-cosmetic-kg", "fda-animal-health-kg", "fda-tobacco-kg")

# graph -> {class: dict(links={pred: (graph, kind)}, dates=[...], extra=[raw property shapes])}
RECORDS = {
    C: {
        "Recall": dict(links={"ex:hasRecallEvent": (C, "recall-event"), "ex:hasRecallingFirm": (C, "recalling-firm"),
                              "ex:hasSubstance": (S, "unii")},
                       dates=["ex:recallInitiationDate", "ex:reportDate", "ex:centerClassificationDate", "ex:terminationDate"],
                       extra=['sh:property [ sh:path ex:classification ; sh:in ("Class I" "Class II" "Class III" "Not Yet Classified") ; sh:maxCount 1 ]',
                              'sh:property [ sh:path ex:eventId ; sh:minCount 1 ]']),
        "RecallEvent": dict(prov=False),
        "RecallingFirm": dict(prov=False),
        "WarningLetter": dict(links={"ex:hasFirm": (C, "recalling-firm")},
                              dates=["ex:fieldLetterIssueDatetime", "ex:fieldResponseDate", "ex:fieldCloseoutDate", "ex:fieldChangeDate2"]),
        "HistoricalDocument": dict(),
        "RecallAnnouncement": dict(links={"ex:hasRecallingFirm": (C, "recalling-firm")}, dates=["ex:date"]),
    },
    S: {
        "Substance": dict(extra=['sh:property [ sh:path ex:unii ; sh:maxCount 1 ; sh:pattern "^[A-Z0-9]{10}$" ]']),
    },
    D: {
        "DrugApplication": dict(links={"ex:hasSubstance": (S, "unii")}, dates=["ex:submissionStatusDate"]),
        "DrugProduct": dict(links={"ex:hasApplication": (D, "application")}),
        "Submission": dict(links={"ex:hasApplication": (D, "application")}, dates=["ex:submissionStatusDate"]),
        "NdcProduct": dict(links={"ex:hasSubstance": (S, "unii"), "ex:hasApplication": (D, "application"),
                                  "ex:packaging": (D, "ndc-package")},
                           dates=["ex:marketingStartDate", "ex:marketingEndDate", "ex:listingExpirationDate"]),
        "NdcPackage": dict(links={"ex:hasApplication": (D, "application")},
                           dates=["ex:marketingStartDate", "ex:marketingEndDate", "ex:inactivationDate", "ex:reactivationDate"]),
        "OrangeBookProduct": dict(links={"ex:hasApplication": (D, "application")}, dates=["ex:approvalDate"]),
        "OrangeBookPatent": dict(links={"ex:hasProduct": (D, "application")}, dates=["ex:patentExpireDateText", "ex:submissionDate"]),
        # the Orange Book data files' exclusivity rows; "OrangeBookExclusivity" is the openFDA child node
        "OrangeBookExclusivityRecord": dict(links={"ex:hasProduct": (D, "application")}, dates=["ex:exclusivityDate"]),
        "PurpleBookChange": dict(links={"ex:hasApplication": (D, "application")}, dates=["ex:approvalDate", "ex:dateOfFirstLicensure"]),
        "PurpleBookProduct": dict(links={"ex:hasApplication": (D, "application")}, dates=["ex:approvalDate", "ex:dateOfFirstLicensure"]),
        "DrugShortage": dict(links={"ex:hasSubstance": (S, "unii"), "ex:hasPackageNdc": (D, "ndc-package")},
                             dates=["ex:initialPostingDate", "ex:updateDate", "ex:discontinuedDate", "ex:changeDate"]),
        "CompleteResponseLetter": dict(links={"ex:hasApplication": (D, "application")}, dates=["ex:letterDate"]),
    },
    F: {
        "FoodSubstance": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "GrasNotice": dict(dates=["ex:dateOfFiling", "ex:dateOfClosure", "ex:dateOfCorrectionLetter"],
                           extra=['sh:property [ sh:path ex:grasNoticeGrnNo ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "FoodContactNotification": dict(dates=["ex:effectiveDate"],
                                        extra=['sh:property [ sh:path ex:fcnNo ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ScogsReport": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "IndirectAdditive": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "ColorAdditive": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "CediRecord": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "PostmarketAssessmentSubstance": dict(links={"ex:hasSubstance": (S, "(unii|gsrs)")}),
        "ThresholdOfRegulationExemption": dict(), "RecycledPlasticOpinion": dict(dates=["ex:dateOfNol"]),
        "SeafoodListEntry": dict(), "NewPlantVarietyConsultation": dict(), "NewProteinConsultation": dict(),
        "GenomeEditedPlantMeeting": dict(dates=["ex:dateOfMeeting"]),
        "NdiNotification": dict(dates=["ex:dateOfSubmission", "ex:dateOfFdaSResponse"]),
        "CaersReport": dict(dates=["ex:dateCreated", "ex:dateStarted"],
                            extra=['sh:property [ sh:path ex:reportNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "CosmeticEvent": dict(dates=["ex:initialReceivedDate", "ex:latestReceivedDate", "ex:eventDate"],
                              extra=['sh:property [ sh:path ex:reportNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
    },
    A: {
        "AnimalEvent": dict(dates=["ex:originalReceiveDate", "ex:onsetDate"],
                            extra=['sh:property [ sh:path ex:uniqueAerIdNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "AnimalDrugApplication": dict(dates=["ex:approvalDate", "ex:actionDate", "ex:dateOfAction"],
                                      extra=['sh:property [ sh:path ex:applicationNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
    },
    T: {
        "TobaccoProblemReport": dict(dates=["ex:dateSubmitted"],
                                     extra=['sh:property [ sh:path ex:reportId ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:integer ]']),
        "TobaccoMarketingOrder": dict(dates=["ex:issueDate"]),
        "TobaccoProduct": dict(dates=["ex:dateOfAction"], extra=['sh:property [ sh:path ex:stn ; sh:maxCount 1 ]']),
        "TobaccoDigitalAdStudyRow": dict(), "TobaccoHarmPerceptionRecord": dict(),
        "TobaccoPreventionAdStudy": dict(), "SmokefreeMetric": dict(),
    },
}

HEAD = """@prefix sh:   <http://www.w3.org/ns/shacl#> .
@prefix xsd:  <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <{ns}> .
@prefix shp:  <{ns}shape/> .

# Generated by pipeline/gen_shapes.py for {graph}. Do not edit by hand.
"""

PROV = """    sh:property [ sh:path rdfs:label ; sh:minCount 1 ; sh:datatype xsd:string ] ;
    sh:or (
        [ sh:property [ sh:path ex:isStub ; sh:hasValue true ] ]
        [ sh:property [ sh:path ex:sourceDataset ; sh:minCount 1 ; sh:datatype xsd:string ] ;
          sh:property [ sh:path ex:sourceRecordId ; sh:minCount 1 ] ;
          sh:property [ sh:path ex:sourceUrl ; sh:minCount 1 ] ;
          sh:property [ sh:path ex:retrievedAt ; sh:minCount 1 ; sh:datatype xsd:date ] ]
    ) ;
"""


def shape(graph, cls, cfg):
    lines = [f"shp:{cls}Shape a sh:NodeShape ;", f"    sh:targetClass ex:{cls} ;"]
    if cfg.get("prov", True):
        lines.append(PROV.rstrip("\n"))
    else:
        lines.append("    sh:property [ sh:path rdfs:label ; sh:minCount 1 ] ;")
    for pred, (g, kind) in cfg.get("links", {}).items():
        base = fda_iri.id_base(g) + kind + "/"
        lines.append(f'    sh:property [ sh:path {pred} ; sh:nodeKind sh:IRI ; sh:pattern "^{base}" ] ;')
    for pred in cfg.get("dates", []):
        lines.append(f"    sh:property [ sh:path {pred} ; sh:or ( [ sh:datatype xsd:date ] [ sh:datatype xsd:string ] ) ] ;")
    for raw in cfg.get("extra", []):
        lines.append(f"    {raw} ;")
    lines[-1] = lines[-1].rstrip(" ;") + " ."
    return "\n".join(lines) + "\n\n"


def main(out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for graph, classes in RECORDS.items():
        text = HEAD.format(ns=fda_iri.ns(graph), graph=graph)
        for cls, cfg in classes.items():
            text += shape(graph, cls, cfg)
        (out_dir / f"{graph}.shapes.ttl").write_text(text, encoding="utf-8", newline="\n")
        print(f"{graph}.shapes.ttl: {len(classes)} node shapes")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "shapes")
