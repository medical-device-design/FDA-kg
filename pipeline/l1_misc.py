#!/usr/bin/env python3
"""
l1_misc.py -- L1 converters for the round-3 sources:

  ndi                  NDI notifications list (fda.gov/media/193535, xlsx)        -> fda-food-cosmetic-kg
  recall-announcements FDA Recalls, Market Withdrawals & Safety Alerts (xlsx pages) -> fda-compliance-kg
  tobacco-products     Searchable Tobacco Products Database (CSV export)           -> fda-tobacco-kg
  adafda               Animal Drugs @ FDA: catalogue.json + previews/<id>.json     -> fda-animal-health-kg

Every column or field is kept (lowerCamel of the header), dates typed where the value is a
date, provenance on every record. Keys:
  ndi                  ndi-notification/<NDIN number>
  recall-announcements recall-announcement/<sha1 of the row>  (press releases carry no id;
                       pages overlap, so identical rows are written once); ex:hasRecallingFirm
                       uses the same name-keyed firm node as enforcement recalls and warning letters
  tobacco-products     tobacco-product/<sha1 of the row>; ex:stn is the join key to marketing orders
  adafda               animal-application/<application number, slugged>, children via mapper

Usage:
  python3 l1_misc.py ndi <snapshot_dir> <out.ttl>
  python3 l1_misc.py recall-announcements <snapshot_dir> <out.ttl>
  python3 l1_misc.py tobacco-products <snapshot_dir> <out.ttl>
  python3 l1_misc.py adafda <snapshot_dir> <out.ttl>
"""
import csv
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402
import xlsx_min    # noqa: E402

F, C, T, A = "fda-food-cosmetic-kg", "fda-compliance-kg", "fda-tobacco-kg", "fda-animal-health-kg"
csv.field_size_limit(1 << 28)


class Writer:
    def __init__(self, out, graph, dataset, stamp, url):
        self.fh = open(out, "w", encoding="utf-8", newline="\n")
        self.fh.write(common.prefixes({"ex": fda_iri.ns(graph)}) + "\n")
        self.graph, self.dataset, self.stamp, self.url = graph, dataset, stamp, url
        self.n = self.triples = 0
        self.seen = set()

    def flat(self, iri, cls, row, label, rec_id, links=(), url=None):
        """One flat record: every column as a literal, dates typed when they parse."""
        if iri in self.seen:
            return False
        self.seen.add(iri)
        pairs = [("a", f"ex:{cls}")]
        for col, v in row.items():
            if v is None or v == "":
                continue
            p = f"ex:{mapper.camel(col)}"
            pairs.append((p, mapper.date_lit(v) if "date" in col.lower() else common.lit(v)))
        pairs.append(("rdfs:label", common.lit(label)))
        pairs += list(links)
        pairs += common.provenance(self.dataset, rec_id, source_url=url or self.url, retrieved_at=self.stamp)
        self.triples += common.write_block(self.fh, f"<{iri}>", pairs)
        self.n += 1
        return True

    def close(self):
        self.fh.close()


def _first(snap, patterns):
    for pat in patterns:
        for p in sorted(snap.glob(pat)):
            if p.name not in ("SHA256SUMS", "SOURCE_URL"):
                return p
    raise SystemExit(f"no input matching {patterns} in {snap}")


def _header_row(path, any_of):
    """Index of the first xlsx row with 3+ cells whose text contains any of the words (case-insensitive)."""
    for i, r in enumerate(xlsx_min.rows(path)):
        cells = [c for c in r if c]
        text = " ".join(str(c) for c in cells).lower()
        if len(cells) >= 3 and any(w in text for w in any_of):
            return i
        if i > 30:
            break
    return 0


# ---------------------------------------------------------------------------
def convert_ndi(snap, out, stamp):
    src = _first(snap, ["*.xlsx"])
    h = _header_row(src, ["ndin", "notification"])
    w = Writer(out, F, "fda/ndi-notifications", stamp, "https://www.fda.gov/media/193535/download")
    key_col = None
    for i, row in enumerate(xlsx_min.dict_rows(src, h)):
        if key_col is None:
            key_col = next((k for k in row if "notification" in k.lower() and "#" in k or k.lower().startswith("ndin")), None) \
                or next((k for k in row if "notification" in k.lower()), None)
        key = row.get(key_col) if key_col else None
        name = next((row[k] for k in row if "name" in k.lower() or "ingredient" in k.lower()), None)
        if key:
            iri = fda_iri._inst(F, "ndi-notification", fda_iri.slug(str(key)))
            rec = str(key)
        else:
            iri = fda_iri.hashed(F, "ndi-notification", row)
            rec = f"row:{i}"
        w.flat(iri, "NdiNotification", row, f"NDIN {key} {name or ''}".strip() if key else (name or f"NDI row {i}"), rec)
    w.close()
    return w


