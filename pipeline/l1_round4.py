#!/usr/bin/env python3
"""
l1_round4.py -- L1 converters for the round-4 sources (official FDA files and single-table pages
found on October 27, 2026). One function per source, flat records, every column kept
(lowerCamel of the header, or the openFDA spelling where the column is the same field),
provenance on every record, dates typed when the value is a real date.

  ndc-extra        NDC Directory companion files (unfinished, excluded, compounders)   -> fda-drug-biologic-kg
  iid              Inactive Ingredient Database download (IIR_OCOMM.xlsx + change log) -> fda-drug-biologic-kg
  dmf              List of Drug Master Files (quarterly xlsx)                           -> fda-drug-biologic-kg
  outsourcing      Registered outsourcing facilities (503B) page table                  -> fda-drug-biologic-kg
  vaccines         Vaccines licensed for use in the United States page table            -> fda-drug-biologic-kg
  cgt              Approved cellular and gene therapy products page table               -> fda-drug-biologic-kg
  debarment        FDA debarment list (drug product applications) xlsx                  -> fda-compliance-kg
  disqualification Clinical investigators disqualification proceedings export (HTML)   -> fda-compliance-kg
  tds              Total Diet Study results FY2018-2020 (elements, radionuclides txt)   -> fda-food-cosmetic-kg

Keys:
  ndc-extra   products  ndc-product/<PRODUCTID>  (same key space as the openFDA NDC listing, class NdcProduct,
              ex:ndcDirectoryList "unfinished" | "excluded"); packages ndc-package/<NDCPACKAGECODE> (class
              NdcPackage, same list marker); compounders rows compounded-product-report/<sha1> with
              ex:hasPackageNdc to the package node
  iid         inactive-ingredient-record/<sha1 of the row>, ex:hasSubstance when the row carries a UNII;
              change log rows iid-change/<sha1 of the row>
  dmf         drug-master-file/<DMF number>
  outsourcing outsourcing-facility/<sha1 of the row>
  vaccines    licensed-vaccine/<sha1 of the row>
  cgt         cgt-product/<sha1 of the row>
  debarment   debarment/<sha1 of the row>          (the statutory public list; the person is the record)
  disqualification investigator-disqualification/<sha1 of the row>   (public proceedings list)
  tds         tds-result/<sha1 of the row>, one record per analyte measurement

Usage: python3 l1_round4.py <source> <snapshot_dir> <out.ttl[.gz]>
"""
import csv
import gzip
import html as htmlmod
import io
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402
import xlsx_min    # noqa: E402

D, C, S, F = "fda-drug-biologic-kg", "fda-compliance-kg", "fda-substance-kg", "fda-food-cosmetic-kg"
csv.field_size_limit(1 << 28)
_UNII = re.compile(r"^[A-Z0-9]{10}$")
_DD_MON_YY = re.compile(r"^(\d{1,2})-([A-Za-z]{3})-(\d{2}|\d{4})$")
_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# NDC companion files use the same fields as the openFDA NDC endpoint under upper-case names;
# the openFDA spelling is used so a query sees one predicate across both sources.
NDC_ALIAS = {
    "PRODUCTID": "productId", "PRODUCTNDC": "productNdc", "PRODUCTTYPENAME": "productType",
    "PROPRIETARYNAME": "brandName", "PROPRIETARYNAMESUFFIX": "brandNameSuffix", "NONPROPRIETARYNAME": "genericName",
    "DOSAGEFORMNAME": "dosageForm", "ROUTENAME": "route", "STARTMARKETINGDATE": "marketingStartDate",
    "ENDMARKETINGDATE": "marketingEndDate", "MARKETINGCATEGORYNAME": "marketingCategory",
    "APPLICATIONNUMBER": "applicationNumber", "LABELERNAME": "labelerName", "SUBSTANCENAME": "substanceName",
    "ACTIVE_NUMERATOR_STRENGTH": "activeNumeratorStrength", "ACTIVE_INGRED_UNIT": "activeIngredUnit",
    "PHARM_CLASSES": "pharmClass", "DEASCHEDULE": "deaSchedule", "NDC_EXCLUDE_FLAG": "ndcExcludeFlag",
    "LISTING_RECORD_CERTIFIED_THROUGH": "listingExpirationDate", "NDCPACKAGECODE": "packageNdc",
    "PACKAGEDESCRIPTION": "description", "SAMPLE_PACKAGE": "samplePackage",
    "ACTIVEINGREDIENTSINFO": "activeIngredientsInfo", "REPORTINGPERIOD": "reportingPeriod",
}
NDC_DATES = {"marketingStartDate", "marketingEndDate", "listingExpirationDate"}


