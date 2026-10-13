#!/usr/bin/env python3
"""
l1_gsrs.py -- L1 converter for GSRS substances (openFDA other/substance)
               -> fda-substance-kg

The source is ONE JSON document (about 2.4 GB unzipped), so it is streamed one
record at a time with ijson. Memory stays flat whatever the file size.

Mapping (no field is dropped):
  * the record becomes the Substance node, IRI = fda_iri.substance_ref(unii, uuid)
    (UNII when present, otherwise the GSRS uuid), the SAME IRI unii.ttl mints
  * every scalar field becomes ex:<lowerCamel(key)> with a typed literal
  * every nested object becomes a child node under its substance
    (<substance>/<section>/<uuid or index>), linked by ex:<lowerCamel(key)>,
    typed ex:Gsrs<Section>, and mapped recursively the same way
  * an object carrying "refuuid" is a pointer to another substance: it is kept
    as a child node AND linked with ex:<key>Substance to that substance's IRI
  * strings inside a "references" list are citation uuids: they become links to
    the record's <substance>/references/<uuid> nodes
  * numbers stay exact (Decimal, never float), molfiles keep their whitespace,
    epoch-millisecond *date fields also get an xsd:dateTime twin
  * a few PRIMARY codes also get shortcut properties (ex:casNumber, ...) so the
    common joins (CAS, PubChem CID, DTXSID, RxCUI) need no extra hop

Usage:
  python3 l1_gsrs.py <snapshot_dir> <out.ttl> [--limit N]
"""
import re
import sys
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402  (device pipeline helper, copied unchanged)
import fda_iri     # noqa: E402

GRAPH, DATASET = "fda-substance-kg", "other/substance"
RAW_TEXT_KEYS = {"molfile"}            # whitespace is meaningful, never strip
CODE_SHORTCUTS = {                     # code_system -> shortcut property
    "CAS": "casNumber",
    "PUBCHEM": "pubchemCid",
    "EPA CompTox": "dtxsid",
    "RXCUI": "rxcui",
    "DRUG BANK": "drugbankId",
    "CHEBI": "chebiId",
    "ChEMBL": "chemblId",
    "ECHA (EC/EINECS)": "ecNumber",
    "MESH": "meshId",
    "NCI_THESAURUS": "nciThesaurusCode",
    "INN": "innId",
    "WIKIPEDIA": "wikipediaTitle",
}
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_WORDS = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


def words(key):
    return [w.lower() for w in _WORDS.findall(str(key))] or ["x"]


def camel(key):
    w = words(key)
    return w[0] + "".join(x.capitalize() for x in w[1:])


def pascal(key):
    return "".join(x.capitalize() for x in words(key))


def kebab(key):
    return "-".join(words(key))


def scalar(key, v):
    """Typed literal for one scalar value, or None if blank."""
    if isinstance(v, bool):
        return common.bool_lit("true" if v else "false")
    if isinstance(v, int):
        return f'"{v}"^^xsd:integer'
    if isinstance(v, Decimal):
        return f'"{format(v, "f")}"^^xsd:decimal'
    if isinstance(v, float):                       # not produced, kept for safety
        return f'"{repr(v)}"^^xsd:double'
    if v is None:
        return None
    if key in RAW_TEXT_KEYS:
        s = str(v)
        return f'"{common.esc(s)}"' if s.strip() else None
    return common.lit(v)


def epoch_twin(key, v):
    if key.lower().endswith("date") and isinstance(v, int) and v > 10**11:
        dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        return (f"ex:{camel(key)}Time",
                f'"{dt.strftime("%Y-%m-%dT%H:%M:%SZ")}"^^xsd:dateTime')
    return None


