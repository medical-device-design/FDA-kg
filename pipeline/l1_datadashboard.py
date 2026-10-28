#!/usr/bin/env python3
"""
l1_datadashboard.py -- FDA Data Dashboard API (OII) snapshot -> fda-compliance-kg

Snapshot: raw/fda-compliance-kg/fda-datadashboard/<date>/<endpoint>/<year>.json (fetch_l0_datadashboard.py),
MANIFEST.json with the per-year counts. Every column is kept (lowerCamel of the API field name), dates typed.

Records (all in fda-compliance-kg):
  firm/<FEINumber>                       ex:Firm                  one per FEI seen in any dataset: legal or firm name,
                                                                  address, country, as last published (latest dated row);
                                                                  the same IRI the DECRS and CBER establishment records
                                                                  point at with ex:hasFirm, so inspections, citations,
                                                                  actions, refusals and registrations join on one node
  inspection/<InspectionID>              ex:Inspection            one per inspection id (FEI, end date, fiscal year)
  inspection-classification/<sha1>       ex:InspectionClassification   one per inspections_classifications row
  inspection-citation/<sha1>             ex:InspectionCitation    one per inspections_citations row (CitationID is the citation type)
  compliance-action/<sha1>               ex:ComplianceAction      one per compliance_actions row
  import-refusal/<sha1>                  ex:ImportRefusal         one per import_refusals row
Links: ex:hasFirm -> firm/<FEI>, ex:inspection -> inspection/<id>. The FirmName on an import refusal is the
name FDA publishes for the shipper of record (a business name as published).

Usage: python3 l1_datadashboard.py <snapshot_dir> <out.ttl>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

C = "fda-compliance-kg"
DOCS = "https://datadashboard.fda.gov/oii/api/index.htm"
DATES = {"InspectionEndDate", "ActionTakenDate", "RefusalDate", "FMD145Date"}
SETS = {  # endpoint -> (class, kind, key field or None, date field)
    "inspections_classifications": ("InspectionClassification", "inspection-classification", None, "InspectionEndDate"),
    # CitationID identifies the citation type (the CFR reference), not the row: rows are keyed by their content
    "inspections_citations": ("InspectionCitation", "inspection-citation", None, "InspectionEndDate"),
    "compliance_actions": ("ComplianceAction", "compliance-action", None, "ActionTakenDate"),
    "import_refusals": ("ImportRefusal", "import-refusal", None, "RefusalDate"),
}
ADDRESS = ["LegalName", "FirmName", "AddressLine1", "AddressLine2", "City", "StateCode", "State", "ZipCode", "CountryCode", "CountryName"]


def pairs_for(row):
    out = []
    for k, v in row.items():
        if v is None or (isinstance(v, str) and v.strip() == ""):
            continue
        p = f"ex:{mapper.camel(k)}"
        out.append((p, mapper.date_lit(v) if k in DATES else mapper.scalar(k, v)))
    return out


def label_for(ep, row):
    name = row.get("LegalName") or row.get("FirmName") or f"FEI {row.get('FEINumber')}"
    if ep == "inspections_classifications":
        return f"Inspection {row.get('InspectionID')} of {name}, {row.get('InspectionEndDate', '')}: {row.get('Classification', '')}".strip()
    if ep == "inspections_citations":
        return f"Citation {row.get('CitationID')} ({row.get('ActCFRNumber', '')}) at {name}, inspection {row.get('InspectionID')}"
    if ep == "compliance_actions":
        return f"{row.get('ActionType', 'Compliance action')} against {name}, {row.get('ActionTakenDate', '')}".strip()
    return f"Import refusal, {name} ({row.get('CountryCode', '')}), {row.get('ProductCode', '')}, {row.get('RefusalDate', '')}"


def convert(snap, out):
    snap = Path(snap)
    stamp = snap.name
    fh = open(out, "w", encoding="utf-8", newline="\n")
    fh.write(common.prefixes({"ex": fda_iri.ns(C)}) + "\n")
    triples = 0
    counts = {}
    firms = {}          # fei -> {field: (date, value)}
    inspections = {}    # id -> (fei, end date, fiscal year)
    seen = set()
    for ep, (cls, kind, key, datef) in SETS.items():
        d = snap / ep
        if not d.is_dir():
            print(f"  missing {ep}", file=sys.stderr)
            continue
        n = 0
        for f in sorted(d.glob("*.json")):
            for row in json.loads(f.read_text(encoding="utf-8")):
                fei = row.get("FEINumber")
                if key and row.get(key) is not None:
                    iri = fda_iri._inst(C, kind, fda_iri.slug(str(row[key])))
                else:
                    iri = fda_iri.hashed(C, kind, row)
                if iri in seen:
                    continue
                seen.add(iri)
                pairs = [("a", f"ex:{cls}")] + pairs_for(row)
                if fei:
                    pairs.append(("ex:hasFirm", f"<{fda_iri.firm(str(fei))}>"))
                    when = str(row.get(datef) or "")
                    slot = firms.setdefault(fei, {})          # field -> (date, value): newest value per field
                    for k in ADDRESS:
                        if row.get(k) and (k not in slot or when >= slot[k][0]):
                            slot[k] = (when, row[k])
                if row.get("InspectionID") is not None:
                    iid = str(row["InspectionID"])
                    pairs.append(("ex:inspection", f"<{fda_iri._inst(C, 'inspection', fda_iri.slug(iid))}>"))
                    inspections.setdefault(iid, (fei, row.get("InspectionEndDate"), row.get("FiscalYear")))
                pairs.append(("rdfs:label", common.lit(label_for(ep, row))))
                pairs += common.provenance(f"fda/data-dashboard/{ep}", f"{f.stem}:{iri.rsplit('/', 1)[1]}", source_url=DOCS, retrieved_at=stamp)
                triples += common.write_block(fh, f"<{iri}>", pairs)
                n += 1
        counts[ep] = n
    for iid, (fei, end, fy) in inspections.items():
        pairs = [("a", "ex:Inspection"), ("ex:inspectionId", common.lit(iid)), ("ex:inspectionEndDate", mapper.date_lit(end)),
                 ("ex:fiscalYear", mapper.scalar("FiscalYear", fy))]
        if fei:
            pairs.append(("ex:hasFirm", f"<{fda_iri.firm(str(fei))}>"))
        pairs.append(("rdfs:label", common.lit(f"Inspection {iid}" + (f" ({end})" if end else ""))))
        pairs += common.provenance("fda/data-dashboard/inspections", iid, source_url=DOCS, retrieved_at=stamp)
        triples += common.write_block(fh, f"<{fda_iri._inst(C, 'inspection', fda_iri.slug(iid))}>", pairs)
    for fei, slot in firms.items():
        addr = {k: v for k, (_d, v) in slot.items()}
        name = addr.get("LegalName") or addr.get("FirmName") or f"FEI {fei}"
        pairs = [("a", "ex:Firm"), ("ex:feiNumber", common.lit(fei))] + [(f"ex:{mapper.camel(k)}", common.lit(v)) for k, v in addr.items()]
        pairs.append(("rdfs:label", common.lit(name)))
        pairs += common.provenance("fda/data-dashboard/firms", str(fei), source_url=DOCS, retrieved_at=stamp)
        triples += common.write_block(fh, f"<{fda_iri.firm(str(fei))}>", pairs)
    fh.close()
    print(f"data-dashboard -> {Path(out).name}: {counts}, {len(inspections)} inspections, {len(firms)} firms, {triples} triples")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    convert(sys.argv[1], sys.argv[2])