def date_lit(v):
    """mapper.date_lit plus DD-MON-YY (unfinished_package.txt writes '04-DEC-09'). Two-digit years
    below 50 are 20xx, the rest 19xx; a value that is not a date stays a plain string."""
    s = str(v).strip() if v is not None else ""
    if not s:
        return None
    m = _DD_MON_YY.match(s)
    if m and m.group(2).lower() in _MON:
        yy = m.group(3)
        yyyy = yy if len(yy) == 4 else (f"20{yy}" if int(yy) < 50 else f"19{yy}")
        typed = common.date_lit(f"{yyyy}{_MON[m.group(2).lower()]:02d}{int(m.group(1)):02d}")
        return typed if typed.endswith("^^xsd:date") else common.lit(s)
    return mapper.date_lit(v)


class Writer:
    def __init__(self, out, graph, dataset, stamp, url):
        p = str(out)
        self.fh = gzip.open(p, "wt", encoding="utf-8", newline="\n", compresslevel=6) if p.endswith(".gz") \
            else open(p, "w", encoding="utf-8", newline="\n")
        self.fh.write(common.prefixes({"ex": fda_iri.ns(graph)}) + "\n")
        self.graph, self.dataset, self.stamp, self.url = graph, dataset, stamp, url
        self.n = self.triples = self.dup = 0
        self.seen = set()

    def flat(self, iri, cls, row, label, rec_id, links=(), dates=frozenset(), alias=None, dataset=None, url=None, dedupe=True):
        if dedupe and iri in self.seen:
            self.dup += 1
            return False
        self.seen.add(iri)
        pairs = [("a", f"ex:{cls}")]
        for col, v in row.items():
            if v is None or str(v).strip() == "":
                continue
            key = (alias or {}).get(col) or mapper.camel(col)
            typed = date_lit(v) if (key in dates or (not dates and "date" in col.lower())) else common.lit(v)
            pairs.append((f"ex:{key}", typed))
        pairs.append(("rdfs:label", common.lit(label)))
        pairs += list(links)
        pairs += common.provenance(dataset or self.dataset, rec_id, source_url=url or self.url, retrieved_at=self.stamp)
        self.triples += common.write_block(self.fh, f"<{iri}>", pairs)
        self.n += 1
        return True

    def close(self):
        self.fh.close()


def _first(snap, patterns):
    for pat in patterns:
        for p in sorted(Path(snap).glob(pat)):
            if p.name not in ("SHA256SUMS", "SOURCE_URL"):
                return p
    raise SystemExit(f"no input matching {patterns} in {snap}")


def _clean(row):
    out = {}
    for k, v in row.items():
        if k is None:
            continue
        k = k.strip().lstrip("﻿")
        if isinstance(v, str):
            v = v.strip()
        if k and v not in (None, ""):
            out[k] = v
    return out


def _tsv_rows(text):
    return (_clean(r) for r in csv.DictReader(io.StringIO(text), delimiter="\t"))


def _zip_text(zpath, member):
    with zipfile.ZipFile(zpath) as z:
        raw = z.read(member)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _app_link(number):
    try:
        return [("ex:hasApplication", f"<{fda_iri.application(number)}>")]
    except ValueError:
        return []


# ---------------------------------------------------------------------------
NDC_PAGE = "https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory"


