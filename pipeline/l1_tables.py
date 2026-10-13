#!/usr/bin/env python3
"""
l1_tables.py -- L1 converter for FDA's delimited bulk files and the warning-letter
index. One config per table; the row-to-node mapping is mapper.py as everywhere else.

Sources (snapshot dir = the dated L0 folder):
  drugsatfda   Drugs@FDA data files zip, 12 tab-delimited tables -> fda-drug-biologic-kg
  orangebook   EOBZIP.zip, three tilde-delimited tables            -> fda-drug-biologic-kg
  purplebook   monthly CSV change reports (one or many files)      -> fda-drug-biologic-kg
  warning-letters  fda.gov datatable JSON (list of dicts)          -> fda-compliance-kg

Every column is kept (lowerCamel of the header). Application numbers are normalized
through fda_iri.application() so Drugs@FDA, Orange Book, Purple Book, NDC, NSDE and
CRL rows all land on the same application IRI.

Usage:
  python3 l1_tables.py <source> <snapshot_dir> <out.ttl>
"""
import csv
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

D, C = "fda-drug-biologic-kg", "fda-compliance-kg"
csv.field_size_limit(1 << 28)


def clean(row):
    """Strip whitespace from keys and values; drop blank values. Keeps text verbatim
    otherwise (Drugs@FDA pads SubmissionType with spaces, e.g. 'SUPPL     ')."""
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        k = k.strip().lstrip("﻿")
        if isinstance(v, str):
            v = v.strip()
        if v not in (None, "", "Null"):
            out[k] = v
    return out


def app(no, typ=None):
    """Application IRI; when the type is unknown (ApplNo missing from
    Applications.txt) fall back to the untyped IRI instead of dropping the row."""
    try:
        return fda_iri.application(no, typ)
    except ValueError:
        return fda_iri.application_untyped(no)


def app_product(no, prod, typ=None):
    return app(no, typ) + "/product/" + fda_iri.slug(prod)


def submission(no, typ, stype, sno):
    return app(no, typ) + f"/submission/{fda_iri.slug(stype)}-{fda_iri.slug(sno)}"


_TAG = re.compile(r"<[^>]+>")


def untag(s):
    return _TAG.sub("", s or "").strip()


# ---------------------------------------------------------------------------
class Out:
    def __init__(self, path, graph, prefix, dates, stamp, dataset):
        self.fh = open(path, "w", encoding="utf-8", newline="\n", buffering=1 << 20)
        self.fh.write(common.prefixes({"ex": fda_iri.ns(graph)}) + "\n")
        self.m = mapper.Mapper(self.fh, class_prefix=prefix, date_fields=dates)
        self.stamp, self.dataset = stamp, dataset
        self.rows = self.skipped = 0
        self.skips = {}          # table -> [count, sample rows]

    def skip(self, table, row):
        self.skipped += 1
        c = self.skips.setdefault(table, [0, []])
        c[0] += 1
        if len(c[1]) < 2:
            c[1].append({k: row[k] for k in list(row)[:6]})

    def node(self, iri, row, cls, label, rec_id, links=(), source_url=None):
        extra = [("rdfs:label", common.lit(label))] + list(links)
        extra += common.provenance(self.dataset, rec_id, source_url=source_url,
                                   retrieved_at=self.stamp)
        self.m.map_obj(iri, row, cls=cls, extra=extra, top=True)
        self.rows += 1

    def close(self):
        self.fh.close()


def read_table(text, delim):
    return (clean(r) for r in csv.DictReader(io.StringIO(text), delimiter=delim))


def zip_tables(zpath, encoding="latin-1"):
    with zipfile.ZipFile(zpath) as zf:
        return {n: zf.read(n).decode(encoding) for n in zf.namelist()}


