#!/usr/bin/env python3
"""
l2_term_text.py -- put the adverse-event reaction term text back into the public graphs.

The L1 files were built with --publish, which dropped the MedDRA preferred-term text pending the
license question. On November 4, 2026 the MSSO Help Desk confirmed that the PT term text as FDA
publishes it may be republished (codes and hierarchy may not). This pass reads the text from the
raw snapshots again and writes it as a separate public file per source, attached to the same
nodes the L1 files declare, so nothing large is rebuilt:

  faers    <report/<id>/patient/reaction/<i>>  ex:reactionmeddrapt "text"      (62 M reactions)
  vaers    <vaers-report/<id>/symptoms/<n>>     ex:symptom1 .. ex:symptom5 "text"
  caers    <caers-report/<n>>                   ex:reactions "text" (one per reaction)
  cosmetic <cosmetic-event/<n>>                 ex:reactions "text"

Text is written verbatim (no normalization, no mapping). Outputs: out/<graph>/l2_term_text_<source>.ttl.gz.

Usage: python3 l2_term_text.py faers|vaers|caers|cosmetic <snapshot_dir> <out.ttl.gz> [--workers N]
"""
import csv
import gzip
import io
import re
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

E = "fda-drug-event-kg"
F = "fda-food-cosmetic-kg"


def _faers_zip(zpath):
    import ijson
    buf, n = io.StringIO(), 0
    with zipfile.ZipFile(zpath) as zf:
        for name in sorted(zf.namelist()):
            with zf.open(name) as fh:
                rid, idx, terms = None, -1, []
                for prefix, event, value in ijson.parse(fh):
                    if prefix == "results.item":
                        if event == "start_map":
                            rid, idx, terms = None, -1, []
                        elif event == "end_map" and rid is not None:
                            riri = fda_iri.drug_event_report(rid)
                            for i, t in terms:
                                lit = common.lit(t)
                                if lit:
                                    buf.write(f"<{riri}/patient/reaction/{i}>\n    ex:reactionmeddrapt {lit} .\n\n")
                                    n += 1
                    elif prefix == "results.item.safetyreportid":
                        rid = value
                    elif prefix == "results.item.patient.reaction.item" and event == "start_map":
                        idx += 1
                    elif prefix == "results.item.patient.reaction.item.reactionmeddrapt":
                        terms.append((idx, value))
    return buf.getvalue(), n


def faers(snap, out, workers):
    zips = sorted(Path(snap).glob("*.json.zip"))
    total = 0
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
        with Pool(workers) as pool:
            for k, (text, n) in enumerate(pool.imap(_faers_zip, zips), 1):
                fh.write(text)
                total += n
                if k % 100 == 0 or k == len(zips):
                    print(f"  {k}/{len(zips)} partitions, {total} reaction texts", file=sys.stderr, flush=True)
    return total


def vaers(snap, out):
    """Same member order, same duplicate-member skip and same per-report sequence as l1_vaers.py,
    so the text lands on the node l1_vaers.py declared (November 7, 2026)."""
    import collections
    import l1_vaers
    total = 0
    seen = set()
    seq = collections.Counter()
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
        for zpath in sorted(Path(snap).glob("*.zip")):
            with zipfile.ZipFile(zpath) as zf:
                for name in sorted(zf.namelist()):
                    if not re.search(r"VAERSSYMPTOMS\.csv$", name, re.I):
                        continue
                    if name in seen:
                        continue
                    seen.add(name)
                    for i, row in enumerate(csv.DictReader(l1_vaers.open_member(zf, name))):
                        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
                        vid = row.get("VAERS_ID")
                        if not vid:
                            continue
                        seq[(vid, "sym")] += 1
                        n = str(seq[(vid, "sym")])
                        pairs = [(f"ex:symptom{k}", common.lit(row.get(f"SYMPTOM{k}"))) for k in range(1, 6) if row.get(f"SYMPTOM{k}")]
                        if pairs:
                            total += common.write_block(fh, f"<{l1_vaers.report_iri(vid)}/symptoms/{fda_iri.slug(n)}>", pairs)
    return total


def openfda_reactions(snap, out, iri_fn):
    import ijson
    total = 0
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(F)}) + "\n")
        for z in sorted(Path(snap).glob("*.json.zip")):
            with zipfile.ZipFile(z) as zf:
                for name in sorted(zf.namelist()):
                    with zf.open(name) as fh_in:
                        for rec in ijson.items(fh_in, "results.item"):
                            rn = rec.get("report_number")
                            if not rn:
                                continue
                            pairs = [("ex:reactions", common.lit(t)) for t in rec.get("reactions") or []]
                            if pairs:
                                total += common.write_block(fh, f"<{iri_fn(rn)}>", pairs)
    return total


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    mode, snap, out = sys.argv[1:4]
    workers = int(sys.argv[sys.argv.index("--workers") + 1]) if "--workers" in sys.argv else 4
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if mode == "faers":
        n = faers(snap, out, workers)
    elif mode == "vaers":
        n = vaers(snap, out)
    elif mode == "caers":
        n = openfda_reactions(snap, out, fda_iri.caers_report)
    elif mode == "cosmetic":
        n = openfda_reactions(snap, out, fda_iri.cosmetic_event)
    else:
        raise SystemExit(__doc__)
    print(f"{mode} -> {Path(out).name}: {n} triples")