def convert_recall_announcements(snap, out, stamp):
    files = sorted(p for p in snap.glob("*.xlsx"))
    w = Writer(out, C, "fda/recalls-market-withdrawals-safety-alerts", stamp,
               "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts")
    dup = 0
    firms = {}          # the same name-keyed firm node the enforcement and warning-letter converters mint
    for f in files:
        for row in xlsx_min.dict_rows(f, 0):
            iri = fda_iri.hashed(C, "recall-announcement", row)
            company = row.get("Company-Name") or row.get("Company Name")
            links = []
            if company:
                try:
                    firm_iri = fda_iri.recalling_firm(company)
                    links.append(("ex:hasRecallingFirm", f"<{firm_iri}>"))
                    firms.setdefault(firm_iri, company)
                except ValueError:
                    pass
            label = f"{row.get('Brand-Names') or row.get('Brand Name(s)') or company or 'recall'} {row.get('Date', '')}".strip()
            if not w.flat(iri, "RecallAnnouncement", row, label, f"{f.name}:{iri.rsplit('/', 1)[1]}", links):
                dup += 1
    for firm_iri in sorted(firms):
        w.triples += common.write_block(w.fh, f"<{firm_iri}>", [("a", "ex:RecallingFirm"), ("rdfs:label", common.lit(firms[firm_iri]))])
    w.close()
    w.dup = dup
    return w


def convert_tobacco_products(snap, out, stamp):
    src = _first(snap, ["*.csv"])
    text = src.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    start = next(i for i, ln in enumerate(lines) if ln.startswith('"Company"') or ln.startswith("Company,"))
    w = Writer(out, T, "fda/searchable-tobacco-products-database", stamp,
               "https://www.accessdata.fda.gov/scripts/searchtobacco/index.cfm")
    for i, raw in enumerate(csv.DictReader(io.StringIO("\n".join(lines[start:])))):
        row = {k.strip(): v.strip() for k, v in raw.items() if k and v and v.strip() and v.strip() != "N/A"}
        if not row:
            continue
        iri = fda_iri.hashed(T, "tobacco-product", row)
        label = f"{row.get('Product Name', '')} ({row.get('Company', '')})".strip()
        w.flat(iri, "TobaccoProduct", row, label, f"row:{i}")
    w.close()
    return w


def convert_adafda(snap, out, stamp):
    cat = json.loads(_first(snap, ["catalogue.json"]).read_text(encoding="utf-8"))
    previews = {p.stem: p for p in (snap / "previews").glob("*.json")} if (snap / "previews").is_dir() else {}
    fh = open(out, "w", encoding="utf-8", newline="\n")
    fh.write(common.prefixes({"ex": fda_iri.ns(A)}) + "\n")
    m = mapper.Mapper(fh, class_prefix="AnimalDrug", date_fields={"approvalDate", "actionDate", "dateOfAction"})
    items = cat if isinstance(cat, list) else cat.get("content") or cat.get("results") or cat.get("data") or []
    n = 0
    for rec in items:
        app_id = str(rec.get("applicationId") or rec.get("id") or "")
        appno = rec.get("applicationNumber") or rec.get("application_number")
        if not appno:
            continue
        iri = fda_iri._inst(A, "animal-application", fda_iri.slug(str(appno)))
        full = dict(rec)
        if app_id in previews:
            try:
                pv = json.loads(previews[app_id].read_text(encoding="utf-8"))
                if isinstance(pv, dict):
                    for k, v in pv.items():
                        full.setdefault(k, v)
            except json.JSONDecodeError:
                pass
        label = f"{appno} {rec.get('proprietaryName') or rec.get('sponsorName') or ''}".strip()
        extra = [("rdfs:label", common.lit(label))]
        extra += common.provenance("fda/animal-drugs-at-fda", str(appno),
                                   source_url=f"https://animaldrugsatfda.fda.gov/adafda/views/#/search/application/{app_id}" if app_id else
                                   "https://animaldrugsatfda.fda.gov/adafda/views/#/search", retrieved_at=stamp)
        m.map_obj(iri, full, cls="AnimalDrugApplication", extra=extra, top=True)
        n += 1
    fh.close()

    class R:
        pass
    r = R()
    r.n, r.triples = n, m.triples
    return r


CONVERTERS = {"ndi": convert_ndi, "recall-announcements": convert_recall_announcements,
              "tobacco-products": convert_tobacco_products, "adafda": convert_adafda}


def main(argv):
    if len(argv) < 4 or argv[1] not in CONVERTERS:
        raise SystemExit(__doc__)
    snap, out = Path(argv[2]), Path(argv[3])
    stamp = snap.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise SystemExit("snapshot folder must be named YYYY-MM-DD")
    out.parent.mkdir(parents=True, exist_ok=True)
    r = CONVERTERS[argv[1]](snap, out, stamp)
    extra = f", {r.dup} duplicate rows across pages skipped" if hasattr(r, "dup") else ""
    print(f"{argv[1]} -> {out.name}: {r.n} records, {r.triples} triples{extra}")


if __name__ == "__main__":
    main(sys.argv)
