#!/usr/bin/env python3
"""
l2_stubs.py -- stub nodes for IRIs that L1 files reference but never declare.

L1 keeps every source row and links it to the canonical IRI of the application, package
NDC or firm it names. When the owning source does not list that entity (an Orange Book
application absent from Drugs@FDA, a shortage package not in the NDC Directory), the link
dangles. This L2 step scans a graph's Turtle files, finds every object of the link
predicates that has no rdf:type block anywhere in the graph, and writes one stub node per
missing IRI: type, label, the source files that referenced it, and ex:isStub true so
queries can tell stubs from source-backed nodes.

Deterministic: output sorted by IRI, no timestamps.

Usage:
  python3 l2_stubs.py <graph_dir> <out.ttl>
"""
import gzip
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

# predicate -> (kind path segment, class, label maker)
RULES = {
    "ex:hasApplication": ("application", "DrugApplication",
                          lambda seg: seg.upper()),
    "ex:hasPackageNdc":  ("ndc-package", "NdcPackage",
                          lambda seg: seg.replace("_", "-")),
    "ex:hasRecallingFirm": ("recalling-firm", "RecallingFirm", lambda seg: seg),
    "ex:hasFirm":        ("recalling-firm", "RecallingFirm", lambda seg: seg),
}
_SUBJ = re.compile(r"^<([^>]+)>\s*$")
_LINK = re.compile(r"^\s+(ex:\w+) <([^>]+)>")


def opener(p):
    return gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else open(p, encoding="utf-8")


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    gdir, out = Path(argv[1]), Path(argv[2])
    graph = gdir.name
    assert graph in fda_iri.GRAPHS, graph
    files = sorted(p for p in gdir.iterdir() if p.suffix in (".ttl", ".gz") and p.name != out.name)
    declared = set()
    refs = {}           # iri -> (predicate, set(files))
    for f in files:
        with opener(f) as fh:
            cur = None
            for line in fh:
                m = _SUBJ.match(line)
                if m:
                    cur = m.group(1)
                    continue
                if cur and line.startswith("    a ex:"):
                    declared.add(cur)
                    cur = None
                    continue
                m = _LINK.match(line)
                if m and m.group(1) in RULES:
                    r = refs.setdefault(m.group(2), (m.group(1), set()))
                    r[1].add(f.name)
        print(f"  scanned {f.name}: {len(declared)} declared so far, {len(refs)} referenced", file=sys.stderr)
    missing = sorted(i for i in refs if i not in declared)
    base = fda_iri.id_base(graph)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(graph)}) + "\n")
        for iri in missing:
            pred, srcs = refs[iri]
            kind, cls, label = RULES[pred]
            if not iri.startswith(base + kind + "/"):
                continue        # a link into another graph; that graph owns the node
            seg = iri[len(base) + len(kind) + 1:]
            pairs = [("a", f"ex:{cls}"), ("rdfs:label", common.lit(label(seg))),
                     ("ex:isStub", '"true"^^xsd:boolean')]
            pairs += [("ex:referencedBy", common.lit(s)) for s in sorted(srcs)]
            common.write_block(fh, f"<{iri}>", pairs)
            n += 1
    print(f"{graph}: {len(declared)} declared, {len(refs)} referenced, {len(missing)} missing, {n} stubs -> {out.name}")


if __name__ == "__main__":
    main(sys.argv)
