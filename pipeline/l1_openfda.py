#!/usr/bin/env python3
"""
l1_openfda.py -- L1 converters for the Phase 1 openFDA sources.

    unii         other/unii         -> fda-substance-kg   (Substance)
    enforcement  food|drug/enforcement -> fda-compliance-kg (Recall, RecallEvent,
                                          RecallingFirm)

Rules (handoff section 0.3 and 5):
  * every source field is kept (no capping, no lossy cleaning)
  * IRIs come only from fda_iri.py, literals only from common.py, which is the
    device pipeline's own common.py copied unchanged
  * retrieved_at is the L0 snapshot date, never "now", so reruns are identical

Usage:
  python3 l1_openfda.py unii        <snapshot_dir> <out.ttl>
  python3 l1_openfda.py enforcement <snapshot_dir> <out.ttl> <product: food|drug>
"""
import io
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402  (device pipeline helper, copied unchanged)
import fda_iri     # noqa: E402

DATE_FIELDS = {"recall_initiation_date", "center_classification_date",
               "report_date", "termination_date"}
_CAMEL = re.compile(r"_([a-z0-9])")


def camel(field):
    return _CAMEL.sub(lambda m: m.group(1).upper(), field)


def load_results(snapshot_dir):
    """Yield records from every partition zip in the snapshot, in file order."""
    zips = sorted(Path(snapshot_dir).glob("*.json.zip"))
    if not zips:
        raise SystemExit(f"no partition zips in {snapshot_dir}")
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for name in sorted(zf.namelist()):
                with zf.open(name) as fh:
                    data = json.load(io.TextIOWrapper(fh, encoding="utf-8"))
                for rec in data.get("results", []):
                    yield rec


def snapshot_date(snapshot_dir):
    d = Path(snapshot_dir).name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d):
        raise SystemExit(f"snapshot folder must be named YYYY-MM-DD, got {d}")
    return d


def header(graph):
    return common.prefixes({"ex": fda_iri.ns(graph)}) + "\n"


class Writer:
    def __init__(self, out):
        self.out, self.triples, self.subjects = out, 0, 0

    def block(self, iri, pairs):
        n = common.write_block(self.out, f"<{iri}>", pairs)
        self.triples += n
        self.subjects += 1 if n else 0


# ---------------------------------------------------------------------------
def convert_unii(snapshot_dir, out_path):
    graph, dataset = "fda-substance-kg", "other/unii"
    stamp = snapshot_date(snapshot_dir)
    skipped = 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        out.write(header(graph))
        w = Writer(out)
        for r in load_results(snapshot_dir):
            unii = (r.get("unii") or "").strip()
            if not unii:
                skipped += 1
                continue
            pairs = [("a", "ex:Substance"),
                     ("rdfs:label", common.lit(r.get("substance_name"))),
                     ("ex:unii", common.lit(unii)),
                     ("ex:substanceName", common.lit(r.get("substance_name")))]
            extra = sorted(set(r) - {"unii", "substance_name"})
            for k in extra:                      # keep any future field too
                pairs.append((f"ex:{camel(k)}", common.lit(json.dumps(r[k])
                              if isinstance(r[k], (dict, list)) else r[k])))
            pairs += common.provenance(
                dataset, unii,
                source_url=f"https://api.fda.gov/other/unii.json?search=unii:%22{quote(unii)}%22",
                retrieved_at=stamp)
            w.block(fda_iri.substance(unii), pairs)
    return w, skipped


# ---------------------------------------------------------------------------
def convert_enforcement(snapshot_dir, out_path, product):
    graph = "fda-compliance-kg"
    dataset = f"{product}/enforcement"
    stamp = snapshot_date(snapshot_dir)
    firms, events, skipped = {}, {}, 0
    unnumbered, by_event = {}, 0
    with open(out_path, "w", encoding="utf-8", newline="\n") as out:
        out.write(header(graph))
        w = Writer(out)
        for r in load_results(snapshot_dir):
            rn = (r.get("recall_number") or "").strip()
            ev = (r.get("event_id") or "").strip()
            if rn:
                subj, label, rec_id = fda_iri.recall(rn), rn, rn
            elif ev:                      # no recall number yet: key by event
                unnumbered[ev] = unnumbered.get(ev, 0) + 1
                subj = fda_iri.recall_by_event(ev, unnumbered[ev])
                label = f"event {ev} recall {unnumbered[ev]} (no recall number)"
                rec_id = f"event:{ev}:{unnumbered[ev]}"
                by_event += 1
            else:
                skipped += 1
                continue
            pairs = [("a", "ex:Recall"), ("rdfs:label", common.lit(label))]
            for k in sorted(r):
                v = r[k]
                if k == "openfda":
                    continue
                if isinstance(v, (dict, list)):
                    v = json.dumps(v, sort_keys=True)
                obj = common.date_lit(v) if k in DATE_FIELDS else common.lit(v)
                pairs.append((f"ex:{camel(k)}", obj))

            if ev:
                pairs.append(("ex:hasRecallEvent", f"<{fda_iri.recall_event(ev)}>"))
                events.setdefault(ev, r.get("product_type"))
            fn = (r.get("recalling_firm") or "").strip()
            try:
                firm_iri = fda_iri.recalling_firm(fn)
            except ValueError:
                firm_iri = None
            if firm_iri:
                pairs.append(("ex:hasRecallingFirm", f"<{firm_iri}>"))
                firms.setdefault(firm_iri, fn)

            # openfda harmonized block: keep every value; UNII also links out
            ofda = r.get("openfda") or {}
            for k in sorted(ofda):
                for v in common.as_list(ofda[k]):
                    pairs.append((f"ex:openfda{camel('_' + k)}", common.lit(v)))
                    if k == "unii":
                        try:
                            pairs.append(("ex:hasSubstance",
                                          f"<{fda_iri.substance(v)}>"))
                        except ValueError:
                            pass
            search = (f"recall_number:%22{quote(rn)}%22" if rn
                      else f"event_id:%22{quote(ev)}%22")
            pairs += common.provenance(
                dataset, rec_id,
                source_url=f"https://api.fda.gov/{dataset}.json?search={search}",
                retrieved_at=stamp)
            w.block(subj, pairs)

        for ev in sorted(events):
            w.block(fda_iri.recall_event(ev),
                    [("a", "ex:RecallEvent"), ("rdfs:label", common.lit(ev)),
                     ("ex:eventId", common.lit(ev))])
        for iri in sorted(firms):
            w.block(iri, [("a", "ex:RecallingFirm"),
                          ("rdfs:label", common.lit(firms[iri]))])
    w.by_event = by_event
    return w, skipped


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    kind, snap, out = argv[1], argv[2], argv[3]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if kind == "unii":
        w, skipped = convert_unii(snap, out)
    elif kind == "enforcement":
        if len(argv) < 5 or argv[4] not in ("food", "drug", "device"):
            raise SystemExit("enforcement needs product food|drug")
        w, skipped = convert_enforcement(snap, out, argv[4])
    else:
        raise SystemExit(f"unknown source {kind}")
    print(f"{kind} {Path(out).name}: {w.subjects} subjects, {w.triples} triples, "
          f"{skipped} records skipped (no key), "
          f"{getattr(w, 'by_event', 0)} keyed by event id (no recall number)")


if __name__ == "__main__":
    main(sys.argv)