# ---------------------------------------------------------------------------
def convert_drugsatfda(snap, out_path, stamp):
    t = zip_tables(next(snap.glob("*.zip")))
    o = Out(out_path, D, "DfdaFile", {"SubmissionStatusDate", "ApplicationDocsDate"},
            stamp, "fda/drugsatfda-data-files")
    base = "https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files"
    # lookups first: small vocab nodes
    lookups = {
        "ActionTypes_Lookup.txt": ("ActionTypes_LookupID", "action-type", "ActionType", "ActionTypes_LookupDescription"),
        "ApplicationsDocsType_Lookup.txt": ("ApplicationDocsType_Lookup_ID", "doc-type", "ApplicationDocType", "ApplicationDocsType_Lookup_Description"),
        "MarketingStatus_Lookup.txt": ("MarketingStatusID", "marketing-status", "MarketingStatus", "MarketingStatusDescription"),
        "SubmissionClass_Lookup.txt": ("SubmissionClassCodeID", "submission-class", "SubmissionClass", "SubmissionClassCodeDescription"),
    }
    lk = {}
    for fname, (idcol, kind, cls, labcol) in lookups.items():
        lk[kind] = {}
        for r in read_table(t[fname], "\t"):
            iri = fda_iri._inst(D, kind, fda_iri.slug(r[idcol]))
            lk[kind][r[idcol]] = iri
            o.node(iri, r, cls, r.get(labcol, r[idcol]), f"{fname}:{r[idcol]}", source_url=base)
    appl_type = {}
    for r in read_table(t["Applications.txt"], "\t"):
        appl_type[r["ApplNo"]] = r.get("ApplType")
        try:
            iri = app(r["ApplNo"], r.get("ApplType"))
        except ValueError:
            o.skip("Applications.txt", r)
            continue
        o.node(iri, r, "DrugApplication", f'{r.get("ApplType", "")}{r["ApplNo"]} {r.get("SponsorName", "")}'.strip(),
               r["ApplNo"], source_url=base)
    for r in read_table(t["Products.txt"], "\t"):
        try:
            iri = app_product(r["ApplNo"], r["ProductNo"], appl_type.get(r["ApplNo"]))
        except (ValueError, KeyError):
            o.skip("Products.txt", r)
            continue
        o.node(iri, r, "DrugProduct", f'{r.get("DrugName", "")} {r.get("Strength", "")} ({r["ApplNo"]}/{r["ProductNo"]})'.strip(),
               f'{r["ApplNo"]}:{r["ProductNo"]}',
               links=[("ex:hasApplication", f"<{app(r['ApplNo'], appl_type.get(r['ApplNo']))}>")], source_url=base)
    for r in read_table(t["Submissions.txt"], "\t"):
        try:
            iri = submission(r["ApplNo"], appl_type.get(r["ApplNo"]), r["SubmissionType"], r["SubmissionNo"])
        except (ValueError, KeyError):
            o.skip("Submissions.txt", r)
            continue
        links = [("ex:hasApplication", f"<{app(r['ApplNo'], appl_type.get(r['ApplNo']))}>")]
        if r.get("SubmissionClassCodeID") in lk["submission-class"]:
            links.append(("ex:hasSubmissionClass", f"<{lk['submission-class'][r['SubmissionClassCodeID']]}>"))
        o.node(iri, r, "Submission", f'{r["ApplNo"]} {r["SubmissionType"].strip()} {r["SubmissionNo"]}',
               f'{r["ApplNo"]}:{r["SubmissionType"].strip()}:{r["SubmissionNo"]}', links=links, source_url=base)
    for r in read_table(t["ApplicationDocs.txt"], "\t"):
        try:
            sub = submission(r["ApplNo"], appl_type.get(r["ApplNo"]), r["SubmissionType"], r["SubmissionNo"])
        except (ValueError, KeyError):
            o.skip("ApplicationDocs.txt", r)
            continue
        iri = sub + "/doc/" + fda_iri.slug(r["ApplicationDocsID"])
        links = [("ex:hasSubmission", f"<{sub}>")]
        if r.get("ApplicationDocsTypeID") in lk["doc-type"]:
            links.append(("ex:hasDocType", f"<{lk['doc-type'][r['ApplicationDocsTypeID']]}>"))
        o.node(iri, r, "ApplicationDocument", r.get("ApplicationDocsTitle") or f'doc {r["ApplicationDocsID"]}',
               r["ApplicationDocsID"], links=links, source_url=r.get("ApplicationDocsURL") or base)
    for fname, kind, cls in (("MarketingStatus.txt", "marketing-status", "ProductMarketingStatus"),
                             ("TE.txt", "te", "TherapeuticEquivalence")):
        for i, r in enumerate(read_table(t[fname], "\t")):
            try:
                prod = app_product(r["ApplNo"], r["ProductNo"], appl_type.get(r["ApplNo"]))
            except (ValueError, KeyError):
                o.skip(fname, r)
                continue
            iri = prod + f"/{kind}/{i}"
            links = [("ex:hasProduct", f"<{prod}>")]
            if r.get("MarketingStatusID") in lk["marketing-status"]:
                links.append(("ex:hasMarketingStatus", f"<{lk['marketing-status'][r['MarketingStatusID']]}>"))
            o.node(iri, r, cls, f'{cls} {r["ApplNo"]}/{r["ProductNo"]}', f"{fname}:{i}", links=links, source_url=base)
    for fname, kind, cls in (("Join_Submission_ActionTypes_Lookup.txt", "action", "SubmissionAction"),
                             ("SubmissionPropertyType.txt", "property", "SubmissionProperty")):
        for i, r in enumerate(read_table(t[fname], "\t")):
            try:
                sub = submission(r["ApplNo"], appl_type.get(r["ApplNo"]), r["SubmissionType"], r["SubmissionNo"])
            except (ValueError, KeyError):
                o.skip(fname, r)
                continue
            iri = sub + f"/{kind}/{i}"
            links = [("ex:hasSubmission", f"<{sub}>")]
            if r.get("ActionTypes_LookupID") in lk["action-type"]:
                links.append(("ex:hasActionType", f"<{lk['action-type'][r['ActionTypes_LookupID']]}>"))
            o.node(iri, r, cls, f"{cls} {i}", f"{fname}:{i}", links=links, source_url=base)
    o.close()
    return o


