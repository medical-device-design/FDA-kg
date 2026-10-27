#!/usr/bin/env bash
# L1 for the phase-3 openFDA sets: drug/label (SPL) into fda-drug-biologic-kg and drug/event (FAERS)
# into its own graph fda-drug-event-kg, built with --publish (MedDRA PT text stripped). Both written
# gzipped; riot validates each, then chunked full-coverage SHACL. Outputs only; raw/ untouched.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/phase3
export TMPDIR=$R/work; mkdir -p $W $O/fda-drug-event-kg
latest() { ls -d "$1"/20* | sort | tail -1; }
cd "$P"; python3 fda_iri.py >/dev/null || exit 1; python3 gen_shapes.py $R/repo/shapes >/dev/null
check='JVM_ARGS=-Xmx8g '"$J"'/shacl validate --shapes '"$R"'/repo/shapes/GRAPH.shapes.ttl --data {} 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "'
echo "=== drug/label -> fda-drug-biologic-kg"
python3 l1_openfda_any.py drug/label "$(latest $R/raw/fda-drug-biologic-kg/openfda-drug-label)" $O/fda-drug-biologic-kg/drug_label.ttl.gz
"$J/riot" --validate --count $O/fda-drug-biologic-kg/drug_label.ttl.gz 2>&1 | tail -1
python3 $P/chunk_ttl.py $O/fda-drug-biologic-kg/drug_label.ttl.gz $W 200000 "${check//GRAPH/fda-drug-biologic-kg}" | tail -1
echo "=== drug/event -> fda-drug-event-kg (publish mode)"
python3 l1_openfda_any.py drug/event "$(latest $R/raw/fda-drug-event-kg/openfda-drug-event)" $O/fda-drug-event-kg/drug_event.ttl.gz --publish
"$J/riot" --validate --count $O/fda-drug-event-kg/drug_event.ttl.gz 2>&1 | tail -1
python3 $P/chunk_ttl.py $O/fda-drug-event-kg/drug_event.ttl.gz $W 400000 "${check//GRAPH/fda-drug-event-kg}" | tail -1
echo "=== no MedDRA PT text in the published FAERS file (must be 0)"
zcat $O/fda-drug-event-kg/drug_event.ttl.gz | grep -c "ex:reactionmeddrapt " || true
rm -rf $W; du -sh $O/fda-drug-biologic-kg/drug_label.ttl.gz $O/fda-drug-event-kg; df -h / | tail -1; echo "DONE build_phase3"
