#!/usr/bin/env python3
"""
stream_check.py -- full-coverage check of an L1 Turtle file against the node-level rules that
gen_shapes.py generates for its graph, in one streaming pass (gzip or plain), for files too big
for Jena SHACL (the FAERS graph: 18 billion triples).

The rules are read from gen_shapes.RECORDS[graph], the same source the SHACL files are made
from: label, provenance block (or ex:isStub true), link predicates in the right namespace, date
predicates typed xsd:date or plain string, and the per-class extras (minCount, maxCount, pattern,
datatype, sh:in, sh:hasValue). Every block (subject with its predicate lines) is checked; nothing
is sampled. Reports blocks per class, violations per (class, rule) with the first three subjects,
and lines it could not parse (which count as a failure of the check, not of the data).

This is a complement to Jena, not a replacement: run Jena on a sample of chunks of the same file
and confirm the two agree (scripts/validate_faers.sh does both).

Usage: python3 stream_check.py <graph> <file.ttl[.gz]> [more files ...]
"""
import gzip
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fda_iri      # noqa: E402
import gen_shapes   # noqa: E402

_SUBJ = re.compile(r"^<([^>]+)>\s*$")
_LINE = re.compile(r"^\s+(\S+) (.*?) ([;.])$")
_LINE_S = re.compile(r"^\s+(\S+) (.*?) ([;.])$", re.S)
_LIT = re.compile(r'^"((?:[^"\\]|\\.)*)"(?:\^\^(\S+)|@([A-Za-z-]+))?$')
_EXTRA = re.compile(r"sh:path (\S+)(.*)")
PROV = ("ex:sourceDataset", "ex:sourceRecordId", "ex:sourceUrl", "ex:retrievedAt")


def parse_extra(raw):
    """'sh:property [ sh:path ex:x ; sh:minCount 1 ; sh:maxCount 1 ; sh:pattern "..." ]' -> dict"""
    m = _EXTRA.search(raw)
    path, rest = m.group(1), m.group(2)
    r = {"path": path}
    for k in ("minCount", "maxCount"):
        mm = re.search(rf"sh:{k} (\d+)", rest)
        if mm:
            r[k] = int(mm.group(1))
    mm = re.search(r'sh:pattern "((?:[^"\\]|\\.)*)"', rest)
    if mm:
        r["pattern"] = re.compile(mm.group(1).replace("\\\\", "\\"))
    mm = re.search(r"sh:datatype (\S+)", rest)
    if mm:
        r["datatype"] = mm.group(1)
    mm = re.search(r"sh:in \(([^)]*)\)", rest)
    if mm:
        r["in"] = set(re.findall(r'"((?:[^"\\]|\\.)*)"', mm.group(1)))
    mm = re.search(r"sh:hasValue (\S+)", rest)
    if mm:
        r["hasValue"] = mm.group(1)
    return r


def rules_for(graph):
    out = {}
    for cls, cfg in gen_shapes.RECORDS[graph].items():
        links = {p: fda_iri.id_base(g) + kind + "/" for p, (g, kind) in cfg.get("links", {}).items()}
        out[f"ex:{cls}"] = {"prov": cfg.get("prov", True), "label": cfg.get("label", True), "links": links,
                            "dates": set(cfg.get("dates", [])), "extra": [parse_extra(x) for x in cfg.get("extra", [])]}
    return out


def opener(p):
    return gzip.open(p, "rt", encoding="utf-8") if str(p).endswith(".gz") else open(p, encoding="utf-8")


def check_block(subj, props, rules, viol, examples):
    types = [o for o in props.get("a", []) if o.startswith("ex:")]
    for t in types:
        r = rules.get(t)
        if not r:
            continue

        def bad(rule):
            viol[(t, rule)] += 1
            if len(examples[(t, rule)]) < 3:
                examples[(t, rule)].append(subj)

        labels = props.get("rdfs:label", [])
        if (r["prov"] or r["label"]) and not labels:
            bad("rdfs:label minCount 1")
        if r["prov"]:
            stub = any(_LIT.match(o) and _LIT.match(o).group(1) == "true" for o in props.get("ex:isStub", []))
            if not stub:
                for p in PROV:
                    if not props.get(p):
                        bad(f"{p} minCount 1")
                for o in props.get("ex:retrievedAt", []):
                    m = _LIT.match(o)
                    if not m or m.group(2) != "xsd:date":
                        bad("ex:retrievedAt xsd:date")
        for p, base in r["links"].items():
            for o in props.get(p, []):
                if not (o.startswith("<") and o.endswith(">") and re.match("^" + base, o[1:-1])):
                    bad(f"{p} IRI in {base}")
        for p in r["dates"]:
            for o in props.get(p, []):
                m = _LIT.match(o)
                if not m or m.group(2) not in (None, "xsd:date", "xsd:string"):
                    bad(f"{p} xsd:date or string")
        for e in r["extra"]:
            vals = props.get(e["path"], [])
            if "minCount" in e and len(vals) < e["minCount"]:
                bad(f"{e['path']} minCount {e['minCount']}")
            if "maxCount" in e and len(vals) > e["maxCount"]:
                bad(f"{e['path']} maxCount {e['maxCount']}")
            for o in vals:
                m = _LIT.match(o)
                lex = m.group(1) if m else o
                dt = m.group(2) if m else None
                if "pattern" in e and not e["pattern"].search(lex):
                    bad(f"{e['path']} pattern")
                if "datatype" in e and dt != e["datatype"]:
                    bad(f"{e['path']} datatype {e['datatype']}")
                if "in" in e and lex not in e["in"]:
                    bad(f"{e['path']} sh:in")
                if "hasValue" in e and lex != e["hasValue"]:
                    bad(f"{e['path']} hasValue {e['hasValue']}")


def main(graph, files):
    rules = rules_for(graph)
    blocks = Counter()
    viol = Counter()
    examples = defaultdict(list)
    unparsed = 0
    n_blocks = 0
    for f in files:
        subj, props, cont = None, defaultdict(list), None
        with opener(f) as fh:
            for line in fh:
                if cont is not None:                      # inside a literal that spans lines
                    cont += line
                    mm = _LINE_S.match(cont.rstrip("\n"))
                    if mm and (cont.count('"') - cont.count('\\"')) % 2 == 0:
                        props[mm.group(1)].append(mm.group(2))
                        cont = None
                    continue
                m = _SUBJ.match(line)
                if m:
                    if subj:
                        n_blocks += 1
                        for t in props.get("a", []):
                            blocks[t] += 1
                        check_block(subj, props, rules, viol, examples)
                    subj, props = m.group(1), defaultdict(list)
                    continue
                if line.startswith("@prefix") or not line.strip():
                    continue
                m = _LINE.match(line.rstrip("\n"))
                if not m:
                    if line.count('"') % 2 == 1:          # literal continues on the next line
                        cont = line
                        continue
                    unparsed += 1
                    continue
                props[m.group(1)].append(m.group(2))
            if subj:
                n_blocks += 1
                for t in props.get("a", []):
                    blocks[t] += 1
                check_block(subj, props, rules, viol, examples)
        print(f"scanned {f}", file=sys.stderr, flush=True)
    print(f"blocks: {n_blocks}; unparsed lines: {unparsed}")
    for t, n in sorted(blocks.items()):
        print(f"  {n:>12} {t}")
    if viol:
        print("violations:")
        for (t, rule), n in sorted(viol.items()):
            print(f"  {n:>10} {t} : {rule}   e.g. {examples[(t, rule)]}")
    else:
        print("violations: none")
    print("RESULT " + ("conforms" if not viol and not unparsed else "FAIL"))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
