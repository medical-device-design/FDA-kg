#!/usr/bin/env python3
"""faers_dup_versions.py -- find every FAERS safetyreportid that occurs more than once in the
openFDA drug/event bulk partitions and decide which occurrence to keep.

openFDA's bulk export lists some report ids in two partitions (an earlier and a later version
of one case). The L1 build gave both the same IRI, so their values merged on one node.
The "keep" column marks the latest copy (highest safetyreportversion, then latest
transmissiondate). It is informational only: the release keeps every copy (option A, November 18,
2026), the n-th copy in partition order as report/<id>-n (faers_split_versions.awk).

Usage: faers_dup_versions.py <snapshot_dir> <dup_iris.txt> <out.tsv> [workers]
(dup_iris.txt: the report IRIs found twice by the link check, one <IRI> per line)
Output columns: iri, occurrence (1-based, in sorted partition order), partition, item,
safetyreportversion, transmissiondate, receivedate, keep (1/0)
"""
import sys, zipfile, collections
from multiprocessing import Pool
from pathlib import Path
import ijson
sys.path.insert(0, "/srv/fda-products-kg/repo/pipeline")
import fda_iri  # noqa: E402

DUP = set()
FIELDS = {"safetyreportid", "safetyreportversion", "transmissiondate", "receivedate"}


def scan(zpath):
    rows, k = [], -1
    with zipfile.ZipFile(zpath) as zf:
        for name in sorted(zf.namelist()):
            with zf.open(name) as fh:
                cur = {}
                for prefix, event, value in ijson.parse(fh):
                    if prefix == "results.item" and event == "start_map":
                        k += 1; cur = {}
                    elif prefix.startswith("results.item.") and prefix[13:] in FIELDS and event in ("string", "number"):
                        cur[prefix[13:]] = str(value)
                    elif prefix == "results.item" and event == "end_map":
                        try:
                            hit = "safetyreportid" in cur and fda_iri.drug_event_report(cur["safetyreportid"]) in DUP
                        except ValueError:
                            hit = False
                        if hit:
                            rows.append((cur["safetyreportid"], k, cur.get("safetyreportversion", ""),
                                         cur.get("transmissiondate", ""), cur.get("receivedate", "")))
    return zpath.name, rows


def load(path):
    DUP.update(l.strip().strip("<>") for l in open(path) if l.strip())


def main(snap, dups, out, workers=4):
    load(dups)
    zips = sorted(Path(snap).glob("*.json.zip"))
    occ = collections.defaultdict(list)
    with Pool(workers, initializer=load, initargs=(dups,)) as pool:
        for i, (zname, rows) in enumerate(pool.imap(scan, zips), 1):
            for rid, k, ver, tdate, rdate in rows:
                occ[rid].append((i, zname, k, ver, tdate, rdate))
            if i % 100 == 0 or i == len(zips):
                print(f"{i}/{len(zips)} partitions", file=sys.stderr, flush=True)
    n_ids = n_rows = 0
    with open(out, "w") as fh:
        for rid, lst in occ.items():
            if len(lst) < 2:
                continue
            n_ids += 1
            def key(t):
                v = int(t[3]) if t[3].isdigit() else -1
                return (v, t[4], t[0], t[2])
            win = max(lst, key=key)
            for j, t in enumerate(lst, 1):
                n_rows += 1
                fh.write("\t".join([fda_iri.drug_event_report(rid), str(j), t[1], str(t[2]), t[3], t[4], t[5],
                                    "1" if t is win else "0"]) + "\n")
    print(f"{len(DUP)} listed, {len(occ)} found, {n_ids} with more than one occurrence, {n_rows} occurrences", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]) if len(sys.argv) > 4 else 4)
