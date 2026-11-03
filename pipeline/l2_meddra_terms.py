#!/usr/bin/env python3
"""
l2_meddra_terms.py -- map the MedDRA term text in FDA adverse event sources to MedDRA codes
(links into the fda-drug-event-kg hierarchy built by l1_meddra.py).

The public L1 files are built with --publish, which drops the MedDRA preferred-term text. This
pass reads the term text from the raw snapshots again and writes only links to MedDRA code
IRIs, one small file per source, so the text never has to be in the graph for the codes to be:

  faers    raw openFDA drug/event partitions   patient.reaction[i].reactionmeddrapt
           -> <report/<id>/patient/reaction/<i>>  ex:hasMeddraPt <meddra-pt/CODE> ;
              ex:hasMeddraLlt <meddra-llt/CODE> (when the text matched an LLT, not a PT) ;
              ex:meddraMatch "PT" | "LLT" | "PT-loose" | "LLT-loose" | "PT-history" | "LLT-history"
  vaers    raw VAERS zips, *VAERSSYMPTOMS.csv  SYMPTOM1..5
           -> <vaers-report/<id>/symptoms/<n>>  ex:symptom<k>Pt / ex:symptom<k>Llt / ex:symptom<k>Match
  caers    raw openFDA food/event               reactions[]  -> <caers-report/<n>>   ex:hasMeddraPt ...
  cosmetic raw openFDA cosmetic/event           reactions[]  -> <cosmetic-event/<n>> ex:hasMeddraPt ...

Matching, against one MedDRA release (MedAscii pt.asc and llt.asc): casefold and collapse
whitespace, then (1) PT name, (2) LLT name (current or not; the LLT's PT is linked too),
(3) the same two with punctuation removed ("loose"), (4) a name the PT or LLT carried in an earlier
release, from the history file ("history", for renamed terms). Anything else is counted and listed,
never guessed. The reports' own MedDRA version fields are tallied so the match rate can be read
against them. Nothing in the raw files is modified; licensed text is written only to the
dictionary and unmapped lists under work/, which stay on the VM.

Usage:
  python3 l2_meddra_terms.py <release_dir> faers    <snapshot_dir> <out.ttl.gz> [--workers N] [--limit N]
  python3 l2_meddra_terms.py <release_dir> vaers    <snapshot_dir> <out.ttl.gz>
  python3 l2_meddra_terms.py <release_dir> caers    <snapshot_dir> <out.ttl.gz>
  python3 l2_meddra_terms.py <release_dir> cosmetic <snapshot_dir> <out.ttl.gz>
Reports (stderr and <out>.report.txt): distinct strings, matched by level, unmapped with counts.
"""
import csv
import gzip
import io
import re
import sys
import zipfile
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import l1_meddra   # noqa: E402

E = "fda-drug-event-kg"
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^a-z0-9]+")


def norm(s):
    return _WS.sub(" ", str(s)).strip().casefold()


def loose(s):
    return _PUNCT.sub("", norm(s))


class Dictionary:
    def __init__(self, release):
        self.pt, self.llt, self.pt_loose, self.llt_loose = {}, {}, {}, {}
        for r in l1_meddra.read(release, "pt"):
            self.pt.setdefault(norm(r["pt_name"]), r["pt_code"])
            self.pt_loose.setdefault(loose(r["pt_name"]), r["pt_code"])
        for r in l1_meddra.read(release, "llt"):
            if not r["pt_code"].strip():
                continue
            self.llt.setdefault(norm(r["llt_name"]), (r["llt_code"], r["pt_code"].strip()))
            self.llt_loose.setdefault(loose(r["llt_name"]), (r["llt_code"], r["pt_code"].strip()))
        # names a term carried in an earlier release (renamed terms): meddra_history_english.asc
        llt_pt = {c: pt for (c, pt) in self.llt.values()}
        pt_codes = set(self.pt.values())
        self.pt_hist, self.llt_hist = {}, {}
        for r in l1_meddra.read(release, "meddra_history_english"):
            t, c, k = r["term_type"].strip(), r["term_code"].strip(), norm(r["term_name"])
            if t == "PT" and c in pt_codes:
                self.pt_hist.setdefault(k, c)
            elif t == "LLT" and c in llt_pt:
                self.llt_hist.setdefault(k, (c, llt_pt[c]))
        self.cache = {}

    def lookup(self, text):
        """-> (pt_code, llt_code or None, level) or None"""
        k = norm(text)
        if k in self.cache:
            return self.cache[k]
        r = None
        if k in self.pt:
            r = (self.pt[k], None, "PT")
        elif k in self.llt:
            r = (self.llt[k][1], self.llt[k][0], "LLT")
        else:
            kl = loose(text)
            if kl and kl in self.pt_loose:
                r = (self.pt_loose[kl], None, "PT-loose")
            elif kl and kl in self.llt_loose:
                r = (self.llt_loose[kl][1], self.llt_loose[kl][0], "LLT-loose")
            elif k in self.pt_hist:
                r = (self.pt_hist[k], None, "PT-history")
            elif k in self.llt_hist:
                r = (self.llt_hist[k][1], self.llt_hist[k][0], "LLT-history")
        self.cache[k] = r
        return r


