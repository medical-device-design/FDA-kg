#!/usr/bin/env python3
"""
fda_iri.py -- the single source of every IRI in the FDA regulated-products graphs.

Same system as medical-device-kg/pipeline/iri.py (Roche, 2026-10-12):
  * one namespace pair per graph, named by its okn.us shortname
        vocabulary  https://bmedesign.org/<shortname>/ns/
        instances   https://bmedesign.org/<shortname>/id/
  * instance paths are <kebab-type>/<slug(key)>, slug() is the device rule
    (lowercase, runs of non-[a-z0-9] -> "_", strip "_"), opaque ids verbatim
  * deterministic, and empty keys raise instead of making orphan nodes

An entity is minted ONLY by the graph that owns it. Other graphs reference that
IRI (for example a drug recall's UNII points at fda-substance-kg's substance).
"""
import re

BASE = "https://bmedesign.org/"
GRAPHS = (
    "fda-compliance-kg", "fda-substance-kg", "fda-drug-biologic-kg",
    "fda-food-cosmetic-kg", "fda-animal-health-kg", "fda-tobacco-kg",
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_SAFE_VERBATIM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._~-]*$")


def slug(value):
    if value is None:
        raise ValueError("slug() received None")
    s = _NON_ALNUM.sub("_", str(value).strip().lower()).strip("_")
    if not s:
        raise ValueError(f"value {value!r} slugs to empty; cannot mint an IRI")
    return s


def _verbatim(value):
    s = str(value).strip()
    if not _SAFE_VERBATIM.match(s):
        raise ValueError(f"key {value!r} is not URI-safe for verbatim use")
    return s


def ns(graph):
    assert graph in GRAPHS, graph
    return f"{BASE}{graph}/ns/"


def id_base(graph):
    assert graph in GRAPHS, graph
    return f"{BASE}{graph}/id/"


def term(graph, name):
    if not name or not _SAFE_VERBATIM.match(str(name)):
        raise ValueError(f"invalid vocabulary term name: {name!r}")
    return ns(graph) + name


def _inst(graph, *segments):
    return id_base(graph) + "/".join(segments)


# ---- fda-substance-kg -----------------------------------------------------
def substance(unii):
    """substance('S8B49CX5KM') -> .../fda-substance-kg/id/unii/s8b49cx5km"""
    return _inst("fda-substance-kg", "unii", slug(unii))


def gsrs_substance(uuid):
    """GSRS substance that has NO UNII, keyed on its GSRS uuid (verbatim).
    gsrs_substance('c088fcc5-2fe2-4aa6-8524-cb7aa8aa4a02')
      -> .../fda-substance-kg/id/gsrs/c088fcc5-2fe2-4aa6-8524-cb7aa8aa4a02"""
    return _inst("fda-substance-kg", "gsrs", _verbatim(uuid))


def substance_ref(unii=None, uuid=None):
    """The ONE rule for which IRI a substance gets: UNII when it has one,
    otherwise its GSRS uuid. Used for both the record and every reference to it."""
    if unii and str(unii).strip():
        return substance(unii)
    if uuid and str(uuid).strip():
        return gsrs_substance(uuid)
    raise ValueError("substance_ref() needs a unii or a uuid")


def child(parent, *segments):
    """A node nested under another IRI (device pattern: udi/<key>/storage/0).
    Segments are kebab names, opaque uuids or integer indexes, used verbatim."""
    return parent + "/" + "/".join(_verbatim(str(s)) for s in segments)


# ---- fda-compliance-kg (hub) ---------------------------------------------
def recall(recall_number):
    """Same slug rule as the device graph's recall().
    recall('D-0862-2026') -> .../fda-compliance-kg/id/recall/d_0862_2026"""
    return _inst("fda-compliance-kg", "recall", slug(recall_number))


def recall_by_event(event_id, n):
    """A recall published WITHOUT a recall number (Roche, 2026-10-12: key by event).
    n is its 1-based position among the unnumbered records of that event, in source
    order. Cannot collide with a real recall number, which never starts "event".
    When FDA later assigns the number, the next rebuild mints recall() instead.
    recall_by_event('99892', 1) -> .../fda-compliance-kg/id/recall/event_99892_1"""
    return _inst("fda-compliance-kg", "recall", slug(f"event {slug(event_id)} {int(n)}"))


def recall_event(event_id):
    """recall_event('99712') -> .../fda-compliance-kg/id/recall-event/99712"""
    return _inst("fda-compliance-kg", "recall-event", slug(event_id))


