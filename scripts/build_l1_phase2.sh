#!/usr/bin/env bash
# L1 build for every phase-2 openFDA endpoint (VM copy: all fields, no licence filter).
# Each output is riot-validated. Stops if free disk drops under 6 GB. Start under nohup.
set -uo pipefail
R=/srv/fda-products-kg
P=$R/repo/pipeline
RIOT=$R/tools/apache-jena-5.2.0/bin/riot
cd "$P"
python3 fda_iri.py && python3 mapper.py || exit 1

# graph|product/endpoint|output name   (animal events last: 159 partitions)
JOBS=(
  "fda-drug-biologic-kg|drug/drugsfda|drugsfda"
  "fda-drug-biologic-kg|drug/ndc|ndc"
  "fda-drug-biologic-kg|drug/orangebook|orangebook"
  "fda-drug-biologic-kg|drug/shortages|shortages"
  "fda-drug-biologic-kg|transparency/crl|crl"
  "fda-drug-biologic-kg|other/nsde|nsde"
  "fda-food-cosmetic-kg|food/event|caers"
  "fda-food-cosmetic-kg|cosmetic/event|cosmetic_event"
  "fda-tobacco-kg|tobacco/problem|tobacco_problem"
  "fda-tobacco-kg|research/tobaccodigitalads|tobacco_digital_ads"
  "fda-tobacco-kg|research/tobaccoharmmenthol|tobacco_harm_menthol"
  "fda-tobacco-kg|research/tobaccopreventionads|tobacco_prevention_ads"
  "fda-tobacco-kg|research/tobaccosmokefree|tobacco_smokefree"
  "fda-compliance-kg|other/historicaldocument|historical_document"
  "fda-animal-health-kg|animalandveterinary/event|animal_event"
)
fail=0
for job in "${JOBS[@]}"; do
  IFS='|' read -r graph ep name <<<"$job"
  snap=$(ls -d $R/raw/$graph/openfda-${ep/\//-}/*/ | sort | tail -1)
  out=$R/out/$graph/$name.ttl
  free_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9')
  (( free_gb >= 6 )) || { echo "STOP before $ep: ${free_gb} GB free"; exit 1; }
  echo "=== $ep  (snapshot $(basename "$snap"))"
  /usr/bin/time -f "   time %es  peakRAM %MKB" python3 l1_openfda_any.py "$ep" "$snap" "$out" \
    || { echo "FAILED $ep"; fail=1; continue; }
  "$RIOT" --validate --count "$out" 2>&1 | tail -1 || { echo "RIOT FAILED $out"; fail=1; }
  ls -la "$out" | awk '{print "   size", $5}'
done
echo "DONE phase 2 L1 build (fail=$fail)"
du -sh $R/out/*; df -h / | tail -1
