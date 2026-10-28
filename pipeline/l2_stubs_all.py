#!/usr/bin/env python3
"""
l2_stubs_all.py -- stub nodes for every IRI the seven graphs reference but none declares,
from the link_report.py dump (--dump unresolved.tsv: target graph, kind, iri, source graph,
predicate per line).

Each stub is written into the graph that OWNS the IRI (its namespace), never into the graph
that referenced it: a DECRS establishment pointing at an FEI the Data Dashboard has not
published gets a Firm stub in fda-compliance-kg; a shortage package not in the NDC Directory
gets an NdcPackage stub in fda-drug-biologic-kg. One stub per IRI: type, label, the key
(feiNumber, unii, ...), ex:isStub true (the shapes accept that in place of provenance) and one
ex:referencedBy per (source graph, predicate). Output out/<graph>/l2_stubs.ttl, sorted by IRI,
no timestamps. Supersedes l2_stubs.py (same-graph only).

Usage: python3 l2_stubs_all.py <unresolved.tsv> <out_root>
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

# (graph, kind) -> (class, key property or None, label maker)
RULES = {
    ("fda-compliance-kg", "firm"): ("Firm", "ex:feiNumber", lambda s: f"FEI {s}"),
    ("fda-compliance-kg", "recalling-firm"): ("RecallingFirm", None, lambda s: s),
    ("fda-drug-biologic-kg", "application"): ("DrugApplication", "ex:applicationNumber", lambda s: s.upper()),
    ("fda-drug-biologic-kg", "ndc-package"): ("NdcPackage", "ex:packageNdc", lambda s: s.replace("_", "-")),
    ("fda-drug-biologic-kg", "ndc-product"): ("NdcProduct", "ex:productId", lambda s: s),
    ("fda-substance-kg", "unii"): ("Substance", "ex:unii", lambda s: s.upper()),
    ("fda-substance-kg", "gsrs"): ("Substance", "ex:gsrsUuid", lambda s: s),
}


def main(tsv, root):
    root = Path(root)
    by_graph = defaultdict(lambda: defaultdict(set))     # graph -> iri -> {(kind, src, pred)}
    skipped = defaultdict(int)
    for line in Path(tsv).read_text(encoding="utf-8").splitlines():
        tgt, kind, iri, src, pred = line.rstrip("\n").split("\t")
        if (tgt, kind) not in RULES:
            skipped[(tgt, kind)] += 1
            continue
        by_graph[tgt][iri].add((kind, src, pred))
    for graph, iris in sorted(by_graph.items()):
        out = root / graph / "l2_stubs.ttl"
        base = fda_iri.id_base(graph)
        n = 0
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(common.prefixes({"ex": fda_iri.ns(graph)}) + "\n")
            for iri in sorted(iris):
                refs = iris[iri]
                kind = next(iter(refs))[0]
                cls, keyp, label = RULES[(graph, kind)]
                rest = iri[len(base) + len(kind) + 1:]
                if kind == "unii" and "/references/" in rest:
                    # a citation uuid a GSRS record cites but does not carry (unii/<x>/references/<uuid>)
                    unii, ref = rest.split("/references/", 1)
                    pairs = [("a", "ex:GsrsReferences"), ("ex:uuid", common.lit(ref)),
                             ("rdfs:label", common.lit(f"Reference {ref} of {unii.upper()}"))]
                elif kind == "application" and "/product/" in rest:
                    cls = "DrugProduct"
                    appl, prod = rest.split("/product/", 1)
                    pairs = [("a", "ex:DrugProduct"), ("ex:hasApplication", f"<{base}application/{appl}>"),
                             ("ex:productNumber", common.lit(prod)), ("rdfs:label", common.lit(f"{appl.upper()} product {prod}"))]
                else:
                    pairs = [("a", f"ex:{cls}"), ("rdfs:label", common.lit(label(rest)))]
                    if keyp:
                        pairs.append((keyp, common.lit(label(rest) if kind in ("unii", "ndc-package", "application") else rest)))
                pairs.append(("ex:isStub", '"true"^^xsd:boolean'))
                pairs += [("ex:referencedBy", common.lit(f"{s} {p}")) for _k, s, p in sorted(refs)]
                common.write_block(fh, f"<{iri}>", pairs)
                n += 1
        print(f"{graph}: {n} stubs -> {out}")
    if skipped:
        print(f"skipped (no rule): {dict(skipped)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2])
