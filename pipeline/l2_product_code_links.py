#!/usr/bin/env python3
"""
l2_product_code_links.py -- links from import refusals (Data Dashboard) and Import Alert product
rows to the Product Code Builder taxonomy nodes (l1_pcb.py), all inside fda-compliance-kg.

Reads the PCB snapshot (raw/fda-compliance-kg/fda-pcb/<date>/) for the lookups and scans
out/fda-compliance-kg/data_dashboard.ttl and import_alerts.ttl for the ex:productCode values of
ex:ImportRefusal, ex:ImportAlertProductScope and ex:ImportAlertFirmProduct nodes. The source
files are not changed; this writes one extra file of links.

Code forms seen in the sources:
  98NCA11        full 7-character code (refusals)                -> ex:hasProductCode
  86HQY          industry+class+subclass+PIC, no group (refusals)
  66 V - - 99    spaced, "-" wildcards (Import Alerts): industry, class, subclass, PIC, group
Every row gets the links its parts resolve to: ex:hasImportIndustry (import-industry/<NN>),
ex:hasImportClass (import-industry/<NN>/class/<C>), ex:hasImportProduct
(import-industry/<NN>/product/<PRODID>, from industry+class+group) and ex:hasProductCode when
the full 7-character code is in the taxonomy. Unresolvable parts are counted, never guessed.

Usage: python3 l2_product_code_links.py <pcb_snapshot_dir> <out_dir> [out.ttl]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

C = "fda-compliance-kg"
CLASSES = {"ex:ImportRefusal", "ex:ImportAlertProductScope", "ex:ImportAlertFirmProduct"}
_SUBJ = re.compile(r"^<(https://bmedesign\.org/[^>]+)>\s*$")
_TYPE = re.compile(r"^    a (ex:\w+)")
_CODE = re.compile(r'^    ex:productCode "([^"]*)"')


def rows(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    r = d.get("RESULT") or {}
    return [dict(zip(r.get("COLUMNS") or [], x)) for x in (r.get("DATA") or [])]


def load_lookups(snap):
    snap = Path(snap)
    industries = {str(r["INDID"]) for r in rows(snap / "industry.json")}
    classes = {(str(r["INDID"]), str(r["CLASSID"])) for r in rows(snap / "class.json")}
    products = defaultdict(list)
    for r in rows(snap / "product.json"):
        products[(str(r["INDID"]), str(r.get("CLASSCODE") or ""), str(r.get("GROUPCODE") or ""))].append(r["PRODID"])
    codes = set()
    for f in (snap / "by_industry" / "productcodeindustry").glob("*.json"):
        codes.update(str(r["PRODUCTCODE"]).strip() for r in rows(f))
    return industries, classes, products, codes


def parts(code):
    """(industry, class, subclass, pic, group, full) from any of the three forms; '-' or '' = unknown."""
    s = code.strip().upper()
    if " " in s:
        t = s.split()
        t += [""] * (5 - len(t))
        ind, cls, sub, pic, grp = t[:5]
        norm = lambda x: "" if not x or set(x) == {"-"} else x       # noqa: E731
        ind, cls, sub, pic, grp = norm(ind), norm(cls), norm(sub), norm(pic), norm(grp)
        full = f"{ind}{cls}{sub}{pic}{grp}" if all((ind, cls, sub, pic, grp)) and len(grp) == 2 else ""
        return ind, cls, sub, pic, grp, full
    ind, cls, sub, pic, grp = s[:2], s[2:3], s[3:4], s[4:5], s[5:7]
    return ind, cls, sub, pic, grp, (s if len(s) == 7 else "")


def main(snap, out_dir, name="l2_product_code_links.ttl"):
    industries, classes, products, codes = load_lookups(snap)
    out_dir = Path(out_dir)
    base = fda_iri.id_base(C)
    n = defaultdict(int)
    with open(out_dir / name, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(C)}) + "\n")
        for src in ("data_dashboard.ttl", "import_alerts.ttl"):
            cur, want = None, False
            with open(out_dir / src, encoding="utf-8") as src_fh:
                for line in src_fh:
                    m = _SUBJ.match(line)
                    if m:
                        cur, want = m.group(1), False
                        continue
                    if cur and not want:
                        t = _TYPE.match(line)
                        if t:
                            want = t.group(1) in CLASSES
                        continue
                    if want:
                        m = _CODE.match(line)
                        if not m:
                            continue
                        ind, cls, sub, pic, grp, full = parts(m.group(1))
                        pairs = []
                        if ind in industries:
                            pairs.append(("ex:hasImportIndustry", f"<{base}import-industry/{fda_iri.slug(ind)}>"))
                        elif ind:
                            n["unknown industry"] += 1
                        if cls and (ind, cls) in classes:
                            pairs.append(("ex:hasImportClass", f"<{base}import-industry/{fda_iri.slug(ind)}/class/{fda_iri.slug(cls)}>"))
                        elif cls:
                            n["unknown class"] += 1
                        if grp and cls:
                            pids = products.get((ind, cls, grp), [])
                            for p in pids:
                                pairs.append(("ex:hasImportProduct", f"<{base}import-industry/{fda_iri.slug(ind)}/product/{fda_iri.slug(str(p))}>"))
                            if not pids:
                                n["unknown product group"] += 1
                        if full:
                            if full in codes:
                                pairs.append(("ex:hasProductCode", f"<{base}import-product-code/{fda_iri.slug(full)}>"))
                            else:
                                n["full code not in taxonomy"] += 1
                        if pairs:
                            common.write_block(fh, f"<{cur}>", pairs)
                            n[f"rows linked ({src})"] += 1
                        else:
                            n[f"rows with no link ({src})"] += 1
                        want = False        # one productCode per node
    print(f"product-code links -> {name}: {dict(n)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(*sys.argv[1:4])