def convert_orangebook(snap, out_path, stamp):
    t = zip_tables(next(snap.glob("*.zip")))
    o = Out(out_path, D, "ObFile", {"Approval_Date", "Patent_Expire_Date_Text", "Exclusivity_Date", "Submission_Date"},
            stamp, "fda/orange-book-data-files")
    base = "https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files"
    for r in read_table(t["products.txt"], "~"):
        try:
            iri = app_product(r["Appl_No"], r["Product_No"], r.get("Appl_Type"))
            a = app(r["Appl_No"], r.get("Appl_Type"))
        except (ValueError, KeyError):
            o.skip("products.txt", r)
            continue
        o.node(iri, r, "OrangeBookProduct", f'{r.get("Trade_Name", "")} {r.get("Strength", "")} ({r.get("Appl_Type", "")}{r["Appl_No"]}/{r["Product_No"]})'.strip(),
               f'{r["Appl_No"]}:{r["Product_No"]}', links=[("ex:hasApplication", f"<{a}>")], source_url=base)
    for r in read_table(t["patent.txt"], "~"):
        try:
            prod = app_product(r["Appl_No"], r["Product_No"], r.get("Appl_Type"))
        except (ValueError, KeyError):
            o.skip("patent.txt", r)
            continue
        iri = prod + "/patent/" + fda_iri.slug(f'{r["Patent_No"]} {r.get("Patent_Use_Code", "")}'.strip())
        o.node(iri, r, "OrangeBookPatent", f'patent {r["Patent_No"]} ({r["Appl_No"]}/{r["Product_No"]})',
               f'{r["Appl_No"]}:{r["Product_No"]}:{r["Patent_No"]}', links=[("ex:hasProduct", f"<{prod}>")], source_url=base)
    for r in read_table(t["exclusivity.txt"], "~"):
        try:
            prod = app_product(r["Appl_No"], r["Product_No"], r.get("Appl_Type"))
        except (ValueError, KeyError):
            o.skip("exclusivity.txt", r)
            continue
        iri = prod + "/exclusivity/" + fda_iri.slug(f'{r["Exclusivity_Code"]} {r.get("Exclusivity_Date", "")}')
        o.node(iri, r, "OrangeBookExclusivity", f'exclusivity {r["Exclusivity_Code"]} ({r["Appl_No"]}/{r["Product_No"]})',
               f'{r["Appl_No"]}:{r["Product_No"]}:{r["Exclusivity_Code"]}', links=[("ex:hasProduct", f"<{prod}>")], source_url=base)
    o.close()
    return o


