#!/usr/bin/env bash
# Validation of the FAERS files in fda-drug-event-kg (18 billion triples, two gzipped files): riot on
# part 2 (part 1 passed on October 28), a full grep that no MedDRA PT text (ex:reactionmeddrapt) is
# present, the streaming full-coverage check of both files against the generated rules
# (stream_check.py), and Jena SHACL on every 200th chunk of 100,000 blocks of each file (--every),
# so Jena and the streaming check can be compared on the same data. On the VM this lives at
# repo/validate_faers.sh. Outputs only; nothing is changed.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out/fda-drug-event-kg; W=$R/work/faers
export TMPDIR=$R/work; mkdir -p $W
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
echo "=== riot part 2 $(date -Is)"; "$J/riot" --validate --count $O/drug_event_part2.ttl.gz 2>&1 | tail -1
echo "=== MedDRA term text, lines per file (must be 0) $(date -Is)"
for f in drug_event.ttl.gz drug_event_part2.ttl.gz; do echo -n "$f: "; zcat $O/$f | grep -c 'ex:reactionmeddrapt'; done
echo "=== streaming full-coverage check $(date -Is)"
python3 $P/stream_check.py fda-drug-event-kg $O/drug_event.ttl.gz $O/drug_event_part2.ttl.gz
echo "=== Jena SHACL, every 200th chunk of 100,000 blocks $(date -Is)"
check='JVM_ARGS=-Xmx8g '"$J"'/shacl validate --shapes '"$R"'/repo/shapes/fda-drug-event-kg.shapes.ttl --data {} 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "'
for f in drug_event.ttl.gz drug_event_part2.ttl.gz; do echo "--- $f"; python3 $P/chunk_ttl.py $O/$f $W 100000 "$check" --every 200 | tail -1; done
rm -rf $W; echo "DONE validate_faers $(date -Is)"
