#!/usr/bin/env python3
"""
l1_cber.py -- CBER establishment registrations (eBER blood, eHCTERS HCT/P) from the saved public
query pages (cber_fetch.py snapshot) -> fda-drug-biologic-kg

Records
  eber    ex:BloodEstablishment  IRI blood-establishment/<FEI>  (or id-<facility_id> when no FEI)
  hcters  ex:HctpEstablishment   IRI hctp-establishment/<FEI>   (or id-<establishment_id>)
Both carry ex:hasFirm -> fda-compliance-kg firm/<FEI>, the same join key as DECRS and the Data
Dashboard. Every label/value row of the detail page becomes a predicate (lowerCamel of the label,
section-prefixed where the same label appears in several sections). Address continuation rows are
kept as extra ex:addressLine values. Block sections (OTHER NAMES, TYPE OF OWNERSHIP, ESTABLISHMENT
TYPE) give one value per line. The matrices become child nodes:
  blood-establishment/<key>/product/<code>/op/<code>   ex:BloodProductOperation (product, operation, mark)
  hctp-establishment/<key>/function/<hctp>/<function>   ex:HctpFunction
  hctp-establishment/<key>/listing/<hctp>               ex:HctpListing (describedIn1271_10 mark, proprietary names)
  hctp-establishment/<key>/donor/<hctp>/<category>      ex:HctpDonorInfo
A mark is the check image's file name (eBER uses different images per donor type) or the cell text.

Never published: the reporting official and US agent sections name people with phone and email.
Only their Organization line is kept (ex:reportingOfficialOrganization, ex:usAgentOrganization).
The establishment's own phone is a business number and is kept.

Usage: python3 l1_cber.py <snapshot_dir> <out.ttl>
"""
import csv
import gzip
import html
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

D = "fda-drug-biologic-kg"
APPS = {
    "eber": dict(cls="BloodEstablishment", kind="blood-establishment", dataset="fda/cber-eber-blood-establishment-registration",
                 url="https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/"),
    "hcters": dict(cls="HctpEstablishment", kind="hctp-establishment", dataset="fda/cber-ehcters-hctp-establishment-registration",
                   url="https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/tiss/index.cfm"),
}
PERSON_SECTIONS = ("MAILING ADDRESS OF REPORTING OFFICIAL", "US AGENT")
BLOCK_SECTIONS = ("OTHER NAMES", "TYPE OF OWNERSHIP", "ESTABLISHMENT TYPE")


# ---- a tiny DOM for table / tr / td / th / img / br ---------------------------------------
class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.children, self.parent = tag, dict(attrs), [], parent

    def text(self):
        out = []
        for c in self.children:
            if isinstance(c, str):
                out.append(c)
            elif c.tag == "br":
                out.append("\n")
            elif c.tag == "img":
                out.append(f"[img:{Path(c.attrs.get('src', '')).stem}]")
            else:
                out.append(c.text())
        return "".join(out)

    def find_all(self, tag, direct=False):
        for c in self.children:
            if isinstance(c, str):
                continue
            if c.tag == tag:
                yield c
            if not direct or c.tag not in ("table",):
                yield from c.find_all(tag, direct)