def convert_purplebook(snap, out_path, stamp):
    """Each monthly CSV has two sections, each with its own 'N/R/U,' header:
      1. the month's changes (N new, R added in release, U updated) -> PurpleBookChange,
         kept for every month;
      2. 'Purple Book Database Extract', the full current list -> PurpleBookProduct,
         taken from the LATEST month only (older extracts stay in the raw snapshot)."""
    o = Out(out_path, D, "PbFile",
            {"Approval Date", "Inter. Approval Date", "Date of First Licensure", "Exclusivity Expiration Date",
             "First Interchangeable Exclusivity Exp. Date", "Ref. Product Exclusivity Exp. Date",
             "Orphan Exclusivity Exp. Date"}, stamp, "fda/purple-book-monthly")
    files = sorted(snap.glob("*.csv"))
    latest = files[-1] if files else None
    for f in files:
        lines = f.read_text(encoding="utf-8-sig", errors="replace").splitlines()
        heads = [i for i, ln in enumerate(lines) if ln.startswith("N/R/U,")]
        month = f.stem
        for sec, h in enumerate(heads):
            end = heads[sec + 1] if sec + 1 < len(heads) else len(lines)
            # drop the section title line that precedes the next header
            body = [ln for ln in lines[h:end] if not ln.startswith("Purple Book Database Extract")]
            if sec == 1 and f != latest:
                continue
            for i, r in enumerate(read_table("\n".join(body), ",")):
                if not r:
                    continue
                bla = r.get("BLA Number")
                try:
                    a = app(f"BLA{bla}")
                except ValueError:
                    o.skip(f"{f.name} section {sec + 1}", r)
                    continue
                prod = r.get("Product Number")
                r["_sourceFile"] = f.name
                if sec == 0:
                    iri = a + f"/purplebook/{fda_iri.slug(month)}/{i}"
                    links = [("ex:hasApplication", f"<{a}>")]
                    if prod:
                        links.append(("ex:hasProduct", f"<{app_product(f'BLA{bla}', prod)}>"))
                    o.node(iri, r, "PurpleBookChange",
                           f'{r.get("Proprietary Name", "")} BLA{bla} {r.get("N/R/U", "")} {month}'.strip(),
                           f"{month}:change:{i}", links=links,
                           source_url="https://purplebooksearch.fda.gov/downloads")
                else:
                    iri = app_product(f"BLA{bla}", prod) if prod else a + f"/purplebook-extract/{i}"
                    o.node(iri, r, "PurpleBookProduct",
                           f'{r.get("Proprietary Name") or r.get("Proper Name", "")} BLA{bla}/{prod or ""}'.strip(),
                           f"{month}:extract:{i}", links=[("ex:hasApplication", f"<{a}>")],
                           source_url="https://purplebooksearch.fda.gov/downloads")
    o.close()
    return o


def convert_warning_letters(snap, out_path, stamp):
    data = json.loads(next(snap.glob("*.json")).read_text(encoding="utf-8"))
    o = Out(out_path, C, "Wl", {"field_change_date_2", "field_letter_issue_datetime", "field_response_date",
                               "field_closeout_date"}, stamp, "fda/warning-letters-index")
    for r in data:
        r = clean(r)
        path = r.get("path")
        if not path:
            o.skip("warning-letters.json", r)
            continue
        key = path.rstrip("/").rsplit("/", 1)[-1]
        iri = fda_iri._inst(C, "warning-letter", fda_iri.slug(key))
        for k in list(r):
            if isinstance(r[k], str) and "<" in r[k]:
                r[k + "_text"] = untag(r[k])
        company = r.get("field_company_name_warning_lette_text") or untag(r.get("field_company_name_warning_lette", ""))
        links = []
        if company:
            try:
                links.append(("ex:hasFirm", f"<{fda_iri.recalling_firm(company)}>"))
            except ValueError:
                pass
        o.node(iri, r, "WarningLetter", f'{company} {r.get("field_letter_issue_datetime", "")}'.strip(), key,
               links=links, source_url="https://www.fda.gov" + path)
    o.close()
    return o


CONVERTERS = {"drugsatfda": convert_drugsatfda, "orangebook": convert_orangebook,
              "purplebook": convert_purplebook, "warning-letters": convert_warning_letters}


def main(argv):
    if len(argv) < 4 or argv[1] not in CONVERTERS:
        raise SystemExit(__doc__)
    snap = Path(argv[2])
    stamp = snap.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise SystemExit("snapshot folder must be named YYYY-MM-DD")
    Path(argv[3]).parent.mkdir(parents=True, exist_ok=True)
    o = CONVERTERS[argv[1]](snap, argv[3], stamp)
    print(f"{argv[1]} -> {Path(argv[3]).name}: {o.rows} rows, {o.m.nodes} nodes, "
          f"{o.m.triples} triples, {o.skipped} rows skipped (no key)")
    for table, (n, samples) in sorted(o.skips.items()):
        print(f"   skipped {n:>7} in {table}: e.g. {samples}")


if __name__ == "__main__":
    main(sys.argv)
