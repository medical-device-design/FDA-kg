#!/usr/bin/env python3
"""gen_release_meta.py -- write ontology.ttl and void.ttl for one FDA graph release (v0.0.2 rules).

usage: gen_release_meta.py <shortname> <version> <snapshot YYYY-MM-DD> <out_dir> <file.ttl[.gz]> ...

ontology.ttl  declares every ex: class and predicate found in the files (owl:Class,
              owl:ObjectProperty when every object is an IRI, else owl:DatatypeProperty), plus the
              v0.0.1 names replaced in v0.0.2 as owl:deprecated with dcterms:isReplacedBy
              (bmedesign-kg ruling 2026-11-22-fda-products-v0.0.2, items 1 and 2).
void.ttl      from bmed_commons.void_ttl() (owl:versionInfo, dcterms:issued, CC0).

The scan is a streaming line scan of the pipeline's own Turtle layout (one subject block per
record, one "    predicate object ;" line per triple); it does not parse general Turtle.
"""
import gzip
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipeline"))
import bmed_commons as bc      # noqa: E402
import fda_iri                 # noqa: E402

DEPRECATED = {   # old v0.0.1 term -> replacement
    "ex:reactionmeddrapt": "ex:reactionpttext",
    "ex:reactionmeddraversionpt": "ex:reactionptversion",
    "ex:drugrecuractionmeddraversion": "ex:drugrecuractionptversion",
    "ex:meddraVersion": "ex:ptVersion",
    "ex:sourceDataset": f"<{bc.CORE}sourceDataset>",
    "ex:sourceRecordId": f"<{bc.CORE}sourceRecordId>",
    "ex:sourceUrl": f"<{bc.CORE}sourceUrl>",
    "ex:retrievedAt": f"<{bc.CORE}retrievedAt>",
}
TITLES = {
    "fda-drug-event-kg": ("FDA Drug and Vaccine Adverse Event Knowledge Graph (FAERS, VAERS)",
                          "FAERS and VAERS adverse event reports from openFDA and the VAERS downloads. "
                          "Reaction and symptom text is the MedDRA preferred-term text FDA publishes, kept as MSSO "
                          "permits; MedDRA codes and hierarchy are not included. CC0 1.0 for everything else.",
                          ["https://open.fda.gov/apis/drug/event/", "https://vaers.hhs.gov/data/datasets.html"]),
}
LINE = re.compile(r"^    (\S+) (.+?) [;.]$")


def opener(p):
    return gzip.open(p, "rt", encoding="utf-8") if str(p).endswith(".gz") else open(p, encoding="utf-8")


def scan(files):
    preds, classes = {}, set()
    for f in files:
        with opener(f) as fh:
            for line in fh:
                m = LINE.match(line.rstrip("\n"))
                if not m:
                    continue
                p, o = m.group(1), m.group(2)
                if p == "a":
                    classes.add(o)
                    continue
                if not p.startswith("ex:"):
                    continue
                is_iri = o.startswith("<") or (":" in o and not o.startswith('"'))
                k = preds.setdefault(p, [0, 0])
                k[0 if is_iri else 1] += 1
    return preds, classes


def main():
    sn, version, snap, out = sys.argv[1:5]
    files = sys.argv[5:]
    preds, classes = scan(files)
    ns = fda_iri.ns(sn)
    L = [f"@prefix ex: <{ns}> .", "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
         "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .", "@prefix dcterms: <http://purl.org/dc/terms/> .", "",
         f"<{ns}> a owl:Ontology ; owl:versionInfo \"{version}\" ; dcterms:license <{bc.CC0}> .", ""]
    for c in sorted(classes):
        if c.startswith("ex:"):
            L.append(f"{c} a owl:Class .")
    for p, (n_iri, n_lit) in sorted(preds.items()):
        kind = "owl:ObjectProperty" if n_iri and not n_lit else "owl:DatatypeProperty"
        L.append(f"{p} a {kind} .")
    L.append("")
    for old, new in DEPRECATED.items():
        if old in preds:
            raise SystemExit(f"{old} is still used in the release files; v0.0.2 must not emit it")
        L.append(f"{old} a rdf:Property ; owl:deprecated true ; dcterms:isReplacedBy {new} .")
    L.insert(0, "@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .")
    Path(out).mkdir(parents=True, exist_ok=True)
    Path(out, "ontology.ttl").write_text("\n".join(L) + "\n", encoding="utf-8")
    title, desc, sources = TITLES[sn]
    Path(out, "void.ttl").write_text(bc.void_ttl(f"https://purl.org/okn/frink/kg/{sn}", title, version, snap,
                                                 description=desc, sources=sources), encoding="utf-8")
    print(f"{sn}: {len(classes)} classes, {len(preds)} ex: predicates -> {out}/ontology.ttl, void.ttl")


if __name__ == "__main__":
    main()
