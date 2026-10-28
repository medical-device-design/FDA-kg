#!/usr/bin/env python3
"""
l1_import_alerts.py -- FDA Import Alerts (accessdata.fda.gov/cms_ia) -> fda-compliance-kg

Snapshot: raw/fda-compliance-kg/fda-import-alerts/<date>/ialist.html plus importalert_<n>.html for every
alert on the index (fetch_l0_import_alerts.sh). Each alert page has a header (number, published date,
type, name, reason, guidance, product description, charge), a by-country product scope panel, and the
Red / Yellow / Green lists of firms with their products.

Records:
  import-alert/<number>                               ex:ImportAlert        header fields as text, one per page
  import-alert/<number>/scope/<n>                     ex:ImportAlertProductScope   country + product code/name/desc/problems
  import-alert/<number>/<red|yellow|green>/<sha1>     ex:ImportAlertFirm    firm name, address, country, list color,
                                                                            date published; ex:alert back-link
  .../<sha1>/product/<n>                              ex:ImportAlertFirmProduct    product code, name, date published,
                                                                            description, notes, problems
Firms are businesses on a public regulatory list; no person names appear on these pages. Every field
is kept as the page shows it (text untagged, whitespace collapsed).

Usage: python3 l1_import_alerts.py <snapshot_dir> <out.ttl>
"""
import hashlib
import html as htmlmod
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

C = "fda-compliance-kg"
BASE = "https://www.accessdata.fda.gov/cms_ia/"
_TAG = re.compile(r"<[^>]+>")


def text(s):
    s = re.sub(r"<br\s*/?>", "\n", s or "", flags=re.I)
    s = _TAG.sub(" ", s)
    s = htmlmod.unescape(s).replace("\xa0", " ")
    lines = [" ".join(ln.split()) for ln in s.split("\n")]
    return "\n".join(ln for ln in lines if ln).strip()


def norm(s):
    return re.sub(r"\s+", " ", s)


def alert_iri(number):
    return fda_iri._inst(C, "import-alert", fda_iri.slug(number))


# header: <div><B>Import Alert</B> # 45-02</div> <div><B>Published Date:</B> 10/26/2026</div> <div><B>Type:</B> DWPE</div>
# then <h3>Import Alert Name:</h3> <div>...</div> <h3>Reason for Alert:</h3> <div>...</div> ... <h3>Charge:</h3> ...
_H3 = re.compile(r"<h3[^>]*>(.*?)</h3>\s*(.*?)(?=<h3|<div class=\"panel|<hr|<a name=|$)", re.S | re.I)
_BOLD = re.compile(r"<div[^>]*>\s*<b>\s*([^<]+?)\s*</b>\s*(.*?)</div>", re.S | re.I)
_PANEL = re.compile(r"<h2 class=\"panel-title\">(.*?)</h2>\s*</div>\s*<div class=\"panel-body\">(.*?)</div>\s*</div>", re.S | re.I)
_PANEL_ITEM = re.compile(r"<li>(.*?)</li>", re.S | re.I)
_SECTION = re.compile(r"<a name=\"(Red|Yellow|Green)Firm\">", re.I)
_COUNTRY = re.compile(r"<div class=\"center\">\s*<h4>([^<]+)</h4>\s*</div>", re.I)
_FIRM = re.compile(r"<div class=\"div-info\">\s*<div class=\"div-name floatleft\">(.*?)</div>\s*"
                   r"<div class=\"div-name floatright\">\s*Date Published\s*:\s*(.*?)</div>\s*<div class=\"clear\">(.*?)</div>\s*</div>", re.S | re.I)
_PRODUCT = re.compile(r"<div>\s*<div class=\"floatleft\">\s*<em>(.*?)</em>(.*?)</div>\s*"
                      r"<div class=\"floatright marginsmall\">\s*Date Published:\s*(.*?)</div>\s*</div>\s*(?:<p class=\"clear\">(.*?)</p>)?", re.S | re.I)
_TOKEN = re.compile("|".join(f"(?P<{n}>{p.pattern})" for n, p in
                             [("section", _SECTION), ("country", _COUNTRY), ("firm", _FIRM), ("product", _PRODUCT)]), re.S | re.I)


def field_divs(block):
    """'Desc: x', 'Notes: y', 'Problems: z' divs inside a product or scope block."""
    out = {}
    for m in re.finditer(r"<div[^>]*>(.*?)</div>", block or "", re.S | re.I):
        t = text(m.group(1))
        mm = re.match(r"(Desc|Notes|Problems?)\s*(?:\(s\))?\s*:\s*(.*)", t, re.S | re.I)
        if mm:
            key = {"desc": "description", "notes": "notes", "problem": "problems", "problems": "problems"}[mm.group(1).lower()]
            out[key] = (out.get(key, "") + "\n" + mm.group(2).strip()).strip()
    return out


class Writer:
    def __init__(self, out):
        self.fh = open(out, "w", encoding="utf-8", newline="\n")
        self.fh.write(common.prefixes({"ex": fda_iri.ns(C)}) + "\n")
        self.n = {"alerts": 0, "scope": 0, "firms": 0, "products": 0}
        self.triples = 0

    def block(self, iri, pairs):
        self.triples += common.write_block(self.fh, f"<{iri}>", pairs)


