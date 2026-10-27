#!/usr/bin/env python3
"""
l1_openfda_any.py -- one L1 converter for every openFDA endpoint, driven by a config
table (ENDPOINTS below). Streams partitions with ijson, so memory is flat.

Per endpoint the config says: target graph, class name, how to mint the record's
IRI (natural key, or a hash when the source has none), which fields are dates,
and which values link OUT to other graphs (UNII -> fda-substance-kg, application
number -> drug graph, package NDC -> shared package node). Everything else is the
generic mapping in mapper.py: every field kept, nested objects as child nodes.

Licensed text (MedDRA, VeDDRA terms) stays in the VM copy. With --publish those
fields are removed, so nothing licensed can reach lakeFS before the licence
decision (handoff section 3).

Usage:
  python3 l1_openfda_any.py <product/endpoint> <snapshot_dir> <out.ttl> [--publish] [--limit N]
"""
import gzip
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import quote

import ijson

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common      # noqa: E402
import fda_iri     # noqa: E402
import mapper      # noqa: E402

D, F, A, T, C = ("fda-drug-biologic-kg", "fda-food-cosmetic-kg",
                 "fda-animal-health-kg", "fda-tobacco-kg", "fda-compliance-kg")
E = "fda-drug-event-kg"


def _first(rec, key):
    v = rec.get(key)
    return v[0] if isinstance(v, list) and v else v


def _by_hash(graph, kind):
    return lambda r: fda_iri.hashed(graph, kind, r)


def _openfda_links(rec):
    """Links from openFDA's harmonized block: UNII -> substance, application -> drug."""
    pairs = []
    ofda = rec.get("openfda") or {}
    for u in common.as_list(ofda.get("unii")):
        try:
            pairs.append(("ex:hasSubstance", f"<{fda_iri.substance(u)}>"))
        except ValueError:
            pass
    for a in common.as_list(ofda.get("application_number")):
        try:
            pairs.append(("ex:hasApplication", f"<{fda_iri.application(a)}>"))
        except ValueError:
            pass
    for n in common.as_list(ofda.get("package_ndc")):
        try:
            pairs.append(("ex:hasPackageNdc", f"<{fda_iri.ndc_package(n)}>"))
        except ValueError:
            pass
    return pairs


def _faers_links(rec):
    """FAERS reports: the harmonized openfda block sits inside each patient.drug item;
    lift its UNIIs and application numbers to report-level links (deduplicated)."""
    pairs, seen = [], set()
    for d in (rec.get("patient") or {}).get("drug") or []:
        if isinstance(d, dict):
            for pr in _openfda_links(d):
                if pr not in seen:
                    seen.add(pr)
                    pairs.append(pr)
    return pairs


def _app_link(value, app_type=None):
    """One hasApplication link per application number; value may be a list (CRLs)."""
    pairs = []
    for v in common.as_list(value) if isinstance(value, list) else [value]:
        try:
            pairs.append(("ex:hasApplication", f"<{fda_iri.application(v, app_type)}>"))
        except ValueError:
            pass
    return pairs


def _drugsfda_child(key, item):
    """Drugs@FDA products and submissions get the SAME IRIs the Drugs@FDA data
    files use, so the openFDA and data-file views of one submission merge."""
    a = item.get("_appl")
    try:
        if key == "products" and a and item.get("product_number"):
            return fda_iri.application_product(a, item["product_number"])
        if key == "submissions" and a and item.get("submission_type") and item.get("submission_number"):
            return (fda_iri.application(a) + "/submission/"
                    + f'{fda_iri.slug(item["submission_type"])}-{fda_iri.slug(item["submission_number"])}')
    except ValueError:
        return None
    return None


def _package_child(key, item):
    """NDC Directory 'packaging' entries are the shared package-NDC nodes."""
    if key == "packaging" and item.get("package_ndc"):
        try:
            return fda_iri.ndc_package(item["package_ndc"])
        except ValueError:
            return None
    return None