def pairs_for(hit, pred_pt="ex:hasMeddraPt", pred_llt="ex:hasMeddraLlt", pred_match="ex:meddraMatch"):
    pt, llt, level = hit
    out = [(pred_pt, f"<{l1_meddra.pt_iri(pt)}>")]
    if llt:
        out.append((pred_llt, f"<{l1_meddra.llt_iri(llt)}>"))
    out.append((pred_match, common.lit(level)))
    return out


class Stats:
    def __init__(self):
        self.strings = Counter()      # normalized text -> occurrences
        self.level = Counter()        # match level -> occurrences
        self.unmapped = Counter()     # original text -> occurrences
        self.versions = Counter()
        self.nodes = 0
        self.triples = 0

    def add(self, other):
        for k in ("strings", "level", "unmapped", "versions"):
            getattr(self, k).update(getattr(other, k))
        self.nodes += other.nodes
        self.triples += other.triples

    def report(self, out):
        occ = sum(self.strings.values())
        lines = [f"occurrences: {occ}; distinct strings: {len(self.strings)}; nodes linked: {self.nodes}; triples: {self.triples}"]
        for lvl, n in sorted(self.level.items()):
            lines.append(f"  {lvl:>10}: {n} occurrences")
        um = sum(self.unmapped.values())
        lines.append(f"  unmapped: {um} occurrences, {len(self.unmapped)} distinct ({100.0 * um / max(occ, 1):.2f}% of occurrences)")
        lines.append("MedDRA versions stated in the reports (top 15): " +
                     ", ".join(f"{v}:{n}" for v, n in self.versions.most_common(15)))
        lines.append("unmapped strings (top 60):")
        for s, n in self.unmapped.most_common(60):
            lines.append(f"  {n:>8}  {s}")
        text = "\n".join(lines)
        print(text, file=sys.stderr)
        Path(str(out) + ".report.txt").write_text(text + "\n", encoding="utf-8")
        Path(str(out) + ".unmapped.tsv").write_text(
            "".join(f"{n}\t{s}\n" for s, n in self.unmapped.most_common()), encoding="utf-8")


_D = None     # per-process dictionary


def _init(release):
    global _D
    _D = Dictionary(release)


def _emit(buf, iri, pairs, st):
    st.triples += common.write_block(buf, f"<{iri}>", pairs)
    st.nodes += 1


# ---- FAERS ------------------------------------------------------------------------------
def _faers_zip(args):
    zpath, limit = args
    import ijson
    buf, st = io.StringIO(), Stats()
    n = 0
    with zipfile.ZipFile(zpath) as zf:
        for name in sorted(zf.namelist()):
            with zf.open(name) as fh:
                rid, idx, terms, versions = None, -1, [], []
                for prefix, event, value in ijson.parse(fh):
                    if prefix == "results.item":
                        if event == "start_map":
                            rid, idx, terms, versions = None, -1, [], []
                        elif event == "end_map":
                            if rid is not None:
                                riri = fda_iri.drug_event_report(rid)
                                for i, t in terms:
                                    st.strings[norm(t)] += 1
                                    hit = _D.lookup(t)
                                    if hit:
                                        st.level[hit[2]] += 1
                                        _emit(buf, f"{riri}/patient/reaction/{i}", pairs_for(hit), st)
                                    else:
                                        st.unmapped[str(t).strip()] += 1
                                for v in versions:
                                    st.versions[str(v)] += 1
                                n += 1
                                if limit and n >= limit:
                                    return buf.getvalue(), st
                    elif prefix == "results.item.safetyreportid":
                        rid = value
                    elif prefix == "results.item.patient.reaction.item":
                        if event == "start_map":
                            idx += 1
                    elif prefix == "results.item.patient.reaction.item.reactionmeddrapt":
                        terms.append((idx, value))
                    elif prefix == "results.item.patient.reaction.item.reactionmeddraversionpt":
                        versions.append(value)
    return buf.getvalue(), st


