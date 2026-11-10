#!/usr/bin/env python3
"""Raw-source checks for the gap queries (November 9, 2026). Reads raw zips and published Turtle only."""
import collections, csv, glob, io, re, sys, zipfile
from pathlib import Path
R = Path(sys.argv[1]); W = R / "work/gaps"
csv.field_size_limit(1 << 28)
print("\n## Raw-source checks\n")

# 1. VAERS vaccinations by manufacturer and type, straight from the VAX CSVs (each member read once)
seen, cnt, rows = set(), collections.Counter(), 0
for z in sorted(glob.glob(str(R / "raw/**/*VAERS*.zip"), recursive=True)):
    with zipfile.ZipFile(z) as zf:
        for name in sorted(zf.namelist()):
            if not re.search(r"VAERSVAX\.csv$", name, re.I) or name in seen:
                continue
            seen.add(name)
            raw = zf.read(name)
            try: text = raw.decode("utf-8")
            except UnicodeDecodeError: text = raw.decode("cp1252", errors="replace")
            for r in csv.DictReader(io.StringIO(text)):
                if not (r.get("VAERS_ID") or "").strip(): continue
                rows += 1
                m, t = (r.get("VAX_MANU") or "").strip(), (r.get("VAX_TYPE") or "").strip()
                if m and t: cnt[(m, t)] += 1
print(f"### 1. VAERS VAX rows in the raw CSVs: {rows:,} (graph VaersVaccination count should equal this)\n")
print("Top 15 manufacturer and type from raw rows (compare with q9):\n\n```")
for (m, t), n in cnt.most_common(15): print(f"{n:>9,}  {m}  {t}")
print("```")

# 2. Import alerts, old vs new file: product nodes that carry two product codes (the collision symptom)
def blocks(path):
    subj, lines = None, []
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith("<"):
                if subj: yield subj, lines
                subj, lines = ln.strip(), []
            elif ln.strip() == "":
                if subj: yield subj, lines
                subj, lines = None, []
            elif subj:
                lines.append(ln.strip())
    if subj: yield subj, lines
def two_codes(path):
    codes = collections.defaultdict(set)
    for s, ls in blocks(path):
        if "/product/" in s:
            for l in ls:
                if l.startswith("ex:productCode"): codes[s].add(l)
    return sum(1 for v in codes.values() if len(v) > 1), len(codes)
for f in ("import_alerts.ttl", "import_alerts_v2.ttl"):
    n, tot = two_codes(R / "out/fda-compliance-kg" / f)
    print(f"\n### 2. {f}: {n:,} of {tot:,} firm-product IRIs carry more than one product code")

# 3. x3 row 1 and x7 row 1, recounted from the Turtle files
def first_iri(qfile):
    p = W / "q" / qfile
    if not p.exists(): return None
    for ln in p.read_text().splitlines()[3:]:
        m = re.search(r"<(https://bmedesign\.org/fda-substance-kg/id/[^>]+)>", ln)
        if m: return m.group(1)
def scan(files, iri):
    subjects, classes = set(), collections.Counter()
    for f in files:
        for s, ls in blocks(f):
            if any(l.startswith("ex:hasSubstance") and f"<{iri}>" in l for l in ls):
                subjects.add(s)
                for l in ls:
                    if l.startswith("a "): classes[l[2:].rstrip(" ;.")] += 1
    return subjects, classes
iri = first_iri("x3_recall_to_substance.txt")
if iri:
    subs, cl = scan(sorted((R / "out/fda-compliance-kg").glob("*_enforcement.ttl")), iri)
    rec = sum(n for c, n in cl.items() if c.endswith("Recall"))
    print(f"\n### 3. x3 row 1 {iri}: {rec:,} Recall blocks in the enforcement files link to it (x3 drugRecalls should match)")
iri = first_iri("x7_food_ingredient_to_substance.txt")
if iri:
    subs, cl = scan(sorted((R / "out/fda-food-cosmetic-kg").glob("*.ttl")), iri)
    print(f"\n### 4. x7 row 1 {iri}: {len(cl)} classes in the food-cosmetic files link to it: {', '.join(sorted(cl))}")
