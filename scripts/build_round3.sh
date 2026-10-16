#!/usr/bin/env bash
# L1 for the round-3 sources (after fetch_l0_round3.sh): NDI notifications, recall
# announcements, tobacco products, Animal Drugs @ FDA. riot and SHACL on each new file.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/round3
export TMPDIR=$R/work; mkdir -p $W
latest() { ls -d "$1"/20* | sort | tail -1; }
cd "$P"; python3 fda_iri.py >/dev/null && python3 mapper.py >/dev/null || exit 1
python3 gen_shapes.py $R/repo/shapes >/dev/null
run() {  # source  snapshot  out  graph
  echo "=== $1"
  python3 l1_misc.py "$1" "$2" "$3" || { echo "FAILED $1"; return; }
  "$J/riot" --validate --count "$3" 2>&1 | tail -1
  JVM_ARGS=-Xmx6g $J/shacl validate --shapes $R/repo/shapes/$4.shapes.ttl --data "$3" > $W/rep.ttl 2>$W/err
  echo "   shapes: $(grep -oE 'sh:conforms +(true|false)' $W/rep.ttl | head -1)  violations: $(grep -c sh:ValidationResult $W/rep.ttl)"
  grep -oE 'sh:resultPath +[^ ;]+' $W/rep.ttl | sort | uniq -c | sort -rn | head -4; head -2 $W/err
}
run ndi                  "$(latest $R/raw/fda-food-cosmetic-kg/fda-ndi-notifications)"      $O/fda-food-cosmetic-kg/ndi_notifications.ttl  fda-food-cosmetic-kg
run recall-announcements "$(latest $R/raw/fda-compliance-kg/fda-recall-announcements)"       $O/fda-compliance-kg/recall_announcements.ttl  fda-compliance-kg
run tobacco-products     "$(latest $R/raw/fda-tobacco-kg/fda-tobacco-products-database)"     $O/fda-tobacco-kg/tobacco_products.ttl         fda-tobacco-kg
run adafda               "$(latest $R/raw/fda-animal-health-kg/fda-animal-drugs-at-fda)"     $O/fda-animal-health-kg/animal_drugs_at_fda.ttl fda-animal-health-kg
echo "=== recall announcements: firm links that resolve to existing firm nodes"
grep -oE 'ex:hasRecallingFirm <[^>]+>' $O/fda-compliance-kg/recall_announcements.ttl | grep -oE '<[^>]+>' | sort -u > $W/refs
cat $O/fda-compliance-kg/*.ttl | grep -oE '^<[^>]+>$' | sort -u > $W/subj
echo "   refs=$(wc -l < $W/refs) exist=$(comm -12 $W/refs $W/subj | wc -l)"
echo "=== tobacco products: distinct STNs (marketing orders join on company + product name at L2)"
grep -oE 'ex:stn "[^"]+"' $O/fda-tobacco-kg/tobacco_products.ttl | sort -u | wc -l
rm -rf $W; df -h / | tail -1; echo "DONE build_round3"
