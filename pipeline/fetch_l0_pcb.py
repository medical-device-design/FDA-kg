#!/usr/bin/env python3
"""
fetch_l0_pcb.py -- L0 for the FDA Product Code Builder API (OII): the import product code
taxonomy (industries, classes, subclasses, process indicator codes, product groups/products and
the full product code list per industry), as a dated JSON snapshot.

Credentials: OII_USER, OII_KEY from the env file in $OII_ENV (default ~/.oii.env); read into the
request headers only, never printed or logged.

API: https://www.accessdata.fda.gov/rest/pcbapi/v1/ (OpenAPI at
https://www.accessdata.fda.gov/scripts/ora/pcb/apidocs/src/main/pcb.json). All reads are GET with
Authorization-User / Authorization-Key headers and a signature= cache-buster. Responses:
{MESSAGE, RESULTCOUNT, APIRETURNCODE, RESULT: {COLUMNS: [...], DATA: [[...], ...]}}.

Output: raw/fda-compliance-kg/fda-pcb/<date>/<name>.json for the five global lists and
by_industry/<endpoint>/<industryid>.json for the per-industry lists; MANIFEST.json, SOURCE_URL,
SHA256SUMS.

Usage: python3 fetch_l0_pcb.py <raw_root>
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://www.accessdata.fda.gov/rest/pcbapi/v1/"
DOCS = "https://www.accessdata.fda.gov/scripts/ora/pcb/apidocs/"
GLOBAL = ["industry", "class", "subclass", "pic", "product"]
PER_INDUSTRY = ["industryclass", "industrysubclass", "industrypic", "industryproduct", "productcodeindustry"]
PAUSE = 0.5


def load_env(path):
    env = {}
    for line in Path(path).read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    if not env.get("OII_USER") or not env.get("OII_KEY"):
        raise SystemExit(f"{path}: OII_USER and OII_KEY are required")
    return env


def get(path, env):
    url = f"{BASE}{path}?signature={int(time.time() * 1000)}"
    req = urllib.request.Request(url, headers={"Authorization-User": env["OII_USER"], "Authorization-Key": env["OII_KEY"],
                                               "User-Agent": "Mozilla/5.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:      # noqa: BLE001
            msg = str(e)[:120]
            if attempt == 4:
                raise SystemExit(f"{path}: request failed after 5 attempts: {msg}")
            print(f"  retry {attempt + 1} after error: {msg}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))
    msg = str(data.get("MESSAGE", "")).lower()
    if msg.startswith("no result"):          # empty list for this industry: keep the empty response
        return data
    if not msg.startswith("success"):        # success is APIRETURNCODE 400 "success", as on the Data Dashboard
        raise SystemExit(f"{path}: {data.get('APIRETURNCODE')} {data.get('MESSAGE')}")
    return data


def rows(data):
    res = data.get("RESULT") or {}
    cols = res.get("COLUMNS") or []
    return [dict(zip(cols, r)) for r in (res.get("DATA") or [])]


def main(raw_root):
    env = load_env(os.environ.get("OII_ENV", os.path.expanduser("~/.oii.env")))
    stamp = date.today().isoformat()
    dest = Path(raw_root) / "fda-compliance-kg" / "fda-pcb" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"retrieved": stamp, "api": BASE, "docs": DOCS, "lists": {}, "by_industry": {}}
    industries = []
    for name in GLOBAL:
        out = dest / f"{name}.json"
        if not out.exists():
            out.write_text(json.dumps(get(name, env), ensure_ascii=False), encoding="utf-8")
            time.sleep(PAUSE)
        data = json.loads(out.read_text(encoding="utf-8"))
        n = len(rows(data))
        manifest["lists"][name] = {"rows": n, "columns": (data.get("RESULT") or {}).get("COLUMNS")}
        print(f"{name}: {n} rows", flush=True)
        if name == "industry":
            industries = rows(data)
    id_col = next((c for c in ((manifest["lists"]["industry"]["columns"]) or []) if "ID" in c.upper()), None)
    if not id_col:
        raise SystemExit(f"industry columns: {manifest['lists']['industry']['columns']}")
    for ep in PER_INDUSTRY:
        d = dest / "by_industry" / ep
        d.mkdir(parents=True, exist_ok=True)
        total = 0
        for ind in industries:
            iid = ind[id_col]
            out = d / f"{iid}.json"
            if not out.exists():
                out.write_text(json.dumps(get(f"{ep}/{iid}", env), ensure_ascii=False), encoding="utf-8")
                time.sleep(PAUSE)
            total += len(rows(json.loads(out.read_text(encoding="utf-8"))))
        manifest["by_industry"][ep] = {"industries": len(industries), "rows": total}
        print(f"{ep}: {total} rows over {len(industries)} industries", flush=True)
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (dest / "SOURCE_URL").write_text(DOCS + "\n" + BASE + "{" + ",".join(GLOBAL + [e + "/{industryid}" for e in PER_INDUSTRY]) + "}\n")
    with open(dest / "SHA256SUMS", "w") as fh:
        for p in sorted(dest.rglob("*.json")):
            fh.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(dest)}\n")
    print("DONE fetch_l0_pcb")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
