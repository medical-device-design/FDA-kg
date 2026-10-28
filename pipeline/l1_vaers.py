#!/usr/bin/env python3
"""
l1_vaers.py -- VAERS (Vaccine Adverse Event Reporting System) CSV downloads -> fda-drug-event-kg

Source: https://vaers.hhs.gov/data/datasets.html (manual, CAPTCHA-gated download; the snapshot
folder holds AllVAERSDataCSVS.zip and NonDomesticVAERSDATA.zip as downloaded, SOURCE_URL, SHA256SUMS).
Each zip member set is <year>VAERSDATA.csv, <year>VAERSVAX.csv, <year>VAERSSYMPTOMS.csv (and the
NonDomestic trio), joined on VAERS_ID. Every column is kept.

Records (same graph as FAERS, the adverse-event graph):
  vaers-report/<VAERS_ID>                 ex:VaersReport        one per DATA row (all columns, dates typed)
  vaers-report/<VAERS_ID>/vax/<n>         ex:VaersVaccination   one per VAX row, ex:report back-link
  vaers-report/<VAERS_ID>/symptoms/<n>    ex:VaersSymptomSet    one per SYMPTOMS row (up to 5 terms), ex:report back-link

MedDRA: SYMPTOM1..SYMPTOM5 are MedDRA preferred terms. With --publish those five text columns are
dropped (SYMPTOMVERSION1..5 stay, so the row still says how many terms it carried and which MedDRA
version). SYMPTOM_TEXT in the DATA file is the reporter's free-text narrative, not MedDRA, and is kept.
VAERS publishes no reporter or patient identities, so nothing else is removed.

Usage: python3 l1_vaers.py <snapshot_dir> <out.ttl[.gz]> [--publish]
"""
import csv
import gzip
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

E = "fda-drug-event-kg"
SRC = "https://vaers.hhs.gov/data/datasets.html"
DATE_COLS = {"RECVDATE", "RPT_DATE", "DATEDIED", "VAX_DATE", "ONSET_DATE", "TODAYS_DATE"}
MEDDRA_COLS = {f"SYMPTOM{i}" for i in range(1, 6)}
csv.field_size_limit(1 << 28)


def report_iri(vid):
    return fda_iri._inst(E, "vaers-report", fda_iri.slug(vid))


def open_member(zf, name):
    """Text stream for a zip member: UTF-8 when it decodes, else cp1252 (older years)."""
    raw = zf.read(name)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")
    return io.StringIO(text)


def pairs_for(row, skip=()):
    out = []
    for col, v in row.items():
        if not col or v is None or v == "" or col in skip:
            continue
        p = f"ex:{mapper.camel(col.lower())}"
        out.append((p, mapper.date_lit(v) if col in DATE_COLS else common.lit(v)))
    return out


def convert(snap, out_path, publish):
    snap, out_path = Path(snap), Path(out_path)
    stamp = snap.name
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8", newline="\n", compresslevel=6)) \
        if str(out_path).endswith(".gz") else (lambda p: open(p, "w", encoding="utf-8", newline="\n"))
    counts = {"reports": 0, "vaccinations": 0, "symptom_sets": 0, "triples": 0, "files": 0}
    with opener(out_path) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
        for zpath in sorted(snap.glob("*.zip")):
            with zipfile.ZipFile(zpath) as zf:
                names = sorted(zf.namelist())
                for name in names:
                    kind = re.sub(r"^(?:\d{4}|NonDomestic)VAERS", "", name, flags=re.I).upper().replace(".CSV", "")
                    if kind not in ("DATA", "VAX", "SYMPTOMS"):
                        continue
                    counts["files"] += 1
                    dataset = f"vaers/{name}"
                    rdr = csv.DictReader(open_member(zf, name))
                    for i, row in enumerate(rdr):
                        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
                        vid = row.get("VAERS_ID")
                        if not vid:
                            continue
                        riri = report_iri(vid)
                        if kind == "DATA":
                            pairs = [("a", "ex:VaersReport")] + pairs_for(row)
                            pairs.append(("rdfs:label", common.lit(f"VAERS report {vid}")))
                            pairs += common.provenance(dataset, vid, source_url=SRC, retrieved_at=stamp)
                            counts["triples"] += common.write_block(fh, f"<{riri}>", pairs)
                            counts["reports"] += 1
                        elif kind == "VAX":
                            n = row.get("ORDER") or str(i)
                            ciri = f"{riri}/vax/{fda_iri.slug(n)}"
                            pairs = [("a", "ex:VaersVaccination"), ("ex:report", f"<{riri}>")] + pairs_for(row, skip=("VAERS_ID",))
                            pairs.append(("rdfs:label", common.lit(f"{row.get('VAX_NAME') or row.get('VAX_TYPE') or 'vaccination'} (VAERS {vid})")))
                            pairs += common.provenance(dataset, f"{vid}:{n}", source_url=SRC, retrieved_at=stamp)
                            counts["triples"] += common.write_block(fh, f"<{ciri}>", pairs)
                            counts["vaccinations"] += 1
                        else:
                            n = row.get("ORDER") or str(i)
                            ciri = f"{riri}/symptoms/{fda_iri.slug(n)}"
                            skip = ("VAERS_ID",) + (tuple(MEDDRA_COLS) if publish else ())
                            terms = sum(1 for c in MEDDRA_COLS if row.get(c))
                            pairs = [("a", "ex:VaersSymptomSet"), ("ex:report", f"<{riri}>"),
                                     ("ex:termCount", f'"{terms}"^^xsd:integer')] + pairs_for(row, skip=skip)
                            pairs.append(("rdfs:label", common.lit(f"symptom set {n} (VAERS {vid})")))
                            pairs += common.provenance(dataset, f"{vid}:{n}", source_url=SRC, retrieved_at=stamp)
                            counts["triples"] += common.write_block(fh, f"<{ciri}>", pairs)
                            counts["symptom_sets"] += 1
    print(f"vaers -> {out_path.name}: {counts['files']} files, {counts['reports']} reports, "
          f"{counts['vaccinations']} vaccinations, {counts['symptom_sets']} symptom sets, "
          f"{counts['triples']} triples, publish={publish}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    convert(sys.argv[1], sys.argv[2], "--publish" in sys.argv)