def _strip(rec, *paths):
    """Remove licensed fields in place. A path is ('reactions',) for a top-level key,
    ('reaction', 'veddra_term_name') for a key inside each list item, or any deeper
    path such as ('patient', 'reaction', 'reactionmeddrapt'); lists along the way
    are walked item by item."""
    def walk(node, path):
        if not isinstance(node, dict):
            return
        if len(path) == 1:
            node.pop(path[0], None)
            return
        child = node.get(path[0])
        for item in (child if isinstance(child, list) else [child]):
            walk(item, path[1:])
    for path in paths:
        walk(rec, path)


ENDPOINTS = {
    "drug/drugsfda": dict(
        graph=D, cls="DrugApplication", prefix="DrugsFda",
        iri=lambda r: fda_iri.application(r["application_number"]),
        label=lambda r: f'{r["application_number"]} {r.get("sponsor_name", "")}'.strip(),
        rec_id=lambda r: r["application_number"],
        dates={"submission_status_date"},
        links=_openfda_links,
        child_iri=_drugsfda_child,
        pre=lambda r: [p.__setitem__("_appl", r["application_number"])
                       for p in (r.get("products") or []) + (r.get("submissions") or [])],
    ),
    "drug/ndc": dict(
        graph=D, cls="NdcProduct", prefix="Ndc",
        iri=lambda r: fda_iri.ndc_product(r["product_id"]),
        label=lambda r: f'{r.get("brand_name") or r.get("generic_name") or ""} {r["product_ndc"]}'.strip(),
        rec_id=lambda r: r["product_id"],
        dates={"marketing_start_date", "marketing_end_date", "listing_expiration_date"},
        links=lambda r: _openfda_links(r) + _app_link(r.get("application_number")),
        child_iri=_package_child,
    ),
    "drug/orangebook": dict(
        graph=D, cls="OrangeBookProduct", prefix="OrangeBook",
        iri=lambda r: fda_iri.application_product(
            _first(r, "products")["application_number"], r["product_number"],
            _first(r, "products").get("application_type")),
        label=lambda r: f'{_first(r, "products").get("brand_name", "")} ({_first(r, "products").get("application_number")} {r["product_number"]})',
        rec_id=lambda r: f'{_first(r, "products")["application_number"]}:{r["product_number"]}',
        dates={"approval_date", "patent_expire_date", "exclusivity_date", "submission_date"},
        links=lambda r: _app_link(_first(r, "products")["application_number"],
                                  _first(r, "products").get("application_type")),
    ),
    "drug/shortages": dict(
        graph=D, cls="DrugShortage", prefix="Shortage",
        iri=_by_hash(D, "shortage"),
        label=lambda r: f'{r.get("generic_name", "")} {r.get("package_ndc", "")} ({r.get("status", "")})'.strip(),
        rec_id=lambda r: f'{r.get("package_ndc")}:{r.get("initial_posting_date")}:{r.get("update_date")}',
        dates={"initial_posting_date", "update_date", "discontinued_date", "change_date"},
        links=lambda r: _openfda_links(r) + (
            [("ex:hasPackageNdc", f"<{fda_iri.ndc_package(r['package_ndc'])}>")]
            if r.get("package_ndc") else []),
    ),
    "transparency/crl": dict(
        graph=D, cls="CompleteResponseLetter", prefix="Crl",
        iri=_by_hash(D, "crl"),
        label=lambda r: f'{r.get("application_number", "")} {r.get("letter_date", "")} {r.get("company_name", "")}'.strip(),
        rec_id=lambda r: r.get("file_name"),
        dates={"letter_date"},
        links=lambda r: _app_link(r.get("application_number")),
    ),
    "other/nsde": dict(
        graph=D, cls="NdcPackage", prefix="Nsde",
        iri=lambda r: fda_iri.ndc_package(r["package_ndc"]),
        label=lambda r: f'{r.get("proprietary_name", "")} {r["package_ndc"]}'.strip(),
        rec_id=lambda r: r["package_ndc"],
        dates={"marketing_start_date", "marketing_end_date", "inactivation_date", "reactivation_date"},
        links=lambda r: _app_link(r.get("application_number_or_citation")),
    ),
    "drug/label": dict(
        # SPL labels as openFDA publishes them (one record per label set, latest version);
        # every text section is kept, tables included
        graph=D, cls="DrugLabel", prefix="Label",
        iri=lambda r: fda_iri.drug_label(r["set_id"]),
        label=lambda r: f'{(_first(r.get("openfda") or {}, "brand_name") or _first(r.get("openfda") or {}, "generic_name") or "label")} ({r["set_id"]})',
        rec_id=lambda r: r["set_id"],
        dates={"effective_time"},
        links=_openfda_links,
    ),
    "drug/event": dict(
        # FAERS reports, own graph (fda-drug-event-kg). Reporter identity is not in openFDA;
        # patient block is age, sex, weight and the drug and reaction lists
        graph=E, cls="AdverseEventReport", prefix="Faers",
        iri=lambda r: fda_iri.drug_event_report(r["safetyreportid"]),
        label=lambda r: f'FAERS report {r["safetyreportid"]}',
        rec_id=lambda r: str(r["safetyreportid"]),
        dates={"receivedate", "receiptdate", "transmissiondate", "drugstartdate", "drugenddate", "patientdeathdate"},
        links=_faers_links,
        licensed=lambda r: _strip(r, ("patient", "reaction", "reactionmeddrapt")),   # MedDRA PT text; codes and outcome kept
    ),
    "food/event": dict(
        graph=F, cls="CaersReport", prefix="Caers",
        iri=lambda r: fda_iri.caers_report(r["report_number"]),
        label=lambda r: f'CAERS report {r["report_number"]}',
        rec_id=lambda r: r["report_number"],
        dates={"date_created", "date_started"},
        links=lambda r: [],
        licensed=lambda r: _strip(r, ("reactions",)),          # MedDRA PT strings
    ),
    "cosmetic/event": dict(
        graph=F, cls="CosmeticEvent", prefix="Cosmetic",
        iri=lambda r: fda_iri.cosmetic_event(r["report_number"]),
        label=lambda r: f'cosmetic event report {r["report_number"]}',
        rec_id=lambda r: r["report_number"],
        dates={"initial_received_date", "latest_received_date", "event_date"},
        links=lambda r: [],
        licensed=lambda r: _strip(r, ("reactions",)),          # MedDRA PT strings
    ),
    "animalandveterinary/event": dict(
        graph=A, cls="AnimalEvent", prefix="AnimalEvent",
        iri=lambda r: fda_iri.animal_event(r["unique_aer_id_number"]),
        label=lambda r: f'animal adverse event {r["unique_aer_id_number"]}',
        rec_id=lambda r: r["unique_aer_id_number"],
        dates={"original_receive_date", "onset_date"},
        links=lambda r: [],
        licensed=lambda r: _strip(r, ("reaction", "veddra_term_name")),  # VeDDRA text, codes kept
    ),
    "tobacco/problem": dict(
        graph=T, cls="TobaccoProblemReport", prefix="Tobacco",
        iri=lambda r: fda_iri.tobacco_problem(r["report_id"]),
        label=lambda r: f'tobacco problem report {r["report_id"]}',
        rec_id=lambda r: str(r["report_id"]),
        dates={"date_submitted"},
        links=lambda r: [],
    ),
    "research/tobaccodigitalads": dict(
        graph=T, cls="TobaccoDigitalAdStudyRow", prefix="TobaccoAds",
        iri=_by_hash(T, "tobacco-digital-ad"), label=lambda r: f'{r.get("ad_number", "")} {r.get("channel_or_format", "")}'.strip(),
        rec_id=lambda r: r.get("ad_number"), dates=set(), links=lambda r: []),
    "research/tobaccoharmmenthol": dict(
        graph=T, cls="TobaccoHarmPerceptionRecord", prefix="TobaccoHarm",
        iri=lambda r: fda_iri._inst(T, "tobacco-harm-record", fda_iri.slug(r["record"])),
        label=lambda r: f'harm perception record {r["record"]}',
        rec_id=lambda r: str(r["record"]), dates=set(), links=lambda r: []),
    "research/tobaccopreventionads": dict(
        graph=T, cls="TobaccoPreventionAdStudy", prefix="TobaccoPrevention",
        iri=lambda r: fda_iri._inst(T, "tobacco-prevention-ad", fda_iri.slug(f'{r.get("study_name")} {r["ad_number"]}')),
        label=lambda r: f'{r.get("study_name", "")} {r["ad_number"]}'.strip(),
        rec_id=lambda r: r["ad_number"], dates=set(), links=lambda r: []),
    "research/tobaccosmokefree": dict(
        graph=T, cls="SmokefreeMetric", prefix="Smokefree",
        iri=lambda r: fda_iri._inst(T, "smokefree-metric", fda_iri.slug(r["variable"])),
        label=lambda r: r["variable"], rec_id=lambda r: r["variable"], dates=set(), links=lambda r: []),
    "other/historicaldocument": dict(
        graph=C, cls="HistoricalDocument", prefix="HistDoc",
        iri=_by_hash(C, "historical-document"),
        label=lambda r: f'{r.get("doc_type", "")} {r.get("year", "")}'.strip(),
        rec_id=lambda r: f'{r.get("doc_type")}:{r.get("year")}',
        dates=set(), links=lambda r: []),
}