def convert_ndc_extra(snap, out, stamp):
    snap = Path(snap)
    w = Writer(out, D, "fda/ndc-directory-companion-files", stamp, NDC_PAGE)
    files = [  # (zip, member, list marker, kind)
        ("ndc_unfinished.zip", "unfinished_product.txt", "unfinished", "product"),
        ("ndc_unfinished.zip", "unfinished_package.txt", "unfinished", "package"),
        ("ndc_excluded.zip", "Products_excluded.txt", "excluded", "product"),
        ("ndc_excluded.zip", "Packages_excluded.txt", "excluded", "package"),
    ]
    for zname, member, marker, kind in files:
        zpath = snap / zname
        if not zpath.exists():
            print(f"  missing {zname}", file=sys.stderr)
            continue
        url = f"https://www.accessdata.fda.gov/cder/{zname}"
        for i, row in enumerate(_tsv_rows(_zip_text(zpath, member))):
            if kind == "product":
                pid = row.get("PRODUCTID")
                if not pid:
                    continue
                iri = fda_iri.ndc_product(pid)
                links = [("ex:ndcDirectoryList", common.lit(marker))] + _app_link(row.get("APPLICATIONNUMBER"))
                label = f"{row.get('PROPRIETARYNAME') or row.get('NONPROPRIETARYNAME') or row.get('PRODUCTNDC')} (NDC {row.get('PRODUCTNDC')}, {marker})"
                w.flat(iri, "NdcProduct", row, label, pid, links, NDC_DATES, NDC_ALIAS, f"fda/ndc-{marker}/{member}", url, dedupe=False)
            else:
                code = row.get("NDCPACKAGECODE")
                if not code:
                    continue
                iri = fda_iri.ndc_package(code)
                links = [("ex:ndcDirectoryList", common.lit(marker))]
                if row.get("PRODUCTID"):
                    links.append(("ex:hasProduct", f"<{fda_iri.ndc_product(row['PRODUCTID'])}>"))
                w.flat(iri, "NdcPackage", row, f"{row.get('PACKAGEDESCRIPTION') or code} ({marker})", code, links,
                       NDC_DATES, NDC_ALIAS, f"fda/ndc-{marker}/{member}", url, dedupe=False)
    zpath = snap / "compounders_ndc_directory.zip"
    if zpath.exists():
        url = "https://www.accessdata.fda.gov/cder/compounders_ndc_directory.zip"
        for i, row in enumerate(_tsv_rows(_zip_text(zpath, "compounders_ndc_directory.txt"))):
            if not row:
                continue
            iri = fda_iri.hashed(D, "compounded-product-report", row)
            links = [("ex:ndcDirectoryList", common.lit("compounders"))]
            if row.get("NDCPACKAGECODE"):
                links.append(("ex:hasPackageNdc", f"<{fda_iri.ndc_package(row['NDCPACKAGECODE'])}>"))
            label = f"{row.get('PROPRIETARYNAME') or row.get('NONPROPRIETARYNAME') or 'compounded product'} {row.get('PRODUCTNDC', '')} {row.get('REPORTINGPERIOD', '')}".strip()
            w.flat(iri, "CompoundedProductReport", row, label, f"row:{i}", links, NDC_DATES, NDC_ALIAS,
                   "fda/ndc-compounders/compounders_ndc_directory.txt", url)
    w.close()
    return w


# ---------------------------------------------------------------------------
TDS_PAGE = "https://www.fda.gov/food/fda-total-diet-study-tds/fda-total-diet-study-tds-results"


def convert_tds(snap, out, stamp):
    w = Writer(out, F, "fda/total-diet-study-results", stamp, TDS_PAGE)
    for src in sorted(Path(snap).glob("*.txt")):
        text = src.read_text(encoding="utf-8", errors="replace")
        for i, row in enumerate(_tsv_rows(text)):
            if not row:
                continue
            iri = fda_iri.hashed(F, "tds-result", dict(row, _file=src.name))
            label = f"{row.get('Analyte', '').strip()} in {row.get('TDSFoodDescription', '')} (FY{row.get('FiscalYear', '')}, {row.get('Region', '')})"
            w.flat(iri, "TdsResult", row, label, f"{src.name}:row:{i}", dates=frozenset(), dataset=f"fda/total-diet-study/{src.name}")
    w.close()
    return w


# ---------------------------------------------------------------------------
_FOOTNOTE = re.compile(r"\s*\d+(\s*,\s*\d+)*$")      # 'Initial Registration Date 1' -> 'Initial Registration Date'


def _tables(text):
    """[(header cells, [(cells, hrefs)...])] for every table in an HTML document. Cell text is
    untagged; hrefs lists the absolute link targets inside each cell (letters on the
    disqualification export, product pages on the CBER lists)."""
    out = []
    for t in re.findall(r"<table\b.*?</table>", text, re.S | re.I):
        rows = []
        for tr in re.findall(r"<tr\b.*?</tr>", t, re.S | re.I):
            raw = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", tr, re.S | re.I)
            cells = [" ".join(htmlmod.unescape(re.sub(r"<[^>]+>", " ", c)).split()) for c in raw]
            hrefs = [[h if h.startswith("http") else "https://www.fda.gov" + h
                      for h in re.findall(r'href="([^"]+)"', c, re.I)] for c in raw]
            if cells:
                rows.append((bool(re.search(r"<th\b", tr, re.I)), cells, hrefs))
        if not rows:
            continue
        header = next((c for is_th, c, _h in rows if is_th), rows[0][1])
        header = [_FOOTNOTE.sub("", h).strip() for h in header]
        body = [(c, h) for is_th, c, h in rows if not is_th and c is not rows[0][1]]
        out.append((header, body))
    return out