def recalling_firm(name):
    """L1 name-keyed firm as enforcement data gives it (no FEI there).
    Kept apart from FEI-keyed firm() so L2 can resolve without rewriting IRIs.
    recalling_firm('Kwok Shing, Inc.') -> .../recalling-firm/kwok_shing_inc"""
    return _inst("fda-compliance-kg", "recalling-firm", slug(name))


def firm(fei):
    """FEI-keyed firm or facility (Data Dashboard, DECRS).
    firm('3001234567') -> .../fda-compliance-kg/id/firm/3001234567"""
    return _inst("fda-compliance-kg", "firm", slug(fei))


# ---- fda-drug-biologic-kg ------------------------------------------------
_APPL = re.compile(r"^(NDA|ANDA|BLA|BL|BA|BN)\s*0*(\d+)(?:/.*)?$", re.I)
_PREFIX_FIX = {"BL": "BLA"}


def normalize_application(number=None, app_type=None):
    """Canonical application number. Drugs@FDA writes 'NDA021234' or 'ANDA076803';
    the Orange Book writes '020512' with application_type 'N' or 'A'; NSDE and CRLs
    sometimes add spaces. Returns e.g. 'NDA021234', or None if not an application."""
    if number is None:
        return None
    s = re.sub(r"\s+", "", str(number)).upper()
    m = _APPL.match(s)
    if m:
        prefix = m.group(1).upper()
        return f"{_PREFIX_FIX.get(prefix, prefix)}{int(m.group(2)):06d}"
    if s.isdigit() and app_type:
        prefix = {"N": "NDA", "A": "ANDA", "B": "BLA"}.get(str(app_type).upper()[:1])
        return f"{prefix}{int(s):06d}" if prefix else None
    return None


def application(number, app_type=None):
    """Drug or biologic application (NDA, ANDA, BLA): the hub of the drug graph.
    application('NDA021234') -> .../fda-drug-biologic-kg/id/application/nda021234
    application('020512', 'A') -> .../application/anda020512"""
    canon = normalize_application(number, app_type)
    if not canon:
        raise ValueError(f"not an application number: {number!r}")
    return _inst("fda-drug-biologic-kg", "application", slug(canon))


def application_untyped(number):
    """An application number whose type (NDA/ANDA/BLA) the source does not give and
    Applications.txt does not list, e.g. Drugs@FDA submission rows for ApplNo 000415.
    Kept rather than dropped (no-data-loss rule); the IRI has no type prefix, so a
    query can find these for later resolution.  application_untyped('000415')
    -> .../fda-drug-biologic-kg/id/application/000415"""
    s = re.sub(r"\s+", "", str(number))
    if not s.isdigit():
        raise ValueError(f"not a bare application number: {number!r}")
    return _inst("fda-drug-biologic-kg", "application", f"{int(s):06d}")


def application_product(number, product_number, app_type=None):
    """A product within an application (Drugs@FDA products, Orange Book rows).
    application_product('ANDA020512', '001') -> .../application/anda020512/product/001"""
    return application(number, app_type) + "/product/" + slug(product_number)


def ndc_product(product_id):
    """NDC Directory product, keyed on openFDA's product_id (product_ndc + SPL id),
    the only key that is unique across the directory. Kept verbatim.
    ndc_product('71558-001_43046e5b-...') -> .../ndc-product/71558-001_43046e5b-..."""
    return _inst("fda-drug-biologic-kg", "ndc-product", _verbatim(product_id))


def ndc_package(package_ndc):
    """A package NDC, shared by the NDC Directory packaging list, NSDE and shortages.
    ndc_package('71558-001-30') -> .../fda-drug-biologic-kg/id/ndc-package/71558_001_30"""
    return _inst("fda-drug-biologic-kg", "ndc-package", slug(package_ndc))


def hashed(graph, kind, record):
    """Deterministic IRI for a record that has no natural key (drug shortages,
    complete response letters, historical documents): SHA-1 of the record's
    canonical JSON. Same record, same IRI, on every rebuild."""
    import hashlib
    import json
    h = hashlib.sha1(json.dumps(record, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=True, default=str).encode()).hexdigest()
    return _inst(graph, kind, h[:20])


# ---- fda-food-cosmetic-kg, fda-animal-health-kg, fda-tobacco-kg ----------
def caers_report(report_number):
    """CAERS adverse event report (food, dietary supplement).
    caers_report('102855') -> .../fda-food-cosmetic-kg/id/caers-report/102855"""
    return _inst("fda-food-cosmetic-kg", "caers-report", slug(report_number))