def convert_page(path, w, stamp):
    page = norm(path.read_text(encoding="utf-8", errors="replace"))
    body = page[page.find("<h1>"):] if "<h1>" in page else page
    m = re.search(r"<h1>\s*Import Alert\s*([0-9A-Za-z-]+)\s*</h1>", body)
    if not m:
        print(f"  skip {path.name}: no alert number", file=sys.stderr)
        return
    number = m.group(1)
    iri = alert_iri(number)
    url = BASE + path.name
    pairs = [("a", "ex:ImportAlert"), ("ex:alertNumber", common.lit(number))]
    for k, v in _BOLD.findall(body[:20000]):
        key = k.strip().rstrip(":").strip()
        val = text(v).lstrip("#").strip()
        if key.lower() == "import alert":
            continue
        pairs.append((f"ex:{mapper.camel(key)}", mapper.date_lit(val) if "date" in key.lower() else common.lit(val)))
    first = _SECTION.search(body)          # the lists start at the first Red/Yellow/Green anchor
    head_end = first.start() if first else -1
    head = body[:head_end] if head_end > 0 else body
    name = None
    for k, v in _H3.findall(head):
        key = text(k).rstrip(":").strip()
        val = text(v)
        if key and val:
            pairs.append((f"ex:{mapper.camel(key)}", common.lit(val)))
            if key.lower() == "import alert name":
                name = val.strip('"').strip()
    pairs.append(("rdfs:label", common.lit(f"Import Alert {number}" + (f": {name[:90]}" if name else ""))))
    pairs += common.provenance("fda/import-alerts", number, source_url=url, retrieved_at=stamp)
    w.block(iri, pairs)
    w.n["alerts"] += 1
    # by-country product scope panel
    for country, items in _PANEL.findall(head):
        for li in _PANEL_ITEM.findall(items):
            w.n["scope"] += 1
            code_m = re.search(r"<i>(.*?)</i>(.*?)(?:<br|</div>)", li, re.S | re.I)
            sp = [("a", "ex:ImportAlertProductScope"), ("ex:alert", f"<{iri}>"), ("ex:country", common.lit(text(country)))]
            if code_m:
                sp += [("ex:productCode", common.lit(text(code_m.group(1)))), ("ex:productName", common.lit(text(code_m.group(2))))]
            for k, v in field_divs(li).items():
                sp.append((f"ex:{k}", common.lit(v)))
            sp.append(("rdfs:label", common.lit(f"{text(code_m.group(2)) if code_m else 'product'} ({text(country)}, IA {number})")))
            sp += common.provenance("fda/import-alerts", f"{number}:scope:{w.n['scope']}", source_url=url, retrieved_at=stamp)
            w.block(f"{iri}/scope/{w.n['scope']}", sp)
    # firm lists
    if head_end < 0:
        return
    color = country = None
    firm_iri = None
    pn = 0
    for t in _TOKEN.finditer(body[head_end:]):
        kind = t.lastgroup
        if kind == "section":
            color = _SECTION.search(t.group(0)).group(1).lower()
            country = None
        elif kind == "country":
            country = text(_COUNTRY.search(t.group(0)).group(1))
        elif kind == "firm":
            fm = _FIRM.search(t.group(0))
            fname, fdate, faddr = text(fm.group(1)), text(fm.group(2)), text(fm.group(3))
            key = hashlib.sha1(f"{number}|{color}|{country}|{fname}|{faddr}".encode()).hexdigest()[:20]
            firm_iri = f"{iri}/{color or 'list'}/{key}"
            pn = 0
            fp = [("a", "ex:ImportAlertFirm"), ("ex:alert", f"<{iri}>"), ("ex:listColor", common.lit(color)),
                  ("ex:country", common.lit(country)), ("ex:firmName", common.lit(fname)), ("ex:address", common.lit(faddr)),
                  ("ex:datePublished", mapper.date_lit(fdate)), ("rdfs:label", common.lit(f"{fname} ({country}, IA {number} {color} list)"))]
            fp += common.provenance("fda/import-alerts", f"{number}:{color}:{key}", source_url=url, retrieved_at=stamp)
            w.block(firm_iri, fp)
            w.n["firms"] += 1
        elif kind == "product" and firm_iri:
            pm = _PRODUCT.search(t.group(0))
            pn += 1
            pp = [("a", "ex:ImportAlertFirmProduct"), ("ex:firm", f"<{firm_iri}>"), ("ex:alert", f"<{iri}>"),
                  ("ex:productCode", common.lit(text(pm.group(1)))), ("ex:productName", common.lit(text(pm.group(2)))),
                  ("ex:datePublished", mapper.date_lit(text(pm.group(3))))]
            for k, v in field_divs(pm.group(4)).items():
                pp.append((f"ex:{k}", common.lit(v)))
            pp.append(("rdfs:label", common.lit(f"{text(pm.group(2))} ({text(pm.group(1))})")))
            w.block(f"{firm_iri}/product/{pn}", pp)
            w.n["products"] += 1


def convert(snap, out):
    snap = Path(snap)
    w = Writer(out)
    files = sorted(snap.glob("importalert_*.html"), key=lambda p: int(re.sub(r"\D", "", p.stem)))
    for p in files:
        convert_page(p, w, snap.name)
    w.fh.close()
    print(f"import-alerts -> {Path(out).name}: {len(files)} pages, {w.n['alerts']} alerts, {w.n['scope']} scope rows, "
          f"{w.n['firms']} firms, {w.n['products']} firm products, {w.triples} triples")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    convert(sys.argv[1], sys.argv[2])
