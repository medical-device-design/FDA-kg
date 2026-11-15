#!/usr/bin/env python3
"""Run the FDA-kg query battery against the live per-graph FRINK endpoints (https://apps.okn.us/<graph>/sparql).
Usage: run_frink.py [shortname ...]. Sends one query at a time and retries HTTP 429.
Writes results_<shortnames>.md next to this script. ONLY=name1,name2 runs selected queries."""
import os, sys, time, json, csv, io, glob, urllib.request, urllib.parse, datetime
HERE = os.path.dirname(os.path.abspath(__file__)); Q = os.path.join(HERE, "queries")
if not os.path.isdir(Q): Q = os.path.join(HERE, "..", "queries")
ONLY = os.environ.get("ONLY", "").split(",") if os.environ.get("ONLY") else None
GRAPHS = sys.argv[1:] or ["fda-tobacco-kg", "fda-food-cosmetic-kg", "fda-substance-kg", "fda-compliance-kg", "fda-animal-health-kg"]
EXTRA = {"fda-compliance-kg": sorted(glob.glob(os.path.join(Q, "gaps", "i*.rq")))}
def run(ep, q, tries=6):
    for i in range(tries):
        st, rows, t = run1(ep, q)
        if "429" not in st: return st, rows, t
        time.sleep(20 * (i + 1))
    return st, rows, t
def run1(ep, q):
    data = urllib.parse.urlencode({"query": q}).encode()
    req = urllib.request.Request(ep, data=data, headers={"Accept": "text/csv"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r: body = r.read().decode("utf-8", "replace")
        rows = list(csv.reader(io.StringIO(body)))
        return "ok", rows, time.time() - t0
    except Exception as e:
        msg = getattr(e, "read", lambda: b"")()
        return "error: " + str(e) + " " + msg.decode("utf-8", "replace")[:300].replace("\n", " "), [], time.time() - t0
summary, body = [], []
for g in GRAPHS:
    ep = f"https://apps.okn.us/{g}/sparql"; ns = f"https://bmedesign.org/{g}/ns/"
    qs = [(os.path.join(Q, "common_counts.rq"), None), (os.path.join(Q, "common_provenance.rq"), ns)]
    qs += [(f, None) for f in sorted(glob.glob(os.path.join(Q, g, "*.rq")))] + [(f, None) for f in EXTRA.get(g, [])]
    for f, sub in qs:
        q = open(f).read()
        if sub: q = q.replace("GRAPH_NS", sub)
        name = g + "__" + os.path.basename(f)[:-3]
        if ONLY and name not in ONLY: continue
        st, rows, t = run(ep, q)
        n = max(len(rows) - 1, 0)
        summary.append(f"| {name} | {n} | {t:.1f} s | {st[:160]} |")
        body.append(f"\n## {name} ({n} rows, {t:.1f} s)\n```")
        body += [",".join(r)[:200] for r in rows[:26]]
        if n > 25: body.append(f"(first 25 of {n} rows)")
        body.append("```")
        print(name, n, st[:80], flush=True); time.sleep(3)
out = os.path.join(HERE, "results_" + "_".join(GRAPHS) + ".md")
with open(out, "w") as fh:
    fh.write(f"# FRINK per-graph endpoint results, {datetime.datetime.now():%B %d, %Y %H:%M}\n\n| query | rows | time | status |\n|---|---|---|---|\n")
    fh.write("\n".join(summary) + "\n" + "\n".join(body) + "\n")
print("DONE", out)