def cosmetic_event(report_number):
    """Cosmetic adverse event report. cosmetic_event('24502668') -> .../cosmetic-event/24502668"""
    return _inst("fda-food-cosmetic-kg", "cosmetic-event", slug(report_number))


def animal_event(unique_aer_id):
    """Animal adverse event report, keyed on unique_aer_id_number.
    animal_event('USA-USFDACVM-2015-US-048928') -> .../animal-event/usa_usfdacvm_2015_us_048928"""
    return _inst("fda-animal-health-kg", "animal-event", slug(unique_aer_id))


def tobacco_problem(report_id):
    """Tobacco product problem report. tobacco_problem(307) -> .../tobacco-problem/307"""
    return _inst("fda-tobacco-kg", "tobacco-problem", slug(report_id))


def _selftest():
    S = "https://bmedesign.org/fda-substance-kg/id/"
    C = "https://bmedesign.org/fda-compliance-kg/id/"
    D = "https://bmedesign.org/fda-drug-biologic-kg/id/"
    cases = {
        substance("S8B49CX5KM"): S + "unii/s8b49cx5km",
        recall("D-0862-2026"): C + "recall/d_0862_2026",
        recall("H-1393-2026"): C + "recall/h_1393_2026",
        recall_event("99712"): C + "recall-event/99712",
        recall_by_event("99892", 1): C + "recall/event_99892_1",
        recalling_firm("Kwok Shing, Inc."): C + "recalling-firm/kwok_shing_inc",
        firm("3001234567"): C + "firm/3001234567",
        gsrs_substance("c088fcc5-2fe2-4aa6-8524-cb7aa8aa4a02"):
            S + "gsrs/c088fcc5-2fe2-4aa6-8524-cb7aa8aa4a02",
        substance_ref("174R2IG4T0", "c088fcc5"): S + "unii/174r2ig4t0",
        substance_ref(None, "c088fcc5"): S + "gsrs/c088fcc5",
        child(substance("174R2IG4T0"), "codes", "fceb859d-ac96"):
            S + "unii/174r2ig4t0/codes/fceb859d-ac96",
        application("NDA021234"): D + "application/nda021234",
        application("ANDA 076803"): D + "application/anda076803",
        application("020512", "A"): D + "application/anda020512",
        application("BLA125057"): D + "application/bla125057",
        application_product("020512", "001", "A"): D + "application/anda020512/product/001",
        application_untyped("415"): D + "application/000415",
        ndc_product("71558-001_43046e5b-e40b"): D + "ndc-product/71558-001_43046e5b-e40b",
        ndc_package("71558-001-30"): D + "ndc-package/71558_001_30",
        caers_report("102855"): "https://bmedesign.org/fda-food-cosmetic-kg/id/caers-report/102855",
        cosmetic_event("24502668"): "https://bmedesign.org/fda-food-cosmetic-kg/id/cosmetic-event/24502668",
        animal_event("USA-USFDACVM-2015-US-048928"):
            "https://bmedesign.org/fda-animal-health-kg/id/animal-event/usa_usfdacvm_2015_us_048928",
        tobacco_problem(307): "https://bmedesign.org/fda-tobacco-kg/id/tobacco-problem/307",
    }
    assert normalize_application("nda 21234") == "NDA021234"
    assert normalize_application("BL 125522") == "BLA125522"
    assert normalize_application("NDA 210933/Original 1") == "NDA210933"
    assert normalize_application("NDA 21234/S-012") == "NDA021234"
    assert normalize_application("citation 21 CFR 331") is None
    h1 = hashed("fda-drug-biologic-kg", "shortage", {"a": 1, "b": [2, 3]})
    assert h1 == hashed("fda-drug-biologic-kg", "shortage", {"b": [2, 3], "a": 1})
    assert h1.startswith(D + "shortage/") and len(h1.rsplit("/", 1)[1]) == 20
    for got, want in cases.items():
        assert got == want, f"MINT DRIFT: {got} != {want}"
    assert term("fda-compliance-kg", "Recall") == \
        "https://bmedesign.org/fda-compliance-kg/ns/Recall"
    assert substance(" s8b49cx5km ") == substance("S8B49CX5KM")
    for bad in ("", "  ", None, "!!!"):
        try:
            recall(bad)
        except ValueError:
            continue
        raise AssertionError(f"recall({bad!r}) should raise")
    print(f"fda_iri.py self-test PASSED ({len(cases)} minters).")


if __name__ == "__main__":
    _selftest()
