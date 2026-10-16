#!/usr/bin/env python3
"""
l2_tobacco_links.py -- link Searchable Tobacco Products Database products to the tobacco
marketing orders (fda.gov/media/112123) on normalized company + product name, since the
orders list carries no STN.

Match key: lowercase, punctuation and the words inc/llc/ltd/corp/co/company removed, spaces
collapsed, for both the company and the product. A product node gets ex:hasMarketingOrder
for every order with the same key. The L1 files are untouched.

Usage: python3 l2_tobacco_links.py <out_dir/fda-tobacco-kg> <out.ttl>
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

T = "fda-tobacco-kg"
_SUBJ = re.compile(r"^<([^>]+)>\s*$")
_LIT = re.compile(r'^\s+ex:(\w+) "((?:[^"\\]|\\.)*)"')
_STOP = {"inc", "llc", "ltd", "corp", "co", "company", "corporation", "incorporated", "the", "dba", "lp", "l.p"}


def key(s):
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower().replace("&", " and "))
    return " ".join(w for w in s.split() if w not in _STOP)


def blocks(path):
    cur, props = None, {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = _SUBJ.match(line)
            if m:
                cur, props = m.group(1), {}
                continue
            if cur is None:
                continue
            if line.startswith("    a ex:"):
                props["_class"] = line.split("ex:")[1].split()[0]
            m = _LIT.match(line)
            if m:
                props.setdefault(m.group(1), m.group(2).replace('\\"', '"'))
            if line.rstrip().endswith(" ."):
                yield cur, props
                cur = None


def main(gdir, out):
    gdir = Path(gdir)
    orders = {}
    for iri, p in blocks(gdir / "tobacco_marketing_orders.ttl"):
        if p.get("_class") == "TobaccoMarketingOrder" and p.get("company") and p.get("product"):
            orders.setdefault((key(p["company"]), key(p["product"])), []).append(iri)
    n_links = n_products = 0
    products_matched = set()
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(T)}) + "\n")
        for iri, p in blocks(gdir / "tobacco_products.ttl"):
            if p.get("_class") != "TobaccoProduct":
                continue
            n_products += 1
            hits = orders.get((key(p.get("company", "")), key(p.get("productName", ""))), [])
            if hits:
                products_matched.add(iri)
                pairs = [("ex:hasMarketingOrder", f"<{o}>") for o in sorted(set(hits))]
                common.write_block(fh, f"<{iri}>", pairs)
                n_links += len(pairs)
    print(f"tobacco links: {n_products} products, {len(orders)} distinct order keys, "
          f"{len(products_matched)} products linked, {n_links} links -> {Path(out).name}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