class TableParser(HTMLParser):
    KEEP = {"table", "tr", "td", "th", "img", "br", "b", "span", "font", "a", "div", "p"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        if tag in ("img", "br"):
            self.cur.children.append(Node(tag, attrs, self.cur))
            return
        if tag in ("table", "tr", "td", "th"):
            # implicit closes as browsers do
            if tag == "tr":
                self._close_until({"table"})
            elif tag in ("td", "th"):
                self._close_until({"tr", "table"})
                if self.cur.tag == "table":          # a cell with no <tr>: browsers open one implicitly
                    tr = Node("tr", (), self.cur)
                    self.cur.children.append(tr)
                    self.cur = tr
            n = Node(tag, attrs, self.cur)
            self.cur.children.append(n)
            self.cur = n

    def _close_until(self, stop):
        c = self.cur
        while c is not self.root and c.tag not in stop:
            c = c.parent
        if c is not self.root and c.tag in stop:
            self.cur = c

    def handle_endtag(self, tag):
        if tag in ("table", "tr", "td", "th"):
            c = self.cur
            while c is not self.root and c.tag != tag:
                c = c.parent
            if c is not self.root:
                self.cur = c.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def parse(page):
    p = TableParser()
    p.feed(page)
    return p.root


def clean(s):
    return " ".join(s.replace("\xa0", " ").split())


def cells(tr):
    return [c for c in tr.children if not isinstance(c, str) and c.tag in ("td", "th")]


def cell_text(td):
    """text without nested tables"""
    out = []
    for c in td.children:
        if isinstance(c, str):
            out.append(c)
        elif c.tag == "br":
            out.append("\n")
        elif c.tag == "img":
            out.append(f"[img:{Path(c.attrs.get('src', '')).stem}]")
        elif c.tag != "table":
            out.append(c.text())
    return out and "".join(out) or ""


def mark(td):
    t = clean(cell_text(td))
    m = re.search(r"\[img:([^\]]+)\]", t)
    if m:
        return m.group(1)
    return t or None


# ---- the detail page ------------------------------------------------------------------------
def walk_rows(root):
    """Yield (section, [cells]) for every tr in document order, nested tables flagged."""
    section = ""
    consumed = set()          # rows of matrices already handed over as nested tables
    for tr in root.find_all("tr"):
        if id(tr) in consumed:
            continue
        cs = cells(tr)
        if not cs:
            continue
        texts = [clean(cell_text(c)) for c in cs]
        is_header = any(c.tag == "th" or "header" in c.attrs.get("class", "").lower() for c in cs)
        nested = [t for c in cs for t in c.find_all("table", direct=True) if is_matrix(t)]
        for t in nested:
            consumed.update(id(x) for x in t.find_all("tr"))
        if is_header and not nested and texts[0]:
            section = texts[0].upper()
            continue
        if not nested and not any(texts):
            continue                      # layout wrapper row, its content rows follow on their own
        yield section, cs, texts, nested


def is_matrix(table):
    """A leaf table (no tables inside) with at least two rows of three or more cells."""
    if any(True for _ in table.find_all("table")):
        return False
    wide = [tr for tr in table.find_all("tr") if len(cells(tr)) >= 3]
    return len(wide) >= 2


def matrix(table):
    """header labels (col 1..n) and rows [(row label, [mark per column])]"""
    trs = [tr for tr in table.find_all("tr") if cells(tr)]
    if not trs:
        return [], []
    head = [clean(cell_text(c)) for c in cells(trs[0])][1:]
    rows = []
    for tr in trs[1:]:
        cs = cells(tr)
        if not cs:
            continue
        rows.append((clean(cell_text(cs[0])), [mark(c) for c in cs[1:]]))
    return head, rows


def convert_detail(page, app, key_iri, writer):
    root = parse(page)
    pairs, children = [], []
    fields = {}
    last_field = None
    for section, cs, texts, nested in walk_rows(root):
        if nested:
            for t in nested:
                head, rows = matrix(t)
                children.append((section, head, rows))
            last_field = None
            continue
        if section.startswith(PERSON_SECTIONS):
            if len(texts) >= 2 and texts[0].rstrip(":") == "Organization" and texts[1]:
                pred = "reportingOfficialOrganization" if section.startswith("MAILING") else "usAgentOrganization"
                fields.setdefault(pred, []).append(texts[1])
            continue
        if section.startswith(BLOCK_SECTIONS):
            pred = mapper.camel(section.lower())
            for line in cell_text(cs[0]).split("\n"):
                if clean(line):
                    fields.setdefault(pred, []).append(clean(line))
            continue
        if len(texts) >= 2 and texts[0].endswith(":"):
            label = texts[0].rstrip(":").strip()
            label = re.sub(r"\s*\(.*?\)\s*$", "", label) if label.startswith("FDA Establishment Identifier") else label
            pred = mapper.camel(label.lower())
            if pred == "fdaEstablishmentIdentifier":
                pred = "feiNumber"
            if texts[1]:
                fields.setdefault(pred, []).extend(clean(x) for x in cell_text(cs[1]).split("\n") if clean(x))
            last_field = pred
        elif len(texts) == 1 and texts[0] and last_field in ("address",):
            fields.setdefault("addressLine", []).append(texts[0])
        elif len(texts) == 1 and texts[0] and not texts[0].startswith(("[img:", "eBER v", "eHCTERS v", "Contact ", "FDA Home", "Print Date", "Blood Establishment Registration", "HUMAN CELL")):
            fields.setdefault("note", []).append(texts[0])
    return fields, children


def write_record(fh, app, cfg, rid, meta, fields, children, stamp):
    fei = (fields.get("feiNumber") or [meta.get("fei", "")])[0].strip()
    key = fda_iri.slug(fei) if fei else f"id-{rid}"
    iri = fda_iri._inst(D, cfg["kind"], key)
    pairs = [("a", f"ex:{cfg['cls']}"), ("ex:registryId", common.lit(rid)), ("ex:registry", common.lit(app))]
    for pred, vals in fields.items():
        for v in vals:
            if pred == "lastAnnualRegistrationYear" and v.isdigit():
                pairs.append((f"ex:{pred}", f'"{v}"^^xsd:gYear'))
            else:
                pairs.append((f"ex:{pred}", common.lit(v)))
    if "addressLine" in fields or "address" in fields:
        pairs.append(("ex:addressText", common.lit(" ".join(fields.get("address", []) + fields.get("addressLine", [])))))
    name = (fields.get("legalName") or fields.get("establishmentName") or [meta.get("name", "")])[0]
    pairs.append(("rdfs:label", common.lit(f"{name} ({'FEI ' + fei if fei else cfg['cls'] + ' ' + rid})")))
    if fei:
        pairs.append(("ex:hasFirm", f"<{fda_iri.firm(fei)}>"))
    if meta.get("status"):
        pairs.append(("ex:searchStatus", common.lit(meta["status"])))
    triples = 0
    kids = []
    for section, head, rows in children:
        for row_label, marks in rows:
            if not row_label:
                continue
            if app == "eber":
                m = re.match(r"\((\d+)\)\s*(.*)", row_label)
                pcode, pname = (m.group(1), m.group(2)) if m else (fda_iri.slug(row_label), row_label)
                for col, mk in zip(head, marks):
                    if not mk:
                        continue
                    om = re.match(r"(.*?)\s*\((\d+)\)\s*$", col)
                    oname, ocode = (om.group(1), om.group(2)) if om else (col, fda_iri.slug(col))
                    ciri = f"{iri}/product/{pcode}/op/{ocode}"
                    kids.append((ciri, [("a", "ex:BloodProductOperation"), ("ex:product", common.lit(pname)),
                                        ("ex:productCode", common.lit(pcode)), ("ex:operation", common.lit(oname)),
                                        ("ex:operationCode", common.lit(ocode)), ("ex:mark", common.lit(mk)),
                                        ("rdfs:label", common.lit(f"{pname}: {oname}"))]))
                    pairs.append(("ex:hasProductOperation", f"<{ciri}>"))
            else:
                hslug = fda_iri.slug(row_label)
                if section.startswith("ESTABLISHMENT FUNCTIONS"):
                    for col, mk in zip(head, marks):
                        if mk:
                            ciri = f"{iri}/function/{hslug}/{fda_iri.slug(col)}"
                            kids.append((ciri, [("a", "ex:HctpFunction"), ("ex:hctpType", common.lit(row_label)),
                                                ("ex:function", common.lit(col)), ("ex:mark", common.lit(mk)),
                                                ("rdfs:label", common.lit(f"{row_label}: {col}"))]))
                            pairs.append(("ex:hasFunction", f"<{ciri}>"))
                elif section.startswith("ESTABLISHMENT HCT/P LISTING"):
                    if any(marks):
                        ciri = f"{iri}/listing/{hslug}"
                        kp = [("a", "ex:HctpListing"), ("ex:hctpType", common.lit(row_label)), ("rdfs:label", common.lit(row_label))]
                        for col, mk in zip(head, marks):
                            if mk:
                                kp.append((f"ex:{mapper.camel(col.lower())}", common.lit(mk)))
                        kids.append((ciri, kp))
                        pairs.append(("ex:hasListing", f"<{ciri}>"))
                elif "DONOR" in section:
                    for col, mk in zip(head, marks):
                        if mk:
                            ciri = f"{iri}/donor/{hslug}/{fda_iri.slug(col)}"
                            kids.append((ciri, [("a", "ex:HctpDonorInfo"), ("ex:hctpType", common.lit(row_label)),
                                                ("ex:donorCategory", common.lit(col)), ("ex:mark", common.lit(mk)),
                                                ("rdfs:label", common.lit(f"{row_label}: {col}"))]))
                            pairs.append(("ex:hasDonorInfo", f"<{ciri}>"))
                else:
                    for col, mk in zip(head, marks):
                        if mk:
                            pairs.append(("ex:matrixMark", common.lit(f"{section} | {row_label} | {col} | {mk}")))
    pairs += common.provenance(cfg["dataset"], rid, source_url=cfg["url"], retrieved_at=stamp)
    triples += common.write_block(fh, f"<{iri}>", pairs)
    for ciri, kp in kids:
        triples += common.write_block(fh, f"<{ciri}>", kp)
    return triples, len(kids)


def main(snap, out):
    snap, out = Path(snap), Path(out)
    stamp = snap.name
    fh = open(out, "w", encoding="utf-8", newline="\n")
    fh.write(common.prefixes({"ex": fda_iri.ns(D)}) + "\n")
    total = {}
    for app, cfg in APPS.items():
        adir = snap / app
        if not adir.is_dir():
            print(f"{app}: no snapshot folder, skipped")
            continue
        index = {}
        if (adir / "index.tsv").exists():
            with open(adir / "index.tsv", encoding="utf-8") as ih:
                for row in csv.DictReader(ih, delimiter="\t"):
                    index[row["id"]] = row
        n = triples = kids = 0
        for p in sorted((adir / "detail").glob("*.html.gz"), key=lambda q: int(q.name.split(".")[0])):
            rid = p.name.split(".")[0]
            with gzip.open(p, "rt", encoding="utf-8") as gh:
                page = gh.read()
            fields, children = convert_detail(page, app, None, None)
            t, k = write_record(fh, app, cfg, rid, index.get(rid, {}), fields, children, stamp)
            n += 1
            triples += t
            kids += k
        total[app] = (n, kids, triples)
        print(f"{app}: {n} establishments, {kids} matrix child nodes, {triples} triples")
    fh.close()
    print(f"cber -> {out.name}: " + ", ".join(f"{a} {v[0]}" for a, v in total.items()))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
