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
E = "fda-drug-event-kg"

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
        # round 4: statutory public lists of debarred persons and investigator disqualification proceedings
        "Debarment": dict(dates=["ex:effectiveDate", "ex:frDateTxtMmDdYy"]),
        # Import Alerts (accessdata cms_ia): one node per alert, firm nodes per list color, products under firms
        "ImportAlert": dict(dates=["ex:publishedDate"],
                            extra=['sh:property [ sh:path ex:alertNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportAlertProductScope": dict(links={"ex:alert": (C, "import-alert")}),
        "ImportAlertFirm": dict(links={"ex:alert": (C, "import-alert")}, dates=["ex:datePublished"],
                                extra=['sh:property [ sh:path ex:listColor ; sh:in ("red" "yellow" "green") ; sh:minCount 1 ; sh:maxCount 1 ]',
                                       'sh:property [ sh:path ex:firmName ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportAlertFirmProduct": dict(prov=False, links={"ex:alert": (C, "import-alert"), "ex:firm": (C, "import-alert")},
                                       dates=["ex:datePublished"]),
        # FDA Data Dashboard (OII API): firms keyed by FEI, the node the establishment registries point at
        "Firm": dict(extra=['sh:property [ sh:path ex:feiNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "Inspection": dict(links={"ex:hasFirm": (C, "firm")}, dates=["ex:inspectionEndDate"],
                           extra=['sh:property [ sh:path ex:inspectionId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "InspectionClassification": dict(links={"ex:hasFirm": (C, "firm"), "ex:inspection": (C, "inspection")},
                                         dates=["ex:inspectionEndDate", "ex:fmd145Date"]),
        "InspectionCitation": dict(links={"ex:hasFirm": (C, "firm"), "ex:inspection": (C, "inspection")},
                                   dates=["ex:inspectionEndDate"],
                                   extra=['sh:property [ sh:path ex:citationId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ComplianceAction": dict(links={"ex:hasFirm": (C, "firm")}, dates=["ex:actionTakenDate"]),
        "ImportRefusal": dict(links={"ex:hasFirm": (C, "firm")}, dates=["ex:refusalDate"]),
        # Product Code Builder (OII API): the import product code taxonomy
        "ImportIndustry": dict(links={"ex:hasSubclass": (C, "import-subclass"), "ex:hasProcessIndicator": (C, "import-pic")},
                               extra=['sh:property [ sh:path ex:industryCode ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportProductClass": dict(links={"ex:hasIndustry": (C, "import-industry")},
                                   extra=['sh:property [ sh:path ex:classCode ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportProductSubclass": dict(extra=['sh:property [ sh:path ex:subclassId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportProcessIndicator": dict(extra=['sh:property [ sh:path ex:picId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportProduct": dict(links={"ex:hasIndustry": (C, "import-industry"), "ex:hasClass": (C, "import-industry")},
                              extra=['sh:property [ sh:path ex:productId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "ImportProductCode": dict(links={"ex:hasIndustry": (C, "import-industry"), "ex:hasClass": (C, "import-industry"),
                                         "ex:hasSubclass": (C, "import-subclass"), "ex:hasProcessIndicator": (C, "import-pic"),
                                         "ex:hasProduct": (C, "import-industry")},
                                  extra=['sh:property [ sh:path ex:productCode ; sh:minCount 1 ; sh:maxCount 1 ; sh:pattern "^[0-9]{2}[A-Z0-9][A-Z0-9-]{2}[0-9A-Z]{2}$" ]']),
        "InvestigatorDisqualification": dict(dates=["ex:dateOfStatus", "ex:dateNidpoeIssued", "ex:dateNoohIssued",
                                                    "ex:dateOfPresidingOfficerReport", "ex:dateOfCommissionerSDecision"],
                                             extra=['sh:property [ sh:path ex:name ; sh:minCount 1 ; sh:maxCount 1 ]']),
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
        "NdcPackage": dict(links={"ex:hasApplication": (D, "application"), "ex:hasProduct": (D, "ndc-product")},
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
        "DrugEstablishment": dict(links={"ex:hasFirm": (C, "firm"), "ex:hasRegistrant": (D, "registrant")}, dates=["ex:expirationDate"],
                                  extra=['sh:property [ sh:path ex:feiNumber ; sh:maxCount 1 ]',
                                         'sh:property [ sh:path ex:dunsNumber ; sh:minCount 1 ]',
                                         'sh:property [ sh:path ex:excluded ; sh:minCount 1 ; sh:maxCount 1 ; sh:datatype xsd:boolean ]',
                                         'sh:property [ sh:path ex:establishmentContactName ; sh:maxCount 0 ]',
                                         'sh:property [ sh:path ex:establishmentContactEmail ; sh:maxCount 0 ]',
                                         'sh:property [ sh:path ex:registrantContactName ; sh:maxCount 0 ]',
                                         'sh:property [ sh:path ex:registrantContactEmail ; sh:maxCount 0 ]',
                                         'sh:property [ sh:path ex:agentDetails ; sh:maxCount 0 ]']),
        "Registrant": dict(prov=False, extra=['sh:property [ sh:path ex:duns ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "DrugLabel": dict(links={"ex:hasSubstance": (S, "unii"), "ex:hasApplication": (D, "application"),
                                 "ex:hasPackageNdc": (D, "ndc-package")}, dates=["ex:effectiveTime"],
                          # openFDA spells a few set ids in both letter cases; both spellings stay on the one node
                          extra=['sh:property [ sh:path ex:setId ; sh:minCount 1 ]']),
        # CBER registries (eBER, eHCTERS): people in the reporting-official and US-agent sections are never written
        "BloodEstablishment": dict(links={"ex:hasFirm": (C, "firm"), "ex:hasProductOperation": (D, "blood-establishment")},
                                   extra=['sh:property [ sh:path ex:registryId ; sh:minCount 1 ; sh:maxCount 1 ]',
                                          'sh:property [ sh:path ex:currentStatus ; sh:minCount 1 ; sh:maxCount 1 ]',
                                          'sh:property [ sh:path ex:reportingOfficialName ; sh:maxCount 0 ]',
                                          'sh:property [ sh:path ex:usAgentName ; sh:maxCount 0 ]',
                                          'sh:property [ sh:path ex:email ; sh:maxCount 0 ]']),
        "HctpEstablishment": dict(links={"ex:hasFirm": (C, "firm"), "ex:hasFunction": (D, "hctp-establishment"),
                                         "ex:hasListing": (D, "hctp-establishment"), "ex:hasDonorInfo": (D, "hctp-establishment")},
                                  extra=['sh:property [ sh:path ex:registryId ; sh:minCount 1 ; sh:maxCount 1 ]',
                                         'sh:property [ sh:path ex:currentStatus ; sh:minCount 1 ; sh:maxCount 1 ]',
                                         'sh:property [ sh:path ex:reportingOfficialName ; sh:maxCount 0 ]',
                                         'sh:property [ sh:path ex:email ; sh:maxCount 0 ]']),
        # round 4 (October 27, 2026): official files and single-table pages, see l1_round4.py
        "CompoundedProductReport": dict(links={"ex:hasPackageNdc": (D, "ndc-package")}),
        "InactiveIngredientRecord": dict(links={"ex:hasSubstance": (S, "unii")}, dates=["ex:recordUpdated"]),
        "InactiveIngredientChange": dict(),
        "DrugMasterFile": dict(dates=["ex:submitDate"],
                               extra=['sh:property [ sh:path ex:dmfNumber ; sh:minCount 1 ; sh:maxCount 1 ]']),
        # the 503B list's Contact column (a named person and phone number) is never written
        "OutsourcingFacility": dict(dates=["ex:initialRegistrationDate", "ex:mostRecentRegistrationDate"],
                                    extra=['sh:property [ sh:path ex:contact ; sh:maxCount 0 ]']),
        "LicensedVaccine": dict(extra=['sh:property [ sh:path ex:productName ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "CellularGeneTherapyProduct": dict(extra=['sh:property [ sh:path ex:productTradeName ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "BloodProductOperation": dict(prov=False, extra=['sh:property [ sh:path ex:product ; sh:minCount 1 ; sh:maxCount 1 ]',
                                                         'sh:property [ sh:path ex:operation ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "HctpFunction": dict(prov=False, extra=['sh:property [ sh:path ex:hctpType ; sh:minCount 1 ; sh:maxCount 1 ]',
                                                'sh:property [ sh:path ex:function ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "HctpListing": dict(prov=False, extra=['sh:property [ sh:path ex:hctpType ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "HctpDonorInfo": dict(prov=False, extra=['sh:property [ sh:path ex:hctpType ; sh:minCount 1 ; sh:maxCount 1 ]',
                                                 'sh:property [ sh:path ex:donorCategory ; sh:minCount 1 ; sh:maxCount 1 ]']),
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
        # round 4: Total Diet Study results, one record per analyte measurement
        "TdsResult": dict(extra=['sh:property [ sh:path ex:analyte ; sh:minCount 1 ; sh:maxCount 1 ]']),
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
    E: {
        "AdverseEventReport": dict(links={"ex:hasSubstance": (S, "unii"), "ex:hasApplication": (D, "application"),
                                          "ex:hasPackageNdc": (D, "ndc-package")},
                                   dates=["ex:receivedate", "ex:receiptdate", "ex:transmissiondate"],
                                   extra=['sh:property [ sh:path ex:safetyreportid ; sh:minCount 1 ; sh:maxCount 1 ]']),
        # MedDRA preferred-term text never reaches the published file (built with --publish)
        "FaersReaction": dict(prov=False, label=False, extra=['sh:property [ sh:path ex:reactionmeddrapt ; sh:maxCount 0 ]']),
        # VAERS (vaers.hhs.gov CSVs); symptom-set rows lose the five MedDRA term columns under --publish
        "VaersReport": dict(dates=["ex:recvdate", "ex:rptDate", "ex:datedied", "ex:vaxDate", "ex:onsetDate", "ex:todaysDate"],
                            extra=['sh:property [ sh:path ex:vaersId ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "VaersVaccination": dict(links={"ex:report": (E, "vaers-report")},
                                 extra=['sh:property [ sh:path ex:report ; sh:minCount 1 ; sh:maxCount 1 ]']),
        "VaersSymptomSet": dict(links={"ex:report": (E, "vaers-report")},
                                extra=['sh:property [ sh:path ex:report ; sh:minCount 1 ; sh:maxCount 1 ]',
                                       'sh:property [ sh:path ex:termCount ; sh:minCount 1 ; sh:datatype xsd:integer ]',
                                       'sh:property [ sh:path ex:symptom1 ; sh:maxCount 0 ]',
                                       'sh:property [ sh:path ex:symptom2 ; sh:maxCount 0 ]',
                                       'sh:property [ sh:path ex:symptom3 ; sh:maxCount 0 ]',
                                       'sh:property [ sh:path ex:symptom4 ; sh:maxCount 0 ]',
                                       'sh:property [ sh:path ex:symptom5 ; sh:maxCount 0 ]']),
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
    elif cfg.get("label", True):
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