def _table_rows(text, want):
    """Dict rows of the first table whose header mentions every word in `want`; a cell with
    links also yields '<Header> Url' entries (one value per link, joined by a space)."""
    for header, body in _tables(text):
        text_h = " ".join(header).lower()
        if all(wd in text_h for wd in want):
            for cells, hrefs in body:
                row = {}
                for h, v, links in zip(header, cells, hrefs):
                    if h and v:
                        row[h] = v
                    if h and links:
                        row[f"{h} Url"] = " ".join(dict.fromkeys(links))
                if row:
                    yield row
            return
    raise SystemExit(f"no table with header words {want}")


def convert_html_table(snap, out, stamp, graph, cls, kind, dataset, url, want, label_cols, drop=()):
    """One record per table row. `drop` names columns never written (the 503B list's Contact
    column is a named person with a phone number: contact persons are not published)."""
    src = _first(snap, ["*.html", "*.xls"])
    text = src.read_text(encoding="utf-8", errors="replace")
    w = Writer(out, graph, dataset, stamp, url)
    for i, row in enumerate(_table_rows(text, want)):
        row = {k: v for k, v in row.items() if k not in drop}
        iri = fda_iri.hashed(graph, kind, row)
        label = " ".join(str(row.get(c, "")) for c in label_cols if row.get(c)).strip() or f"{kind} row {i}"
        w.flat(iri, cls, row, label, f"row:{i}")
    w.close()
    return w


# ---------------------------------------------------------------------------
IID_PAGE = "https://www.fda.gov/drugs/drug-approvals-and-databases/inactive-ingredients-database-download"


def convert_iid(snap, out, stamp):
    """IIR_OCOMM.xlsx: one record per (ingredient, route, dosage form) row, every column kept,
    ex:hasSubstance when the UNII column holds a UNII. Change_Log_Data.csv: one record per change row."""
    import tempfile
    snap = Path(snap)
    zpath = _first(snap, ["*.zip"])
    work = Path(tempfile.mkdtemp(prefix="iid_"))
    with zipfile.ZipFile(zpath) as z:
        z.extract("IIR_OCOMM.xlsx", work)
        log_text = z.read("Change_Log_Data.csv").decode("utf-8-sig", errors="replace")
    w = Writer(out, D, "fda/inactive-ingredient-database", stamp, IID_PAGE)
    for i, row in enumerate(xlsx_min.dict_rows(work / "IIR_OCOMM.xlsx")):
        row = _clean(row)
        if not row:
            continue
        iri = fda_iri.hashed(D, "inactive-ingredient-record", row)
        links = []
        unii = (row.get("UNII") or "").strip().upper()
        if _UNII.match(unii):
            links.append(("ex:hasSubstance", f"<{fda_iri.substance(unii)}>"))
        label = f"{row.get('INGREDIENT_NAME', '')} ({row.get('ROUTE', '')}; {row.get('DOSAGE_FORM', '')})"
        w.flat(iri, "InactiveIngredientRecord", row, label, f"IIR_OCOMM.xlsx:row:{i}", links,
               dates=frozenset({"recordUpdated"}), dataset="fda/inactive-ingredient-database/IIR_OCOMM.xlsx")
    for i, row in enumerate(csv.DictReader(io.StringIO(log_text))):
        row = _clean(row)
        if not row:
            continue
        iri = fda_iri.hashed(D, "iid-change", row)
        label = f"IID change {row.get('Change ID', '')}: {row.get('Inactive Ingredient', '')} ({row.get('Snapshot Date', '')})"
        w.flat(iri, "InactiveIngredientChange", row, label, f"Change_Log_Data.csv:row:{i}",
               dates=frozenset(), dataset="fda/inactive-ingredient-database/Change_Log_Data.csv")
    (work / "IIR_OCOMM.xlsx").unlink()
    work.rmdir()
    w.close()
    return w


# ---------------------------------------------------------------------------
DMF_PAGE = "https://www.fda.gov/drugs/drug-master-files-dmfs/list-drug-master-files-dmfs"


