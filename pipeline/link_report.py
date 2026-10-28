#!/usr/bin/env python3
"""
link_report.py -- cross-graph link resolution report for the FDA graphs (read-only).

Scans every L1 file under out/<graph>/ (ttl and ttl.gz), collects the IRIs each graph declares
(subjects with an rdf:type line) and every object link to a bmedesign.org IRI, then reports, per
(source graph, predicate, target graph), how many links resolve to a declared node, how many do
not, and the top unresolved kinds. Writes the report as text, the unresolved IRIs per
(target graph, kind) as a JSON summary, and (with --dump) every unresolved IRI as
"<target graph>\t<kind>\t<iri>\t<source graph>\t<predicate>" lines for the stub pass (l2_stubs_all.py).
Skip every l2_stubs.ttl (--skip l2_stubs.ttl) when the dump feeds the stub pass, so stubs are
derived from L1 alone.

Usage: python3 link_report.py <out_root> <report.txt> <unresolved.json> [--dump unresolved.tsv] [--skip name ...]
"""
import gzip
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

_SUBJ = re.compile(r"^<(https://bmedesign\.org/[^>]+)>\s*$")
_LINK = re.compile(r"^\s+(ex:\w+) <(https://bmedesign\.org/([a-z-]+)/id/([^/>]+)/[^>]*)>")
_TYPE = re.compile(r"^    a ex:")


def opener(p):
    return gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else open(p, encoding="utf-8")


def main(argv):
    root, rep, unres = Path(argv[1]), Path(argv[2]), Path(argv[3])
    dump = Path(argv[argv.index("--dump") + 1]) if "--dump" in argv else None
    skip = set(argv[argv.index("--skip") + 1:]) if "--skip" in argv else set()
    declared = set()
    links = Counter()               # (src graph, pred, tgt graph, kind) -> n
    targets = defaultdict(set)      # (src graph, pred, tgt graph, kind) -> target iris
    graphs = sorted(d for d in root.iterdir() if d.is_dir() and d.name.startswith("fda-"))
    for g in graphs:
        for f in sorted(p for p in g.iterdir() if p.suffix in (".ttl", ".gz")):
            if f.name in skip:
                print(f"skip {g.name}/{f.name}", file=sys.stderr)
                continue
            n_decl = 0
            with opener(f) as fh:
                cur = None
                for line in fh:
                    m = _SUBJ.match(line)
                    if m:
                        cur = m.group(1)
                        continue
                    if cur and _TYPE.match(line):
                        declared.add(cur)
                        n_decl += 1
                        cur = None
                        continue
                    m = _LINK.match(line)
                    if m:
                        key = (g.name, m.group(1), m.group(3), m.group(4))
                        links[key] += 1
                        targets[key].add(m.group(2))
            print(f"{g.name}/{f.name}: {n_decl} declared", file=sys.stderr)
    lines = [f"declared IRIs: {len(declared)}", "",
             f"{'source graph':24} {'predicate':22} {'target graph':24} {'kind':22} {'links':>10} {'distinct':>9} {'unresolved':>10}"]
    out = {}
    dfh = open(dump, "w", encoding="utf-8") if dump else None
    for key in sorted(links):
        src, pred, tgt, kind = key
        tg = targets[key]
        missing = [t for t in tg if t not in declared]
        lines.append(f"{src:24} {pred:22} {tgt:24} {kind:22} {links[key]:>10} {len(tg):>9} {len(missing):>10}")
        if missing:
            out[f"{src}|{pred}|{tgt}|{kind}"] = {"links": links[key], "distinct": len(tg), "unresolved": len(missing),
                                                 "sample": sorted(missing)[:5]}
            if dfh:
                for t in sorted(missing):
                    dfh.write(f"{tgt}\t{kind}\t{t}\t{src}\t{pred}\n")
    if dfh:
        dfh.close()
    rep.write_text("\n".join(lines) + "\n", encoding="utf-8")
    unres.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    main(sys.argv)
