#!/usr/bin/env python3
"""
l1_fdcc.py -- L1 converter for the FDA food-inventory exports (hfpappexternal "fdcc"
"Download data" CSVs) and the tobacco marketing-orders CSV.

Export shape: a "Downloaded from ..." line, a blank line, optionally a quoted note and a
blank line, then the header row. Cells are padded with a leading space, numbers are
wrapped as Excel text formulas =T("175.105"), and name lists use HTML (&diams;, <br />,
<sub>). Every column is kept verbatim (lowerCamel of the header) after unwrapping =T()
and trimming; a column whose value holds HTML also gets a <name>Text twin with the tags
removed and entities decoded, like the warning-letter converter does.

Sets and keys:
  foodsubstances     Substances Added to Food (formerly EAFUS)   food-substance/<CAS>   -> fda-food-cosmetic-kg
  grasnotices        GRAS Notices                                 gras-notice/<GRN No>
  fcn                Effective Food Contact Substance Notifications   fcn/<FCN No>
  scogs              SCOGS reports                                scogs-report/<report no>
  indirectadditives  Food contact substances listed in 21 CFR     indirect-additive/<CAS>
  coloradditives     Regulatory status of color additives         color-additive/<CAS>
  marketingorders    Tobacco marketing orders (fda.gov/media/112123)  hashed -> fda-tobacco-kg
A CAS-keyed row whose CAS repeats gets _2, _3 ... in source order (same rule as
event-keyed recalls). Rows with no key at all are hashed.

Cross-graph: with --cas-map <file> (lines "CAS<TAB>substance IRI", built from
fda-substance-kg), every CAS value also yields ex:hasSubstance.

Usage:
  python3 l1_fdcc.py <set> <snapshot_dir> <out.ttl> [--cas-map FILE]
"""
import csv
import html
import io
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

F, T = "fda-food-cosmetic-kg", "fda-tobacco-kg"
csv.field_size_limit(1 << 28)
_TFORMULA = re.compile(r'^=T\("(.*)"\)$', re.S)
_TAG = re.compile(r"<[^>]+>")

