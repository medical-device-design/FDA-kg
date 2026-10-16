#!/usr/bin/env python3
"""
l1_drls.py -- Drug Establishments Current Registration Site (DECRS) bulk files -> fda-drug-biologic-kg

Source: https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site
Files:  drls_reg.zip (drls_reg.txt, tab separated, registered establishments) and
        drls_excluded.zip (drls_excluded.txt, establishments excluded from the registration list).
        Updated by FDA each business day. Covers drug and biologic establishments that register
        through eDRLS (CDER and CBER products other than blood and HCT/P establishments, which
        register in eBER and eHCTERS and have no bulk download).

Records: ex:DrugEstablishment, IRI establishment/<FEI number> (FEI is the natural key). The
         excluded list is the same class with ex:exclusionFlag "E" and ex:excluded true.
         ex:hasFirm -> the FEI-keyed firm node of fda-compliance-kg (same key the Data Dashboard
         inspections use), ex:hasRegistrant -> registrant/<DUNS> (ex:Registrant, label = name).
         OPERATIONS is kept verbatim (ex:operations) and split on ";" into ex:operation values.

Contact persons: ESTABLISHMENT_CONTACT_NAME/EMAIL, REGISTRANT_CONTACT_NAME/EMAIL and AGENT_DETAILS
         name individual people with email and phone. They are dropped by default (the out/ files are
         the published set and we never publish contact persons). --keep-contacts writes them, for a
         private L1 only.

Usage: python3 l1_drls.py <snapshot_dir> <out.ttl> [--keep-contacts]
"""
import csv
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

D = "fda-drug-biologic-kg"
SRC = "https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site"
CONTACT_COLS = {"ESTABLISHMENT_CONTACT_NAME", "ESTABLISHMENT_CONTACT_EMAIL", "AGENT_DETAILS",
                "REGISTRANT_CONTACT_NAME", "REGISTRANT_CONTACT_EMAIL"}
FILES = [("drls_reg.zip", "drls_reg.txt", "fda/drls-registration"),
         ("drls_excluded.zip", "drls_excluded.txt", "fda/drls-excluded")]


def rows(zpath, member):
    with zipfile.ZipFile(zpath) as z:
        text = z.read(member).decode("utf-8", errors="replace")
    rdr = csv.reader(io.StringIO(text), delimiter="\t")
    header = [h.strip() for h in next(rdr)]
    for r in rdr:
        if not any(c.strip() for c in r):
            continue
        yield {h: c.strip() for h, c in zip(header, r) if h}


def main(argv):
    snap, out = Path(argv[1]), Path(argv[2])
    keep = "--keep-contacts" in argv
    stamp = snap.name
    fh = open(out, "w", encoding="utf-8", newline="\n")
    fh.write(common.prefixes({"ex": fda_iri.ns(D)}) + "\n")
    n = triples = 0
    seen, registrants = set(), {}
    for zname, member, dataset in FILES:
        zpath = snap / zname
        if not zpath.exists():
            print(f"missing {zname}, skipped")
            continue
        for row in rows(zpath, member):
            fei = row.get("FEI_NUMBER", "")
            if not fei:
                continue
            iri = fda_iri._inst(D, "establishment", fda_iri.slug(fei))
            if iri in seen:            # an FEI in both files keeps the registered record
                continue
            seen.add(iri)
            pairs = [("a", "ex:DrugEstablishment")]
            for col, v in row.items():
                if not v or (col in CONTACT_COLS and not keep):
                    continue
                p = f"ex:{mapper.camel(col.lower())}"
                pairs.append((p, mapper.date_lit(v) if "DATE" in col else common.lit(v)))
            for op in [o.strip() for o in row.get("OPERATIONS", "").split(";") if o.strip()]:
                pairs.append(("ex:operation", common.lit(op)))
            excluded = row.get("EXCLUSION_FLAG", "").upper() == "E"
            pairs.append(("ex:excluded", common.bool_lit(excluded)))
            pairs.append(("rdfs:label", common.lit(f"{row.get('FIRM_NAME') or 'establishment'} (FEI {fei})")))
            pairs.append(("ex:hasFirm", f"<{fda_iri.firm(fei)}>"))
            duns = row.get("REGISTRANT_DUNS", "")
            if duns:
                reg = fda_iri._inst(D, "registrant", fda_iri.slug(duns))
                pairs.append(("ex:hasRegistrant", f"<{reg}>"))
                registrants.setdefault(reg, (duns, row.get("REGISTRANT_NAME") or duns))
            pairs += common.provenance(dataset, fei, source_url=SRC, retrieved_at=stamp)
            triples += common.write_block(fh, f"<{iri}>", pairs)
            n += 1
    for reg in sorted(registrants):
        duns, name = registrants[reg]
        triples += common.write_block(fh, f"<{reg}>", [("a", "ex:Registrant"), ("rdfs:label", common.lit(name)),
                                                     ("ex:duns", common.lit(duns))])
    fh.close()
    print(f"drls -> {out.name}: {n} establishments, {len(registrants)} registrants, {triples} triples"
          f"{' (contacts kept, private)' if keep else ' (contact columns dropped)'}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv)
