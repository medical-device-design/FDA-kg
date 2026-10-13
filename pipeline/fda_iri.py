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


def _selftest():
    S = "https://bmedesign.org/fda-substance-kg/id/"
    C = "https://bmedesign.org/fda-compliance-kg/id/"
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
    }
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