SETS = {
    "foodsubstances":    dict(graph=F, cls="FoodSubstance", kind="food-substance", key="CAS Reg No (or other ID)",
                              label="Substance", cas="CAS Reg No (or other ID)",
                              dataset="fda/fdcc-foodsubstances", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=FoodSubstances"),
    "grasnotices":       dict(graph=F, cls="GrasNotice", kind="gras-notice", key="GRAS Notice (GRN) No.",
                              label="Substance", cas=None,   # GRAS notices carry no CAS column
                              dataset="fda/fdcc-grasnotices", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=GRASNotices"),
    "fcn":               dict(graph=F, cls="FoodContactNotification", kind="fcn", key="FCN No",
                              label="Food Contact Substance", cas=None,
                              dataset="fda/fdcc-fcn", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=FCN"),
    "scogs":             dict(graph=F, cls="ScogsReport", kind="scogs-report", key="SCOGS Report Number",
                              label="GRAS Substance", cas="CAS Reg. No. or other ID CODE",
                              dataset="fda/fdcc-scogs", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=SCOGS"),
    "indirectadditives": dict(graph=F, cls="IndirectAdditive", kind="indirect-additive", key="CAS Registry No. (or other ID)",
                              label="Substance", cas="CAS Registry No. (or other ID)",
                              dataset="fda/fdcc-indirectadditives", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=IndirectAdditives"),
    "coloradditives":    dict(graph=F, cls="ColorAdditive", kind="color-additive", key="CAS Reg No or other ID code",
                              label="Color", cas="CAS Reg No or other ID code",
                              dataset="fda/fdcc-coloradditives", url="https://www.hfpappexternal.fda.gov/scripts/fdcc/?set=ColorAdditives"),
    "marketingorders":   dict(graph=T, cls="TobaccoMarketingOrder", kind="marketing-order", key=None,
                              label="Product", cas=None,
                              dataset="fda/tobacco-marketing-orders", url="https://www.fda.gov/media/112123/download?attachment"),
}


def clean_text(v):
    """Tags removed, <br /> lists joined with '; ', entities decoded, the &diams; bullets dropped."""
    t = html.unescape(_TAG.sub(" ", v.replace("<br />", "; ").replace("<br/>", "; ")))
    return re.sub(r"\s+", " ", t.replace("♦", "")).strip(" ;")


def cell(v):
    if v is None:
        return None
    s = str(v).strip()
    m = _TFORMULA.match(s)
    if m:
        s = m.group(1).strip()
    return s or None


def read_export(path):
    """Yield dict rows; skips the preamble (everything before the header line)."""
    text = path.read_text(encoding="utf-8-sig", errors="replace").replace("\r\n", "\n")
    lines = text.split("\n")
    start = 0
    if lines and lines[0].startswith("Downloaded from"):
        # header = first non-blank line after the preamble that is not a quoted note
        i = 1
        while i < len(lines) and (not lines[i].strip() or lines[i].startswith('"')):
            i += 1
        start = i
    body = "\n".join(lines[start:])
    for raw in csv.DictReader(io.StringIO(body)):
        row = {}
        for k, v in raw.items():
            if k is None:
                continue
            k = k.strip()
            if not k:
                continue
            v = cell(v) if not isinstance(v, list) else cell(" ".join(x for x in v if x))
            if v is not None:
                row[k] = v
        if row:
            yield row


def load_cas_map(path):
    m = {}
    if not path:
        return m
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if "\t" in line:
            cas, iri = line.split("\t", 1)
            m.setdefault(cas.strip(), iri.strip())
    return m


def main(argv):
    if len(argv) < 4 or argv[1] not in SETS:
        raise SystemExit(__doc__)
    cfg = SETS[argv[1]]
    snap, out = Path(argv[2]), Path(argv[3])
    stamp = snap.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise SystemExit("snapshot folder must be named YYYY-MM-DD")
    cas_map = load_cas_map(argv[argv.index("--cas-map") + 1]) if "--cas-map" in argv else {}
    src = next(p for p in sorted(snap.iterdir()) if p.name not in ("SHA256SUMS", "SOURCE_URL"))
    g = cfg["graph"]
    out.parent.mkdir(parents=True, exist_ok=True)
    seen, n, triples, linked = {}, 0, 0, 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(g)}) + "\n")
        for i, row in enumerate(read_export(src)):
            key = row.get(cfg["key"]) if cfg["key"] else None
            if key:
                k = fda_iri.slug(key)
                seen[k] = seen.get(k, 0) + 1
                if seen[k] > 1:
                    k = f"{k}_{seen[k]}"
                iri = fda_iri._inst(g, cfg["kind"], k)
                rec_id = key
            else:
                iri = fda_iri.hashed(g, cfg["kind"], row)
                rec_id = f"row:{i}"
            pairs = [("a", f"ex:{cfg['cls']}")]
            for col in row:
                v = row[col]
                p = f"ex:{mapper.camel(col)}"
                pairs.append((p, mapper.date_lit(v) if "date" in col.lower() else common.lit(v)))
                if "<" in v or "&" in v:
                    clean = clean_text(v)
                    if clean and clean != v:
                        pairs.append((p + "Text", common.lit(clean)))
            label = row.get(cfg["label"]) or key or f"{cfg['cls']} {i}"
            label = clean_text(label)
            pairs.append(("rdfs:label", common.lit(label)))
            cas = row.get(cfg["cas"]) if cfg["cas"] else None
            if cas and cas in cas_map:
                pairs.append(("ex:hasSubstance", f"<{cas_map[cas]}>"))
                linked += 1
            pairs += common.provenance(cfg["dataset"], rec_id, source_url=cfg["url"], retrieved_at=stamp)
            triples += common.write_block(fh, f"<{iri}>", pairs)
            n += 1
    dup = sum(1 for v in seen.values() if v > 1)
    print(f"{argv[1]} -> {out.name}: {n} rows, {triples} triples, {linked} CAS links to fda-substance-kg, "
          f"{dup} keys that repeat (suffixed _2, _3 ...)")


if __name__ == "__main__":
    main(sys.argv)
