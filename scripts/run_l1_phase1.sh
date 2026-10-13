#!/usr/bin/env bash
# Phase 1 L1 build on the build VM: UNII, drug and food enforcement -> TTL,
# then a full parse with Jena riot. Writes only under /srv/fda-products-kg/out.
# Reads raw snapshots, never edits them. Copies (not edits) device common.py.
set -euo pipefail
R=/srv/fda-products-kg
P=$R/repo/pipeline
RIOT=$R/tools/apache-jena-5.2.0/bin/riot
STAMP=2026-10-12

cp -p /srv/medical-device-kg/repo/pipeline/common.py "$P/common.py"
cd "$P"
python3 common.py
python3 fda_iri.py

run() {  # kind snapshot out [product]
  /usr/bin/time -f "  time %es  peakRAM %MKB" python3 l1_openfda.py "$@"
}
run unii        $R/raw/fda-substance-kg/openfda-other-unii/$STAMP \
                $R/out/fda-substance-kg/unii.ttl
run enforcement $R/raw/fda-compliance-kg/openfda-drug-enforcement/$STAMP \
                $R/out/fda-compliance-kg/drug_enforcement.ttl drug
run enforcement $R/raw/fda-compliance-kg/openfda-food-enforcement/$STAMP \
                $R/out/fda-compliance-kg/food_enforcement.ttl food

echo "--- riot full parse (counts triples, fails on any syntax error) ---"
for f in $R/out/fda-substance-kg/unii.ttl $R/out/fda-compliance-kg/*_enforcement.ttl; do
  printf '%s: ' "$(basename "$f")"
  "$RIOT" --validate --count "$f" 2>&1 | tail -1
done
echo "--- sanity ---"
grep -c 'a ex:Recall ;' $R/out/fda-compliance-kg/drug_enforcement.ttl
grep -c 'ex:hasSubstance' $R/out/fda-compliance-kg/drug_enforcement.ttl || true
ls -la $R/out/fda-substance-kg $R/out/fda-compliance-kg
df -h / | tail -1
