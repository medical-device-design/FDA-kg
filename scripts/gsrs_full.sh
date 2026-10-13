#!/usr/bin/env bash
# Full GSRS L1 build (167,385 substances); start it under nohup on the build VM.
# Writes out/fda-substance-kg/gsrs_substance.ttl, then validates it with riot.
set -euo pipefail
R=/srv/fda-products-kg
P=$R/repo/pipeline
RIOT=$R/tools/apache-jena-5.2.0/bin/riot
SNAP=$R/raw/fda-substance-kg/openfda-other-substance/2026-10-12
OUT=$R/out/fda-substance-kg/gsrs_substance.ttl

free_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
(( free_gb >= 10 )) || { echo "STOP: only ${free_gb} GB free"; exit 1; }

cd "$P"
python3 fda_iri.py
/usr/bin/time -f "convert time %es  peakRAM %MKB" python3 l1_gsrs.py "$SNAP" "$OUT"
ls -la "$OUT"
/usr/bin/time -f "riot time %es  peakRAM %MKB" "$RIOT" --validate --count "$OUT" 2>&1 | tail -3
echo "DONE gsrs full"
df -h / | tail -1
