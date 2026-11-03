#!/usr/bin/env python3
"""
l1_meddra.py -- MedDRA MedAscii release -> fda-drug-event-kg hierarchy file (LICENSED, VM-only).

MedDRA is licensed to Hofstra University by the MSSO for internal use. The file this script
writes carries term names and must never leave the build VM (no git, no lakeFS, no OneDrive,
no Project docs) until the MSSO gives a written answer on publication. The public graphs keep
only what FDA itself publishes (openFDA strips nothing but we strip the PT text with --publish).

Input: raw/licensed/meddra/<version>/MedAscii/*.asc, '$'-delimited, one row per line, fields in
the order given by dist_file_format_<version>_English.pdf (section 3). Every non-empty field is
kept; the legacy code columns (WHO-ART, HARTS, COSTART, ICD-9, ICD-9-CM, ICD-10, J-ART) have
been empty since MedDRA 15.0 and are written only if present.

Records (all in fda-drug-event-kg):
  meddra-soc/<code>                  ex:MeddraSoc       meddraCode, soc_abbrev, intlOrder; hasHlgt
  meddra-hlgt/<code>                 ex:MeddraHlgt      meddraCode; hasSoc, hasHlt
  meddra-hlt/<code>                  ex:MeddraHlt       meddraCode; hasHlgt, hasPt
  meddra-pt/<code>                   ex:MeddraPt        meddraCode; primarySoc, hasHlt, hasLlt
  meddra-llt/<code>                  ex:MeddraLlt       meddraCode, lltCurrency; hasPt
  meddra-pt/<pt>/path/<soc>          ex:MeddraHierarchyPath  one mdhier row: hasPt, hasHlt, hasHlgt,
                                                        hasSoc, primarySocFlag
  meddra-smq/<code>                  ex:MeddraSmq       meddraCode, smqLevel, description, smqSource,
                                                        smqNote, meddraVersion, status, smqAlgorithm
  meddra-smq/<smq>/member/<term>     ex:MeddraSmqMember term (PT, LLT or child SMQ IRI), termLevel,
                                                        termScope, termCategory, termWeight, termStatus,
                                                        termAdditionVersion, termLastModifiedVersion
  <term>/history/<n>                 ex:MeddraHistoryEntry  termName, termAdditionVersion, termType,
                                                        lltCurrency, action (A/U/D)
rdfs:label is the term name (licensed text). Codes are 8-digit integers kept as strings.

Usage: python3 l1_meddra.py <release_dir> <out.ttl> <retrieved_at YYYY-MM-DD>
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402

E = "fda-drug-event-kg"
SRC = "https://www.meddra.org/software-packages"      # subscriber download, login required
LEGACY = ["whoartCode", "hartsCode", "costartSym", "icd9Code", "icd9cmCode", "icd10Code"]

LAYOUT = {   # file -> field names in file order (section 3 of the format document)
    "soc": ["soc_code", "soc_name", "soc_abbrev"] + LEGACY + ["jartCode"],
    "hlgt": ["hlgt_code", "hlgt_name"] + LEGACY + ["jartCode"],
    "hlt": ["hlt_code", "hlt_name"] + LEGACY + ["jartCode"],
    "pt": ["pt_code", "pt_name", "null_field", "pt_soc_code"] + LEGACY + ["jartCode"],
    "llt": ["llt_code", "llt_name", "pt_code"] + LEGACY[:5] + ["icd10Code", "llt_currency", "jartCode"],
    "soc_hlgt": ["soc_code", "hlgt_code"],
    "hlgt_hlt": ["hlgt_code", "hlt_code"],
    "hlt_pt": ["hlt_code", "pt_code"],
    "mdhier": ["pt_code", "hlt_code", "hlgt_code", "soc_code", "pt_name", "hlt_name", "hlgt_name",
               "soc_name", "soc_abbrev", "null_field", "pt_soc_code", "primary_soc_fg"],
    "intl_ord": ["intl_ord_code", "soc_code"],
    "smq_list": ["smq_code", "smq_name", "smq_level", "smq_description", "smq_source", "smq_note",
                 "meddra_version", "status", "smq_algorithm"],
    "smq_content": ["smq_code", "term_code", "term_level", "term_scope", "term_category",
                    "term_weight", "term_status", "term_addition_version", "term_last_modified_version"],
    "meddra_history_english": ["term_code", "term_name", "term_addition_version", "term_type",
                               "llt_currency", "action"],
    "meddra_release": ["version", "language"],
}
INTS = {"smq_level", "term_level", "term_scope", "term_weight", "intl_ord_code"}


def read(release, name):
    p = Path(release) / "MedAscii" / f"{name}.asc"
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    cols = LAYOUT[name]
    for line in text.splitlines():
        if not line.strip():
            continue
        f = line.split("$")
        if len(f) < len(cols):
            f += [""] * (len(cols) - len(f))
        yield dict(zip(cols, f))


def soc_iri(c): return fda_iri._inst(E, "meddra-soc", c)
def hlgt_iri(c): return fda_iri._inst(E, "meddra-hlgt", c)
def hlt_iri(c): return fda_iri._inst(E, "meddra-hlt", c)
def pt_iri(c): return fda_iri._inst(E, "meddra-pt", c)
def llt_iri(c): return fda_iri._inst(E, "meddra-llt", c)
def smq_iri(c): return fda_iri._inst(E, "meddra-smq", c)


def val(col, v):
    v = v.strip()
    if v == "":
        return None
    return common.int_lit(v) if col in INTS else common.lit(v)


def convert(release, out, retrieved_at):
    release = Path(release)
    rel = next(read(release, "meddra_release"))
    version = rel["version"].strip()
    dataset = f"meddra/{version}/{rel['language'].strip()}"
    fh = open(out, "w", encoding="utf-8", newline="\n", buffering=1 << 20)
    fh.write(common.prefixes({"ex": fda_iri.ns(E)}) + "\n")
    T = [0]
    n = defaultdict(int)

    def block(iri, pairs, key):
        pairs = list(pairs) + common.provenance(dataset, key, source_url=SRC, retrieved_at=retrieved_at)
        T[0] += common.write_block(fh, f"<{iri}>", pairs)

    def extras(row, skip):
        return [(f"ex:{k}", val(k, v)) for k, v in row.items() if k not in skip and v.strip()]

    # relation tables first (so the term blocks carry their links)
    soc_hlgt = defaultdict(list); hlgt_soc = defaultdict(list)
    for r in read(release, "soc_hlgt"):
        soc_hlgt[r["soc_code"]].append(r["hlgt_code"]); hlgt_soc[r["hlgt_code"]].append(r["soc_code"])
    hlgt_hlt = defaultdict(list); hlt_hlgt = defaultdict(list)
    for r in read(release, "hlgt_hlt"):
        hlgt_hlt[r["hlgt_code"]].append(r["hlt_code"]); hlt_hlgt[r["hlt_code"]].append(r["hlgt_code"])
    hlt_pt = defaultdict(list); pt_hlt = defaultdict(list)
    for r in read(release, "hlt_pt"):
        hlt_pt[r["hlt_code"]].append(r["pt_code"]); pt_hlt[r["pt_code"]].append(r["hlt_code"])
    pt_llt = defaultdict(list)
    llts = list(read(release, "llt"))
    for r in llts:
        if r["pt_code"].strip():
            pt_llt[r["pt_code"]].append(r["llt_code"])
    intl = {r["soc_code"]: r["intl_ord_code"] for r in read(release, "intl_ord")}
    history = defaultdict(list)
    for r in read(release, "meddra_history_english"):
        history[r["term_code"]].append(r)
    term_iri = {}   # code -> iri, for SMQ members and history
    hist_done = set()

    def hist(code, iri, ttype):
        # a code can name both a PT and its identical LLT, so history rows go to the node of their term_type
        hist_done.add((code, ttype))
        for i, r in enumerate([h for h in history.get(code, []) if h["term_type"].strip() == ttype], 1):
            pairs = [("a", "ex:MeddraHistoryEntry"), ("ex:term", f"<{iri}>"),
                     ("ex:termName", common.lit(r["term_name"])),
                     ("ex:termAdditionVersion", common.lit(r["term_addition_version"])),
                     ("ex:termType", common.lit(r["term_type"])),
                     ("ex:lltCurrency", val("llt_currency", r["llt_currency"])),
                     ("ex:action", common.lit(r["action"])),
                     ("rdfs:label", common.lit(f"{r['term_type']} {code} {r['action']} v{r['term_addition_version']}"))]
            block(f"{iri}/history/{i}", pairs, f"{code}/history/{i}")
            n["history"] += 1

    for r in read(release, "soc"):
        c = r["soc_code"]; iri = soc_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraSoc"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["soc_name"])),
                 ("ex:socAbbrev", common.lit(r["soc_abbrev"]))]
        if c in intl:
            pairs.append(("ex:intlOrder", common.int_lit(intl[c])))
        pairs += extras(r, {"soc_code", "soc_name", "soc_abbrev"})
        pairs += [("ex:hasHlgt", f"<{hlgt_iri(x)}>") for x in soc_hlgt.get(c, [])]
        block(iri, pairs, c); n["soc"] += 1; hist(c, iri, "SOC")
    for r in read(release, "hlgt"):
        c = r["hlgt_code"]; iri = hlgt_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraHlgt"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["hlgt_name"]))]
        pairs += extras(r, {"hlgt_code", "hlgt_name"})
        pairs += [("ex:hasSoc", f"<{soc_iri(x)}>") for x in hlgt_soc.get(c, [])]
        pairs += [("ex:hasHlt", f"<{hlt_iri(x)}>") for x in hlgt_hlt.get(c, [])]
        block(iri, pairs, c); n["hlgt"] += 1; hist(c, iri, "HLGT")
    for r in read(release, "hlt"):
        c = r["hlt_code"]; iri = hlt_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraHlt"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["hlt_name"]))]
        pairs += extras(r, {"hlt_code", "hlt_name"})
        pairs += [("ex:hasHlgt", f"<{hlgt_iri(x)}>") for x in hlt_hlgt.get(c, [])]
        pairs += [("ex:hasPt", f"<{pt_iri(x)}>") for x in hlt_pt.get(c, [])]
        block(iri, pairs, c); n["hlt"] += 1; hist(c, iri, "HLT")
    for r in read(release, "pt"):
        c = r["pt_code"]; iri = pt_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraPt"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["pt_name"]))]
        if r["pt_soc_code"].strip():
            pairs.append(("ex:primarySoc", f"<{soc_iri(r['pt_soc_code'].strip())}>"))
        pairs += extras(r, {"pt_code", "pt_name", "null_field", "pt_soc_code"})
        pairs += [("ex:hasHlt", f"<{hlt_iri(x)}>") for x in pt_hlt.get(c, [])]
        pairs += [("ex:hasLlt", f"<{llt_iri(x)}>") for x in pt_llt.get(c, [])]
        block(iri, pairs, c); n["pt"] += 1; hist(c, iri, "PT")
    for r in llts:
        c = r["llt_code"]; iri = llt_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraLlt"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["llt_name"])),
                 ("ex:lltCurrency", val("llt_currency", r["llt_currency"]))]
        if r["pt_code"].strip():
            pairs.append(("ex:hasPt", f"<{pt_iri(r['pt_code'].strip())}>"))
        pairs += extras(r, {"llt_code", "llt_name", "pt_code", "llt_currency"})
        block(iri, pairs, c); n["llt"] += 1; hist(c, iri, "LLT")
    for r in read(release, "mdhier"):
        pt, soc = r["pt_code"], r["soc_code"]
        iri = f"{pt_iri(pt)}/path/{soc}"
        pairs = [("a", "ex:MeddraHierarchyPath"), ("ex:hasPt", f"<{pt_iri(pt)}>"), ("ex:hasHlt", f"<{hlt_iri(r['hlt_code'])}>"),
                 ("ex:hasHlgt", f"<{hlgt_iri(r['hlgt_code'])}>"), ("ex:hasSoc", f"<{soc_iri(soc)}>"),
                 ("ex:primarySocFlag", common.lit(r["primary_soc_fg"])),
                 ("rdfs:label", common.lit(f"{r['pt_name']} > {r['hlt_name']} > {r['hlgt_name']} > {r['soc_name']}"))]
        block(iri, pairs, f"{pt}/{soc}"); n["paths"] += 1
    smq_members = defaultdict(list)
    for r in read(release, "smq_content"):
        smq_members[r["smq_code"]].append(r)
    for r in read(release, "smq_list"):
        c = r["smq_code"]; iri = smq_iri(c); term_iri[c] = iri
        pairs = [("a", "ex:MeddraSmq"), ("ex:meddraCode", common.lit(c)), ("rdfs:label", common.lit(r["smq_name"])),
                 ("ex:smqLevel", val("smq_level", r["smq_level"])), ("ex:description", common.lit(r["smq_description"])),
                 ("ex:smqSource", common.lit(r["smq_source"])), ("ex:smqNote", common.lit(r["smq_note"])),
                 ("ex:meddraVersion", common.lit(r["meddra_version"])), ("ex:status", common.lit(r["status"])),
                 ("ex:smqAlgorithm", common.lit(r["smq_algorithm"]))]
        pairs += [("ex:hasMember", f"<{iri}/member/{m['term_code']}>") for m in smq_members.get(c, [])]
        block(iri, pairs, c); n["smq"] += 1
    unresolved = 0
    for c, members in smq_members.items():
        for m in members:
            tc = m["term_code"]
            lvl = m["term_level"].strip()
            t = {"4": pt_iri(tc), "5": llt_iri(tc), "0": smq_iri(tc)}.get(lvl)
            if t is None or (lvl != "0" and tc not in term_iri):
                unresolved += 1
                t = t or term_iri.get(tc)
            pairs = [("a", "ex:MeddraSmqMember"), ("ex:smq", f"<{smq_iri(c)}>"), ("ex:term", f"<{t}>" if t else None),
                     ("ex:termCode", common.lit(tc)), ("ex:termLevel", val("term_level", m["term_level"])),
                     ("ex:termScope", val("term_scope", m["term_scope"])), ("ex:termCategory", common.lit(m["term_category"])),
                     ("ex:termWeight", val("term_weight", m["term_weight"])), ("ex:termStatus", common.lit(m["term_status"])),
                     ("ex:termAdditionVersion", common.lit(m["term_addition_version"])),
                     ("ex:termLastModifiedVersion", common.lit(m["term_last_modified_version"])),
                     ("rdfs:label", common.lit(f"SMQ {c} member {tc} (level {lvl}, scope {m['term_scope'].strip()})"))]
            block(f"{smq_iri(c)}/member/{tc}", pairs, f"{c}/{tc}"); n["smq_members"] += 1
    # history of codes that no longer have a term row (deleted or demoted terms): same IRI scheme, no term node
    IRIS = {"SOC": soc_iri, "HLGT": hlgt_iri, "HLT": hlt_iri, "PT": pt_iri, "LLT": llt_iri}
    for code, rows_ in history.items():
        for ttype in sorted({r["term_type"].strip() for r in rows_}):
            if (code, ttype) not in hist_done and ttype in IRIS:
                hist(code, IRIS[ttype](code), ttype); n["history_orphan_codes"] += 1
    fh.close()
    print(f"meddra {version} -> {Path(out).name}: " + ", ".join(f"{k} {v}" for k, v in n.items()) +
          f", {T[0]} triples, {unresolved} SMQ member codes not in the term files")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    convert(sys.argv[1], sys.argv[2], sys.argv[3])
