#!/usr/bin/env python3
"""
xlsx_min.py -- a dependency-free reader for simple .xlsx exports (one sheet, shared
strings, inline strings, numbers, dates as serials). Enough for FDA's datatable and
media downloads; not a general Excel parser.

rows(path) yields lists of cell values (str, or None for empty cells) for sheet 1,
in row order, with trailing empty cells kept so columns line up.
"""
import re
import zipfile
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_COL = re.compile(r"([A-Z]+)(\d+)")


def _col_index(ref):
    letters = _COL.match(ref).group(1)
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _serial_to_date(v):
    try:
        f = float(v)
    except ValueError:
        return v
    if f.is_integer() and 20000 < f < 80000:          # 1954..2119: an Excel date serial
        return (datetime(1899, 12, 30) + timedelta(days=int(f))).strftime("%Y-%m-%d")
    return v


def _shared_strings(z):
    """Shared-string table, streamed (large exports such as the DMF list have hundreds of
    thousands of strings; a full DOM of the table and the sheet needs several GB)."""
    shared = []
    if "xl/sharedStrings.xml" not in z.namelist():
        return shared
    SI, T = "{%s}si" % NS["m"], "{%s}t" % NS["m"]
    with z.open("xl/sharedStrings.xml") as fh:
        for _ev, el in ET.iterparse(fh):
            if el.tag == SI:
                shared.append("".join(t.text or "" for t in el.iter(T)))
                el.clear()
    return shared


def rows(path, sheet="xl/worksheets/sheet1.xml"):
    with zipfile.ZipFile(path) as z:
        shared = _shared_strings(z)
        date_styles = set()
        if "xl/styles.xml" in z.namelist():
            st = ET.fromstring(z.read("xl/styles.xml"))
            numfmts = {nf.get("numFmtId"): nf.get("formatCode", "") for nf in st.iter("{%s}numFmt" % NS["m"])}
            xfs = st.find("m:cellXfs", NS)
            if xfs is not None:
                for i, xf in enumerate(xfs.findall("m:xf", NS)):
                    fid = xf.get("numFmtId", "0")
                    code = numfmts.get(fid, "")
                    if fid in {"14", "15", "16", "17", "22"} or re.search(r"[dy]", code.lower()) and "m" in code.lower():
                        date_styles.add(str(i))
        ROW = "{%s}row" % NS["m"]
        fh = z.open(sheet)
        for _ev, row in ET.iterparse(fh):
            if row.tag != ROW:
                continue
            out = []
            for c in row.findall("m:c", NS):
                idx = _col_index(c.get("r"))
                while len(out) < idx:
                    out.append(None)
                t, s = c.get("t"), c.get("s")
                v = c.find("m:v", NS)
                if t == "s" and v is not None:
                    val = shared[int(v.text)]
                elif t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                elif v is not None:
                    val = v.text
                    if s in date_styles:
                        val = _serial_to_date(val)
                else:
                    val = None
                out.append(val.strip() if isinstance(val, str) and val.strip() else (val if val not in ("",) else None))
            row.clear()
            yield out
        fh.close()


def dict_rows(path, header_row=0, **kw):
    """Dict per row keyed by the header row's text; blank cells dropped."""
    it = rows(path, **kw)
    header = None
    for i, r in enumerate(it):
        if i < header_row:
            continue
        if header is None:
            header = [h for h in r]
            continue
        d = {}
        for k, v in zip(header, r):
            if k and v is not None:
                d[k.strip()] = v
        if d:
            yield d


if __name__ == "__main__":
    import sys
    for i, r in enumerate(dict_rows(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 0)):
        print(r)
        if i >= 4:
            break
