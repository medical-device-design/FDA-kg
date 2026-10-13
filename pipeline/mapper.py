#!/usr/bin/env python3
"""
mapper.py -- the generic JSON-record -> Turtle mapper shared by every openFDA converter.

What it does with ONE record (a dict):
  * the record becomes a node at the IRI the caller minted
  * every scalar field becomes ex:<lowerCamel(key)> with a typed literal
    (bool -> xsd:boolean, int -> xsd:integer, Decimal -> xsd:decimal, str -> string;
     keys listed in date_fields -> xsd:date via common.date_lit, which keeps bad dates
     as plain strings instead of emitting invalid typed literals)
  * every nested object becomes a child node under the record
    (<record>/<section>/<uuid or index>), linked by ex:<lowerCamel(key)> and typed
    ex:<ClassPrefix><Section>; lists of scalars become repeated properties
  * nothing is dropped. Field names are kept (lowerCamel), values are kept verbatim.
  * the caller may pass extra (predicate, object) pairs for the top node: label,
    cross-graph links, provenance

Determinism: same record, same IRI -> same text. No timestamps, no counters.
"""
import re
from datetime import datetime, timezone
from decimal import Decimal

import common
import fda_iri

RAW_TEXT_KEYS = {"molfile"}            # whitespace is meaningful, never strip
_US_DATE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")
_WORDS = re.compile(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])")


_DT_TIME = re.compile(r"^(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}$")
_MON_DATE = re.compile(r"^([A-Za-z]{3,9})\.? (\d{1,2}), (\d{4})$")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def date_lit(v):
    """common.date_lit plus the other shapes FDA files use:
    MM/DD/YYYY (shortages, CRLs, tobacco, warning letters), 'YYYY-MM-DD hh:mm:ss'
    (Drugs@FDA tables), 'Jul 13, 2026' (Orange Book), 'August 6, 2026' (Purple Book).
    A value that is not a real date stays a plain string with its original text."""
    s = str(v).strip() if v is not None else ""
    if not s:
        return None
    m = _US_DATE.match(s)
    if m:
        mm, dd, yyyy = m.groups()
    else:
        m = _DT_TIME.match(s)
        if m:
            return common.date_lit(m.group(1))
        m = _MON_DATE.match(s)
        if not m or m.group(1)[:3].lower() not in _MONTHS:
            return common.date_lit(v)
        mm, dd, yyyy = f"{_MONTHS[m.group(1)[:3].lower()]:02d}", f"{int(m.group(2)):02d}", m.group(3)
    typed = common.date_lit(f"{yyyy}{mm}{dd}")
    return typed if typed.endswith("^^xsd:date") else common.lit(s)


def words(key):
    return [w.lower() for w in _WORDS.findall(str(key))] or ["x"]


def camel(key):
    w = words(key)
    return w[0] + "".join(x.capitalize() for x in w[1:])


def pascal(key):
    return "".join(x.capitalize() for x in words(key))


def kebab(key):
    return "-".join(words(key))


def scalar(key, v, date_fields=frozenset()):
    """Typed literal for one scalar value, or None if blank."""
    if isinstance(v, bool):
        return common.bool_lit("true" if v else "false")
    if isinstance(v, int):
        return f'"{v}"^^xsd:integer'
    if isinstance(v, Decimal):
        return f'"{format(v, "f")}"^^xsd:decimal'
    if isinstance(v, float):
        return f'"{repr(v)}"^^xsd:double'
    if v is None:
        return None
    if key in date_fields:
        return date_lit(v)
    if key in RAW_TEXT_KEYS:
        s = str(v)
        return f'"{common.esc(s)}"' if s.strip() else None
    return common.lit(v)


def epoch_twin(key, v):
    """GSRS stores some dates as epoch milliseconds; add an xsd:dateTime twin."""
    if key.lower().endswith("date") and isinstance(v, int) and v > 10**11:
        dt = datetime.fromtimestamp(v / 1000, tz=timezone.utc)
        return (f"ex:{camel(key)}Time",
                f'"{dt.strftime("%Y-%m-%dT%H:%M:%SZ")}"^^xsd:dateTime')
    return None


