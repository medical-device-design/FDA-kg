#!/usr/bin/env python3
"""
fetch_l0_datadashboard.py -- L0 for the FDA Data Dashboard API (OII): inspections classifications,
inspection citations, compliance actions and import refusals, as dated JSON snapshots.

Credentials come from an env file (OII_USER, OII_KEY) whose path is in $OII_ENV (default
~/.oii.env). The key is read into the request headers only; it is never printed or logged.

API: POST https://api-datadashboard.fda.gov/v1/<endpoint>, JSON body with filters, sort,
sortorder, start, rows (max 5000), returntotalcount. Paging: start += resultcount until a short
page. To keep every page stable the pull is split into calendar-year windows on the dataset's date
field and sorted on that field. Output: raw/fda-compliance-kg/fda-datadashboard/<date>/<endpoint>/<year>.json
(the result rows of that window), MANIFEST.json with counts, SOURCE_URL, SHA256SUMS.

Usage: python3 fetch_l0_datadashboard.py <raw_root> [endpoint ...]
"""
import hashlib
import json
import os
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

BASE = "https://api-datadashboard.fda.gov/v1/"
DOCS = "https://datadashboard.fda.gov/oii/api/index.htm"
ENDPOINTS = {  # endpoint -> (date field, first year)
    "inspections_classifications": ("InspectionEndDate", 2008),
    "inspections_citations": ("InspectionEndDate", 2008),
    "compliance_actions": ("ActionTakenDate", 2008),
    "import_refusals": ("RefusalDate", 2002),
}
# every column the OpenAPI definition (ddapi.json) lists for each response row
COLUMNS = {
    "inspections_classifications": ["FEINumber", "LegalName", "AddressLine1", "AddressLine2", "City", "StateCode", "State",
                                    "ZipCode", "CountryCode", "CountryName", "InspectionID", "InspectionEndDate", "FiscalYear",
                                    "PostedCitations", "Classification", "ClassificationCode", "ProjectArea", "ProductType",
                                    "AdditionalDetails", "FMD145Date", "FirmProfile"],
    "inspections_citations": ["InspectionID", "FEINumber", "LegalName", "AddressLine1", "AddressLine2", "City", "StateCode",
                              "State", "ZipCode", "CountryCode", "CountryName", "InspectionEndDate", "ProgramArea", "CitationID",
                              "ActCFRNumber", "ShortDescription", "LongDescription", "FirmProfile"],
    "compliance_actions": ["FEINumber", "LegalName", "AddressLine1", "AddressLine2", "City", "StateCode", "State", "ZipCode",
                           "CountryCode", "CountryName", "Region", "ProductType", "Center", "ActionType", "ActionTakenDate",
                           "FiscalYear", "CaseInjunctionID", "FirmProfile"],
    "import_refusals": ["FEINumber", "FirmName", "AddressLine1", "AddressLine2", "City", "State", "ZipCode", "CountryCode",
                        "CountryName", "DistrictCode", "DistrictDescription", "IndustryCode", "IndustryCodeDescription",
                        "ProductCategory", "ProductCode", "ProductCodeDescription", "RefusalDate", "ShipmentID",
                        "FDASampleAnalysis", "PrivateLabAnalysis", "RefusalCharges", "FirmProfile"],
}
ROWS = 5000
PAUSE = 1.0


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


def post(endpoint, body, env):
    req = urllib.request.Request(BASE + endpoint, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json",
                                          "Authorization-User": env["OII_USER"],
                                          "Authorization-Key": env["OII_KEY"]})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:      # noqa: BLE001
            msg = str(e)[:120]
            if attempt == 4:
                raise SystemExit(f"{endpoint}: request failed after 5 attempts: {msg}")
            print(f"  retry {attempt + 1} after error: {msg}", file=sys.stderr)
            time.sleep(10 * (attempt + 1))


def pull_window(endpoint, field, year, env):
    rows, start, total = [], 1, None
    while True:
        body = {"start": start, "rows": ROWS, "sort": field, "sortorder": "asc", "columns": COLUMNS[endpoint],
                "filters": {f"{field}From": [f"{year}-01-01"], f"{field}To": [f"{year}-12-31"]}}
        if start == 1:
            body["returntotalcount"] = True
        data = post(endpoint, body, env)
        if str(data.get("message", "")).lower().startswith("no results"):      # 412: empty window
            break
        if not str(data.get("message", "")).lower().startswith("success"):
            raise SystemExit(f"{endpoint} {year}: {data.get('statuscode')} {data.get('message')} "
                             f"{ {k: v for k, v in data.items() if k.startswith(('invalid', 'missing', 'fieldnames'))} }")
        got = data.get("result") or []
        rows.extend(got)
        n = data.get("resultcount", len(got))
        if start == 1:
            total = data.get("totalrecordcount")
        if n < ROWS or not got:
            break
        start += n
        time.sleep(PAUSE)
    return rows, total


def main(raw_root, only):
    env = load_env(os.environ.get("OII_ENV", os.path.expanduser("~/.oii.env")))
    stamp = date.today().isoformat()
    dest = Path(raw_root) / "fda-compliance-kg" / "fda-datadashboard" / stamp
    dest.mkdir(parents=True, exist_ok=True)
    manifest = {"retrieved": stamp, "api": BASE, "docs": DOCS, "endpoints": {}}
    this_year = date.today().year
    for ep, (field, first) in ENDPOINTS.items():
        if only and ep not in only:
            continue
        d = dest / ep
        d.mkdir(exist_ok=True)
        counts = {}
        for year in range(first, this_year + 1):
            out = d / f"{year}.json"
            if out.exists():
                counts[year] = len(json.loads(out.read_text(encoding="utf-8")))
                continue
            rows, total = pull_window(ep, field, year, env)
            if total is not None and total != len(rows):
                raise SystemExit(f"{ep} {year}: server says {total} rows, got {len(rows)}")
            out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            counts[year] = len(rows)
            print(f"{ep} {year}: {len(rows)} rows", flush=True)
            time.sleep(PAUSE)
        manifest["endpoints"][ep] = {"date_field": field, "rows_by_year": counts, "total": sum(counts.values())}
        print(f"== {ep}: {sum(counts.values())} rows", flush=True)
    (dest / "MANIFEST.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    (dest / "SOURCE_URL").write_text(DOCS + "\n" + BASE + "{inspections_classifications,inspections_citations,compliance_actions,import_refusals}\n")
    with open(dest / "SHA256SUMS", "w") as fh:
        for p in sorted(dest.rglob("*.json")):
            fh.write(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(dest)}\n")
    print("DONE fetch_l0_datadashboard")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2:])