def _serial(v):
    """Excel serial -> ISO date for any positive integer (the DMF list has 1940s dates below
    the 20000 floor xlsx_min uses for untyped cells)."""
    s = str(v).strip()
    if s.isdigit() and 0 < int(s) < 80000:
        from datetime import datetime, timedelta
        return (datetime(1899, 12, 30) + timedelta(days=int(s))).strftime("%Y-%m-%d")
    return s


def convert_dmf(snap, out, stamp):
    src = _first(snap, ["*.xlsx"])
    w = Writer(out, D, "fda/list-of-drug-master-files", stamp, DMF_PAGE)
    header = None
    for i, r in enumerate(xlsx_min.rows(src)):
        cells = [c for c in r if c]
        if header is None:
            if len(cells) >= 4 and any(str(c).upper().startswith("DMF") for c in cells):
                header = [str(h).strip() if h else None for h in r]
            continue
        row = {k: v for k, v in zip(header, r) if k and v is not None and str(v).strip() != ""}
        if not row.get("DMF#"):
            continue
        if row.get("SUBMIT DATE"):
            row["SUBMIT DATE"] = _serial(row["SUBMIT DATE"])
        num = str(row["DMF#"]).strip()
        iri = fda_iri._inst(D, "drug-master-file", fda_iri.slug(num))
        label = f"DMF {num} {row.get('SUBJECT', '')}".strip()
        w.flat(iri, "DrugMasterFile", row, label, num, dates=frozenset({"submitDate"}), alias={"DMF#": "dmfNumber"})
    w.close()
    return w


# ---------------------------------------------------------------------------
DEBAR_PAGE = "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/fda-debarment-list-drug-product-applications"


def convert_debarment(snap, out, stamp):
    src = _first(snap, ["*.xlsx"])
    w = Writer(out, C, "fda/debarment-list-drug-product-applications", stamp, DEBAR_PAGE)
    for i, row in enumerate(xlsx_min.dict_rows(src)):
        row = _clean(row)
        if not row:
            continue
        iri = fda_iri.hashed(C, "debarment", row)
        label = f"{row.get('Last Name', '')}, {row.get('First & Middle Names', '')} ({row.get('Effective Date', '')})"
        w.flat(iri, "Debarment", row, label, f"row:{i}", dates=frozenset({"effectiveDate", "frDateTxtMmDdYy"}))
    w.close()
    return w


# ---------------------------------------------------------------------------
SOURCES = {
    "ndc-extra": convert_ndc_extra,
    "tds": convert_tds,
    "iid": convert_iid,
    "dmf": convert_dmf,
    "debarment": convert_debarment,
    "disqualification": lambda s, o, st: convert_html_table(
        s, o, st, C, "InvestigatorDisqualification", "investigator-disqualification",
        "fda/clinical-investigators-disqualification-proceedings",
        "https://www.accessdata.fda.gov/scripts/sda/sdNavigation.cfm?sd=clinicalinvestigatorsdisqualificationproceedings",
        ["name", "status"], ["Name", "Center", "Status"]),
    "outsourcing": lambda s, o, st: convert_html_table(
        s, o, st, D, "OutsourcingFacility", "outsourcing-facility", "fda/registered-outsourcing-facilities",
        "https://www.fda.gov/drugs/human-drug-compounding/registered-outsourcing-facilities",
        ["facility"], ["Facility"], drop=("Contact", "Contact Url")),
    "vaccines": lambda s, o, st: convert_html_table(
        s, o, st, D, "LicensedVaccine", "licensed-vaccine", "fda/vaccines-licensed-for-use-in-the-united-states",
        "https://www.fda.gov/vaccines-blood-biologics/vaccines/vaccines-licensed-use-united-states",
        ["product name", "trade name"], ["Trade Name", "Product Name"]),
    "cgt": lambda s, o, st: convert_html_table(
        s, o, st, D, "CellularGeneTherapyProduct", "cgt-product", "fda/approved-cellular-and-gene-therapy-products",
        "https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/approved-cellular-and-gene-therapy-products",
        ["product", "manufacturer"], ["Product & Trade Name", "Manufacturer"]),
}


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] not in SOURCES:
        raise SystemExit(__doc__)
    source, snap, out = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    w = SOURCES[source](snap, out, snap.name)
    print(f"{source} -> {Path(out).name}: {w.n} records, {w.triples} triples, {w.dup} duplicate rows skipped")