class Converter:
    def __init__(self, out, stamp):
        self.out, self.stamp = out, stamp
        self.triples = self.nodes = self.substances = self.skipped = 0
        self.code_systems = Counter()
        self.bad_refs = 0
        self.unsafe_uuids = 0

    def block(self, iri, pairs):
        n = common.write_block(self.out, f"<{iri}>", pairs)
        self.triples += n
        self.nodes += 1 if n else 0

    def map_obj(self, iri, obj, root, cls=None, extra=()):
        """Emit one node for dict `obj` at `iri`, recursing into children.
        Children are written first, the node's own block last."""
        pairs = [("a", f"ex:{cls}")] if cls else []
        children = []
        for key in sorted(obj):
            v = obj[key]
            p = f"ex:{camel(key)}"
            if isinstance(v, dict):
                children.append((p, key, None, v))
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        children.append((p, key, i, item))
                    elif key == "references" and isinstance(item, str) \
                            and _SAFE.match(item.strip()):
                        pairs.append((p, f"<{fda_iri.child(root, 'references', item)}>"))
                    else:
                        pairs.append((p, scalar(key, item)))
            else:
                pairs.append((p, scalar(key, v)))
                twin = epoch_twin(key, v)
                if twin:
                    pairs.append(twin)

        for p, key, i, item in children:
            u = item.get("uuid")
            seg = u.strip() if isinstance(u, str) and _SAFE.match(u.strip()) else None
            if seg is None and u:
                self.unsafe_uuids += 1
            seg = seg or (str(i) if i is not None else None)
            c_iri = fda_iri.child(iri, kebab(key), seg) if seg else \
                fda_iri.child(iri, kebab(key))
            pairs.append((p, f"<{c_iri}>"))
            if "refuuid" in item:
                try:
                    tgt = fda_iri.substance_ref(
                        item.get("unii") if _looks_unii(item) else None,
                        item.get("refuuid"))
                    pairs.append((f"ex:{camel(key)}Substance", f"<{tgt}>"))
                except ValueError:
                    self.bad_refs += 1
            self.map_obj(c_iri, item, root, cls=f"Gsrs{pascal(key)}")
        self.block(iri, pairs + list(extra))

    def record(self, rec):
        try:
            subj = fda_iri.substance_ref(rec.get("unii"), rec.get("uuid"))
        except ValueError:
            self.skipped += 1
            return
        self.substances += 1
        extra = [("rdfs:label", common.lit(display_name(rec)))]
        for c in rec.get("codes") or []:
            cs = c.get("code_system")
            self.code_systems[cs] += 1
            if cs in CODE_SHORTCUTS and c.get("type") == "PRIMARY":
                extra.append((f"ex:{CODE_SHORTCUTS[cs]}", common.lit(c.get("code"))))
        extra += common.provenance(
            DATASET, rec.get("uuid") or rec.get("unii"),
            source_url=f"https://gsrs.ncats.nih.gov/ginas/app/beta/substances/{rec.get('uuid')}",
            retrieved_at=self.stamp)
        self.map_obj(subj, rec, subj, cls="Substance", extra=extra)


def _looks_unii(item):
    u = item.get("unii") or ""
    return bool(re.fullmatch(r"[A-Z0-9]{10}", str(u).strip()))


def display_name(rec):
    names = rec.get("names") or []
    for test in (lambda n: n.get("display_name"), lambda n: n.get("preferred"),
                 lambda n: True):
        for n in names:
            if test(n) and n.get("name"):
                return n["name"]
    return rec.get("unii") or rec.get("uuid")


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    snap, out_path = Path(argv[1]), Path(argv[2])
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    stamp = snap.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise SystemExit("snapshot folder must be named YYYY-MM-DD")
    zips = sorted(snap.glob("*.json.zip"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n", buffering=1 << 20) as out:
        out.write(common.prefixes({"ex": fda_iri.ns(GRAPH)}) + "\n")
        conv = Converter(out, stamp)
        for z in zips:
            with zipfile.ZipFile(z) as zf:
                for name in sorted(zf.namelist()):
                    with zf.open(name) as fh:
                        for rec in ijson.items(fh, "results.item"):
                            conv.record(rec)
                            if limit and conv.substances >= limit:
                                break
    print(f"gsrs {out_path.name}: {conv.substances} substances, {conv.nodes} nodes, "
          f"{conv.triples} triples, {conv.skipped} skipped (no key), "
          f"{conv.bad_refs} unresolvable substance refs, "
          f"{conv.unsafe_uuids} non-IRI-safe uuids (indexed instead)")
    print("code systems:", dict(conv.code_systems.most_common(40)))


if __name__ == "__main__":
    main(sys.argv)
