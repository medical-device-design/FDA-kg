#!/usr/bin/env python3
"""
l1_pcb.py -- FDA Product Code Builder (OII) snapshot -> fda-compliance-kg: the import product
code taxonomy that import refusals, import alerts and entry lines use.

Snapshot: raw/fda-compliance-kg/fda-pcb/<date>/ (fetch_l0_pcb.py): industry, class, subclass,
pic, product and by_industry/{industryclass,industrysubclass,industrypic,industryproduct,
productcodeindustry}/<INDID>.json, MANIFEST.json.

A product code is 7 characters: industry (2) + class (1) + subclass (1) + process indicator
code, PIC (1) + product group (2), e.g. 16XYU46 or 17EM125 (class, subclass and PIC can be digits).
Every column is kept; the all-caps API column names map to readable properties (NAMES below).

Records (all in fda-compliance-kg):
  import-industry/<INDID>                        ex:ImportIndustry        industryCode, description (INDDESC)
  import-industry/<INDID>/class/<CLASSID>        ex:ImportProductClass    classCode, description; hasIndustry
  import-subclass/<SUBCLASSID>                   ex:ImportProductSubclass subclassId, subclassCode, description
  import-pic/<PICID>                             ex:ImportProcessIndicator picId, picCode, description
  import-industry/<INDID>/product/<PRODID>       ex:ImportProduct         productId, description, classCode,
                                                                           groupCode; hasIndustry, hasClass
  import-product-code/<CODE>                     ex:ImportProductCode     productCode; hasIndustry, hasClass,
                                                                           hasSubclass, hasProcessIndicator,
                                                                           hasProduct (resolved from the code's
                                                                           parts and the per-industry lists)
Industry -> ex:hasSubclass / ex:hasProcessIndicator links come from industrysubclass / industrypic.
Nothing in this source is personal data.

Usage: python3 l1_pcb.py <snapshot_dir> <out.ttl>
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

C = "fda-compliance-kg"
DOCS = "https://www.accessdata.fda.gov/scripts/ora/pcb/apidocs/"


def rows(path):
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    r = d.get("RESULT") or {}
    cols = r.get("COLUMNS") or []
    return [dict(zip(cols, x)) for x in (r.get("DATA") or [])]


def by_industry(snap, ep):
    out = {}
    for f in sorted((snap / "by_industry" / ep).glob("*.json")):
        out[f.stem] = rows(f)
    return out


def industry_iri(ind):
    return fda_iri._inst(C, "import-industry", fda_iri.slug(ind))


def class_iri(ind, cls):
    return industry_iri(ind) + "/class/" + fda_iri.slug(cls)


def product_iri(ind, pid):
    return industry_iri(ind) + "/product/" + fda_iri.slug(str(pid))


def subclass_iri(sid):
    return fda_iri._inst(C, "import-subclass", fda_iri.slug(str(sid)))


def pic_iri(pid):
    return fda_iri._inst(C, "import-pic", fda_iri.slug(str(pid)))


def code_iri(code):
    return fda_iri._inst(C, "import-product-code", fda_iri.slug(code))


NAMES = {  # API column -> property (the API names are all caps, so lowerCamel would be unreadable)
    "INDID": "industryCode", "INDDESC": "description", "CLASSID": "classCode", "CLASSDESC": "description",
    "SUBCLASSID": "subclassId", "SUBCLASSCODE": "subclassCode", "SUBCLASSDESC": "description",
    "PICID": "picId", "PICCODE": "picCode", "PICDESC": "description", "PRODID": "productId", "PRODDESC": "description",
    "CLASSCODE": "classCode", "PRODCLASS": "classCode", "GROUPCODE": "groupCode", "PRODUCTCODE": "productCode",
}


def pairs_for(row, skip=()):
    out = []
    for k, v in row.items():
        if k in skip or v is None or (isinstance(v, str) and v.strip() == ""):
            continue
        out.append((f"ex:{NAMES.get(k, mapper.camel(k))}", mapper.scalar(k, v)))
    return out


def convert(snap, out):
    snap = Path(snap)
    stamp = snap.name
    fh = open(out, "w", encoding="utf-8", newline="\n")
    fh.write(common.prefixes({"ex": fda_iri.ns(C)}) + "\n")
    T = [0]

    def block(iri, pairs, kind, key):
        pairs += common.provenance(f"fda/pcb/{kind}", key, source_url=DOCS, retrieved_at=stamp)
        T[0] += common.write_block(fh, f"<{iri}>", pairs)

    n = defaultdict(int)
    # industries, with their subclass and PIC lists
    ind_sub = by_industry(snap, "industrysubclass")
    ind_pic = by_industry(snap, "industrypic")
    sub_by_code = {ind: {r["SUBCLASSCODE"]: r["SUBCLASSID"] for r in rs} for ind, rs in ind_sub.items()}
    pic_by_code = {ind: {r["PICCODE"]: r["PICID"] for r in rs} for ind, rs in ind_pic.items()}
    industries = rows(snap / "industry.json")
    for r in industries:
        ind = str(r["INDID"])
        pairs = [("a", "ex:ImportIndustry")] + pairs_for(r)
        for s in ind_sub.get(ind, []):
            pairs.append(("ex:hasSubclass", f"<{subclass_iri(s['SUBCLASSID'])}>"))
        for p in ind_pic.get(ind, []):
            pairs.append(("ex:hasProcessIndicator", f"<{pic_iri(p['PICID'])}>"))
        pairs.append(("rdfs:label", common.lit(f"{ind} {r.get('INDDESC', '')}".strip())))
        block(industry_iri(ind), pairs, "industry", ind)
        n["industries"] += 1
    # classes (per industry)
    classes = set()
    for r in rows(snap / "class.json"):
        ind, cls = str(r["INDID"]), str(r["CLASSID"])
        classes.add((ind, cls))
        pairs = [("a", "ex:ImportProductClass"), ("ex:hasIndustry", f"<{industry_iri(ind)}>")] + pairs_for(r)
        pairs.append(("rdfs:label", common.lit(f"{ind}{cls} {r.get('CLASSDESC', '')}".strip())))
        block(class_iri(ind, cls), pairs, "class", f"{ind}{cls}")
        n["classes"] += 1
    # subclasses and PICs (global ids)
    subs = set()
    for r in rows(snap / "subclass.json"):
        subs.add(r["SUBCLASSID"])
        pairs = [("a", "ex:ImportProductSubclass")] + pairs_for(r)
        pairs.append(("rdfs:label", common.lit(f"Subclass {r.get('SUBCLASSCODE', '')}: {r.get('SUBCLASSDESC', '')}".strip())))
        block(subclass_iri(r["SUBCLASSID"]), pairs, "subclass", str(r["SUBCLASSID"]))
        n["subclasses"] += 1
    pics = set()
    for r in rows(snap / "pic.json"):
        pics.add(r["PICID"])
        pairs = [("a", "ex:ImportProcessIndicator")] + pairs_for(r)
        pairs.append(("rdfs:label", common.lit(f"PIC {r.get('PICCODE', '')}: {r.get('PICDESC', '')}".strip())))
        block(pic_iri(r["PICID"]), pairs, "pic", str(r["PICID"]))
        n["pics"] += 1
    # subclasses / PICs that appear only in a per-industry list
    for ind, rs in ind_sub.items():
        for r in rs:
            if r["SUBCLASSID"] in subs:
                continue
            subs.add(r["SUBCLASSID"])
            pairs = [("a", "ex:ImportProductSubclass")] + pairs_for(r)
            pairs.append(("rdfs:label", common.lit(f"Subclass {r.get('SUBCLASSCODE', '')}: {r.get('SUBCLASSDESC', '')}".strip())))
            block(subclass_iri(r["SUBCLASSID"]), pairs, "subclass", str(r["SUBCLASSID"]))
            n["subclasses"] += 1
    for ind, rs in ind_pic.items():
        for r in rs:
            if r["PICID"] in pics:
                continue
            pics.add(r["PICID"])
            pairs = [("a", "ex:ImportProcessIndicator")] + pairs_for(r)
            pairs.append(("rdfs:label", common.lit(f"PIC {r.get('PICCODE', '')}: {r.get('PICDESC', '')}".strip())))
            block(pic_iri(r["PICID"]), pairs, "pic", str(r["PICID"]))
            n["pics"] += 1
    # products (industry + class + group -> description)
    prod_by_key = defaultdict(list)     # (ind, class, group) -> [prodid]
    for r in rows(snap / "product.json"):
        ind, pid = str(r["INDID"]), r["PRODID"]
        cls, grp = str(r.get("CLASSCODE") or ""), str(r.get("GROUPCODE") or "")
        prod_by_key[(ind, cls, grp)].append(pid)
        pairs = [("a", "ex:ImportProduct"), ("ex:hasIndustry", f"<{industry_iri(ind)}>")] + pairs_for(r)
        if (ind, cls) in classes:
            pairs.append(("ex:hasClass", f"<{class_iri(ind, cls)}>"))
        pairs.append(("rdfs:label", common.lit(f"{ind}{cls}--{grp} {r.get('PRODDESC', '')}".strip())))
        block(product_iri(ind, pid), pairs, "product", f"{ind}:{pid}")
        n["products"] += 1
    # full product codes
    unres = defaultdict(int)
    for ind, rs in sorted(by_industry(snap, "productcodeindustry").items()):
        for r in rs:
            code = str(r["PRODUCTCODE"]).strip()
            if len(code) != 7:
                unres["bad-length"] += 1
            i2, cls, sub, pic, grp = code[:2], code[2:3], code[3:4], code[4:5], code[5:7]
            pairs = [("a", "ex:ImportProductCode"), ("ex:productCode", common.lit(code)), ("ex:industryCode", common.lit(i2)),
                     ("ex:hasIndustry", f"<{industry_iri(i2)}>")]
            if (i2, cls) in classes:
                pairs.append(("ex:hasClass", f"<{class_iri(i2, cls)}>"))
            else:
                unres["class"] += 1
            sid = sub_by_code.get(i2, {}).get(sub)
            if sid is not None:
                pairs.append(("ex:hasSubclass", f"<{subclass_iri(sid)}>"))
            elif sub != "-":
                unres["subclass"] += 1
            pid = pic_by_code.get(i2, {}).get(pic)
            if pid is not None:
                pairs.append(("ex:hasProcessIndicator", f"<{pic_iri(pid)}>"))
            elif pic != "-":
                unres["pic"] += 1
            prods = prod_by_key.get((i2, cls, grp), [])
            for p in prods:
                pairs.append(("ex:hasProduct", f"<{product_iri(i2, p)}>"))
            if not prods:
                unres["product"] += 1
            pairs.append(("rdfs:label", common.lit(code)))
            block(code_iri(code), pairs, "productcode", code)
            n["codes"] += 1
    fh.close()
    print(f"pcb -> {Path(out).name}: {dict(n)}, unresolved parts {dict(unres)}, {T[0]} triples")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    convert(sys.argv[1], sys.argv[2])