SOURCE_URL = "https://api.fda.gov/{ep}.json?search={field}:%22{val}%22"
SEARCH_FIELD = {"drug/drugsfda": "application_number", "drug/ndc": "product_id",
                "drug/label": "set_id", "drug/event": "safetyreportid",
                "other/nsde": "package_ndc", "food/event": "report_number",
                "cosmetic/event": "report_number", "tobacco/problem": "report_id",
                "animalandveterinary/event": "unique_aer_id_number"}


def convert(endpoint, snapshot_dir, out_path, publish=False, limit=None):
    cfg = ENDPOINTS[endpoint]
    snap = Path(snapshot_dir)
    stamp = snap.name
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stamp):
        raise SystemExit("snapshot folder must be named YYYY-MM-DD")
    zips = sorted(snap.glob("*.json.zip"))
    if not zips:
        raise SystemExit(f"no partition zips in {snap}")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = skipped = seen_dup = 0
    seen = set()
    opener = (lambda p: gzip.open(p, "wt", encoding="utf-8", newline="\n", compresslevel=6)) \
        if str(out_path).endswith(".gz") else \
        (lambda p: open(p, "w", encoding="utf-8", newline="\n", buffering=1 << 20))
    with opener(out_path) as out:                       # .ttl.gz output when asked
        out.write(common.prefixes({"ex": fda_iri.ns(cfg["graph"])}) + "\n")
        m = mapper.Mapper(out, class_prefix=cfg["prefix"], date_fields=cfg["dates"],
                          child_iri=cfg.get("child_iri"))
        for z in zips:
            with zipfile.ZipFile(z) as zf:
                for name in sorted(zf.namelist()):
                    with zf.open(name) as fh:
                        for rec in ijson.items(fh, "results.item"):
                            if publish and cfg.get("licensed"):
                                cfg["licensed"](rec)
                            if cfg.get("pre"):
                                cfg["pre"](rec)
                            try:
                                iri = cfg["iri"](rec)
                                rec_id = cfg["rec_id"](rec)
                            except (KeyError, ValueError, TypeError):
                                skipped += 1
                                continue
                            if iri in seen:          # same key twice in one source
                                seen_dup += 1
                            seen.add(iri)
                            extra = [("rdfs:label", common.lit(cfg["label"](rec)))]
                            extra += cfg["links"](rec)
                            field = SEARCH_FIELD.get(endpoint)
                            url = (SOURCE_URL.format(ep=endpoint, field=field, val=quote(str(rec_id)))
                                   if field and rec_id else f"https://api.fda.gov/{endpoint}.json")
                            extra += common.provenance(endpoint, rec_id, source_url=url,
                                                       retrieved_at=stamp)
                            m.map_obj(iri, {k: v for k, v in rec.items() if not k.startswith("_")},
                                      cls=cfg["cls"], extra=extra, top=True)
                            n += 1
                            if limit and n >= limit:
                                break
    print(f"{endpoint} -> {out_path.name}: {n} records, {m.nodes} nodes, {m.triples} triples, "
          f"{skipped} skipped (no key), {seen_dup} duplicate keys, publish={publish}")
    return n, m.triples


if __name__ == "__main__":
    if len(sys.argv) < 4 or sys.argv[1] not in ENDPOINTS:
        raise SystemExit(__doc__ + "\nendpoints: " + ", ".join(ENDPOINTS))
    lim = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
    convert(sys.argv[1], sys.argv[2], sys.argv[3], publish="--publish" in sys.argv, limit=lim)