def faers(release, snap, out, workers=4, limit=None):
    zips = sorted(Path(snap).glob("*.json.zip"))
    st = Stats()
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
        with Pool(workers, initializer=_init, initargs=(release,)) as pool:
            for k, (text, s) in enumerate(pool.imap(_faers_zip, [(z, limit) for z in zips]), 1):
                fh.write(text)
                st.add(s)
                if k % 50 == 0 or k == len(zips):
                    print(f"  {k}/{len(zips)} partitions, {st.nodes} reactions linked", file=sys.stderr, flush=True)
    return st


# ---- VAERS ------------------------------------------------------------------------------
def vaers(release, snap, out):
    import l1_vaers
    d = Dictionary(release)
    st = Stats()
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
        for zpath in sorted(Path(snap).glob("*.zip")):
            with zipfile.ZipFile(zpath) as zf:
                for name in sorted(zf.namelist()):
                    if not re.search(r"VAERSSYMPTOMS\.csv$", name, re.I):
                        continue
                    rdr = csv.DictReader(l1_vaers.open_member(zf, name))
                    for i, row in enumerate(rdr):
                        row = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in row.items() if k}
                        vid = row.get("VAERS_ID")
                        if not vid:
                            continue
                        n = row.get("ORDER") or str(i)
                        ciri = f"{l1_vaers.report_iri(vid)}/symptoms/{fda_iri.slug(n)}"
                        pairs = []
                        for k in range(1, 6):
                            t = row.get(f"SYMPTOM{k}")
                            if not t:
                                continue
                            v = row.get(f"SYMPTOMVERSION{k}")
                            if v:
                                st.versions[v] += 1
                            st.strings[norm(t)] += 1
                            hit = d.lookup(t)
                            if hit:
                                st.level[hit[2]] += 1
                                pairs += pairs_for(hit, f"ex:symptom{k}Pt", f"ex:symptom{k}Llt", f"ex:symptom{k}Match")
                            else:
                                st.unmapped[t] += 1
                        if pairs:
                            _emit(fh, ciri, pairs, st)
    return st


# ---- CAERS / cosmetic (openFDA, reactions[] of strings) ----------------------------------
def openfda_reactions(release, snap, out, iri_fn):
    import ijson
    d = Dictionary(release)
    st = Stats()
    with gzip.open(out, "wt", encoding="utf-8", newline="\n", compresslevel=6) as fh:
        fh.write(common.prefixes({"ex": fda_iri.ns("fda-food-cosmetic-kg")}) + "\n")
        for z in sorted(Path(snap).glob("*.json.zip")):
            with zipfile.ZipFile(z) as zf:
                for name in sorted(zf.namelist()):
                    with zf.open(name) as fh_in:
                        for rec in ijson.items(fh_in, "results.item"):
                            rn = rec.get("report_number")
                            if not rn:
                                continue
                            pairs, seen = [], set()
                            for t in rec.get("reactions") or []:
                                st.strings[norm(t)] += 1
                                hit = d.lookup(t)
                                if hit:
                                    st.level[hit[2]] += 1
                                    if hit[0] in seen:
                                        continue
                                    seen.add(hit[0])
                                    pairs += pairs_for(hit)
                                else:
                                    st.unmapped[str(t).strip()] += 1
                            if pairs:
                                _emit(fh, iri_fn(rn), pairs, st)
    return st


def main(argv):
    release, mode, snap, out = argv[0], argv[1], argv[2], argv[3]
    opts = argv[4:]
    workers = int(opts[opts.index("--workers") + 1]) if "--workers" in opts else 4
    limit = int(opts[opts.index("--limit") + 1]) if "--limit" in opts else None
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    if mode == "faers":
        st = faers(release, snap, out, workers, limit)
    elif mode == "vaers":
        st = vaers(release, snap, out)
    elif mode == "caers":
        st = openfda_reactions(release, snap, out, fda_iri.caers_report)
    elif mode == "cosmetic":
        st = openfda_reactions(release, snap, out, fda_iri.cosmetic_event)
    else:
        raise SystemExit(__doc__)
    print(f"{mode} -> {Path(out).name}", file=sys.stderr)
    st.report(out)


if __name__ == "__main__":
    if len(sys.argv) < 5:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
