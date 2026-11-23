"""bmedesign-kg commons: the one copy of the literal and metadata helpers every graph pipeline uses.

Master-owned. Graph pipelines that cannot import bmedesign-kg copy this file VERBATIM as
`bmed_commons.py` and never edit it; a change is a request to the master. The version below is
what the copy must report in its release notes.

  scrub_text(s)        e-mail addresses -> "[EMAIL REMOVED]" (same pattern the L1-SCRUB check uses)
  plain_decimal(x)     decimal literal in plain notation, never exponent form
  typed_date(s)        YYYY -> xsd:gYear, YYYY-MM -> xsd:gYearMonth, YYYY-MM-DD -> xsd:date, else plain string;
                       also YYYYMMDD, YYYYMM, YYYY-MM-DDThh:mm:ss (date part) and MM/DD/YYYY
  fei(x), fei_firm_iri(x)  FEI in the family form (10 digits, zero-padded) and the fda-compliance-kg Firm IRI
  prov(...)            the core provenance block for one record or hub
  void_ttl(...)        void.ttl text that passes L2-METADATA
"""
import datetime as _dt, re
from decimal import Decimal, InvalidOperation

VERSION = "1.2.1"   # 1.1.0 (Nov 22, 2026): fei(), fei_firm_iri(); 1.2.0 (Nov 23, 2026): linear-time scrub_text, ExPORTER date forms; 1.2.1: impossible dates keep the source text
CORE = "https://bmedesign.org/core/ns/"
CC0 = "https://creativecommons.org/publicdomain/zero/1.0/"
XSD = "http://www.w3.org/2001/XMLSchema#"
# the lookbehind stops the engine retrying inside a word, so long text stays linear (request 2026-11-23-commons-scrub-performance);
# a match always starts at the beginning of the word, so it finds the same addresses as before
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@(?:[\w-]+\.)+[A-Za-z]{2,}(?![A-Za-z])")
EMAIL_MARK = "[EMAIL REMOVED]"

def scrub_text(s):
    if s is None: return None
    s = str(s)
    return EMAIL.sub(EMAIL_MARK, s) if "@" in s else s

def plain_decimal(x):
    """Plain-notation decimal string ('0.00012', '1500'), or None if x is not a number."""
    try: d = Decimal(str(x).strip())
    except (InvalidOperation, ValueError): return None
    if not d.is_finite(): return None
    s = format(d, "f")
    if "." in s: s = s.rstrip("0").rstrip(".") or "0"
    return "0" if s in ("-0", "") else s

_Y, _YM, _YMD = re.compile(r"^\d{4}$"), re.compile(r"^\d{4}-(0[1-9]|1[0-2])$"), re.compile(r"^\d{4}-\d{2}-\d{2}$")
def typed_date(s):
    """(lexical, datatype IRI or None). Compact openFDA forms (YYYYMMDD, YYYYMM) are expanded first."""
    if s is None: return None, None
    src = t = str(s).strip()
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})T[\d:.]+(Z|[+-]\d{2}:?\d{2})?", t)          # 1995-06-30T00:00:00 (NIH ExPORTER) -> date part
    if m: t = m.group(1)
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)                              # 06/30/1995 (US month/day/year)
    if m: t = f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    if re.fullmatch(r"\d{8}", t): t = f"{t[:4]}-{t[4:6]}-{t[6:]}"
    elif re.fullmatch(r"\d{6}", t) and 1 <= int(t[4:]) <= 12: t = f"{t[:4]}-{t[4:]}"
    if _Y.match(t): return t, XSD + "gYear"
    if _YM.match(t): return t, XSD + "gYearMonth"
    if _YMD.match(t):
        try: _dt.date.fromisoformat(t); return t, XSD + "date"
        except ValueError: pass
    return src, None   # not a real date: keep the text as the source gave it (request 2026-11-23-conform-empty-input)

def fei(x):
    """FEI in the canonical family form: digits only, zero-padded to 10 (the form fda-compliance-kg mints). None if empty."""
    d = re.sub(r"\D", "", str(x or ""))
    return d.zfill(10) if d else None

def fei_firm_iri(x):
    v = fei(x)
    return f"https://bmedesign.org/fda-compliance-kg/id/firm/{v}" if v else None

def prov(source_dataset, retrieved_at, source_record_id=None, source_url=None):
    """[(core predicate IRI, lexical, datatype)] for one record or hub. Hubs pass their latest retrieval date
    and the datasets joined with '; '."""
    out = [(CORE + "sourceDataset", str(source_dataset), None), (CORE + "retrievedAt", str(retrieved_at), XSD + "date")]
    if source_record_id: out.append((CORE + "sourceRecordId", str(source_record_id), None))
    if source_url: out.append((CORE + "sourceUrl", str(source_url), XSD + "anyURI"))
    return out

def _q(s): return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'

def void_ttl(dataset_iri, title, version, snapshot_date, description=None, triples=None, sources=(), creator="Roche C. de Guzman"):
    """version must equal the registry current_release (e.g. v0.0.2); snapshot_date is YYYY-MM-DD."""
    L = ["@prefix dcterms: <http://purl.org/dc/terms/> .", "@prefix owl: <http://www.w3.org/2002/07/owl#> .",
         "@prefix void: <http://rdfs.org/ns/void#> .", "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .", "",
         f"<{dataset_iri}> a void:Dataset ;", f"    dcterms:title {_q(title)} ;"]
    if description: L.append(f"    dcterms:description {_q(description)} ;")
    L += [f"    dcterms:license <{CC0}> ;", f"    owl:versionInfo {_q(version)} ;", f'    dcterms:issued "{snapshot_date}"^^xsd:date ;',
          f"    dcterms:creator {_q(creator)} ;"]
    if triples is not None: L.append(f"    void:triples {int(triples)} ;")
    L += [f"    dcterms:source <{s}> ;" for s in sources]
    L[-1] = L[-1][:-2] + " ."
    return "\n".join(L) + "\n"