class Mapper:
    """Writes nodes through common.write_block and counts what it wrote."""

    def __init__(self, out, class_prefix="", date_fields=(), skip_keys=(), child_iri=None):
        self.out = out
        self.class_prefix = class_prefix
        self.date_fields = frozenset(date_fields)
        self.skip_keys = frozenset(skip_keys)      # handled by the caller instead
        # optional hook (key, item) -> IRI, so a nested object that IS a shared
        # entity (e.g. a package NDC) gets its canonical IRI instead of a path
        self.child_iri = child_iri
        self.triples = self.nodes = 0
        self.unsafe_uuids = 0

    def block(self, iri, pairs):
        n = common.write_block(self.out, f"<{iri}>", pairs)
        self.triples += n
        self.nodes += 1 if n else 0

    def map_obj(self, iri, obj, cls=None, extra=(), top=False):
        """Emit the node for dict `obj` at `iri`, children first, own block last.
        Returns the list of (predicate, object) pairs written for this node."""
        pairs = [("a", f"ex:{cls}")] if cls else []
        children = []
        for key in sorted(obj):
            if top and key in self.skip_keys:
                continue
            v = obj[key]
            p = f"ex:{camel(key)}"
            if isinstance(v, dict):
                children.append((p, key, None, v))
            elif isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, dict):
                        children.append((p, key, i, item))
                    elif isinstance(item, list):
                        pairs.append((p, common.lit(str(item))))
                    else:
                        pairs.append((p, scalar(key, item, self.date_fields)))
            else:
                pairs.append((p, scalar(key, v, self.date_fields)))
                twin = epoch_twin(key, v)
                if twin:
                    pairs.append(twin)

        for p, key, i, item in children:
            u = item.get("uuid") if isinstance(item, dict) else None
            seg = u.strip() if isinstance(u, str) and _SAFE.match(u.strip()) else None
            if seg is None and u:
                self.unsafe_uuids += 1
            seg = seg or (str(i) if i is not None else None)
            c_iri = self.child_iri(key, item) if self.child_iri else None
            if not c_iri:
                c_iri = fda_iri.child(iri, kebab(key), seg) if seg else \
                    fda_iri.child(iri, kebab(key))
            pairs.append((p, f"<{c_iri}>"))
            self.map_obj(c_iri, item, cls=f"{self.class_prefix}{pascal(key)}")
        self.block(iri, pairs + list(extra))
        return pairs


def _selftest():
    import io
    buf = io.StringIO()
    m = Mapper(buf, class_prefix="X", date_fields={"when"})
    rec = {"id": "A1", "when": "20240102", "bad": "20249999", "n": 3, "ok": True,
           "tags": ["a", "b"], "sub": [{"k": 1}, {"k": 2, "uuid": "u-2"}], "obj": {"z": "q"}}
    m.map_obj("https://x/id/t/a1", rec, cls="Top", extra=[("rdfs:label", '"A1"')], top=True)
    t = buf.getvalue()
    assert '<https://x/id/t/a1/sub/0>\n    a ex:XSub ;\n    ex:k "1"^^xsd:integer .' in t
    assert "<https://x/id/t/a1/sub/u-2>" in t
    assert "<https://x/id/t/a1/obj>\n    a ex:XObj ;" in t
    assert 'ex:when "2024-01-02"^^xsd:date' in t
    assert 'ex:bad "20249999"' in t
    assert date_lit("01/19/2023") == '"2023-01-19"^^xsd:date'
    assert date_lit("13/40/2023") == "\"13/40/2023\""
    assert date_lit("2003-07-28 00:00:00") == '"2003-07-28"^^xsd:date'
    assert date_lit("Jul 13, 2026") == '"2026-07-13"^^xsd:date'
    assert date_lit("August 6, 2026") == '"2026-08-06"^^xsd:date'
    assert date_lit("Foo 6, 2026") == '"Foo 6, 2026"'
    assert date_lit("") is None
    assert 'ex:ok "true"^^xsd:boolean' in t
    assert 'ex:tags "a" ;\n    ex:tags "b"' in t
    assert t.rstrip().endswith('rdfs:label "A1" .')
    assert m.nodes == 4
    print(f"mapper.py self-test PASSED ({m.triples} triples, {m.nodes} nodes).")


if __name__ == "__main__":
    _selftest()
