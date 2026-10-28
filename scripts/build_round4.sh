#!/usr/bin/env bash
# L1 for the round-4 sources (l1_round4.py), one TTL per source under out/<graph>/, riot validation and
# SHACL on every file (chunked for the NDC companion files). Memory is kept small on purpose: the
# FAERS conversion may be running on the same VM. Outputs only; raw/ untouched.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/round4
export TMPDIR=$R/work; mkdir -p $W
D=${1:-$(ls -d $R/raw/fda-drug-biologic-kg/fda-drug-master-files/20* | sort | tail -1 | xargs basename)}
B=fda-drug-biologic-kg; C=fda-compliance-kg; F=fda-food-cosmetic-kg
cd "$P"; python3 fda_iri.py >/dev/null || exit 1; python3 gen_shapes.py $R/repo/shapes >/dev/null
shacl() { JVM_ARGS=-Xmx3g "$J/shacl" validate --shapes $R/repo/shapes/$1.shapes.ttl --data $2 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "; }
one() { # source graph raw-folder outname
  echo "=== $1 -> $2/$4"
  python3 l1_round4.py $1 $R/raw/$2/$3/$D $O/$2/$4 || { echo "FAILED $1"; return; }
  "$J/riot" --validate --count $O/$2/$4 2>&1 | tail -1
  if [ "$1" = ndc-extra ]; then
    check='JVM_ARGS=-Xmx3g '"$J"'/shacl validate --shapes '"$R"'/repo/shapes/'"$2"'.shapes.ttl --data {} 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "'
    python3 $P/chunk_ttl.py $O/$2/$4 $W 150000 "$check" | tail -1
  else
    shacl $2 $O/$2/$4
  fi
}
one iid              $B fda-inactive-ingredients                    inactive_ingredients.ttl
one dmf              $B fda-drug-master-files                       drug_master_files.ttl
one ndc-extra        $B fda-ndc-extra                               ndc_companion.ttl
one outsourcing      $B fda-outsourcing-facilities                  outsourcing_facilities.ttl
one vaccines         $B fda-licensed-vaccines                       licensed_vaccines.ttl
one cgt              $B fda-cellular-gene-therapy                   cgt_products.ttl
one debarment        $C fda-debarment-list                          debarment_list.ttl
one disqualification $C fda-clinical-investigator-disqualification  investigator_disqualifications.ttl
one tds              $F fda-total-diet-study                        total_diet_study.ttl
echo "=== 503B contact column never written (must be 0)"; grep -c "ex:contact " $O/$B/outsourcing_facilities.ttl || true
echo "=== record counts"; for f in $O/$B/inactive_ingredients.ttl $O/$B/drug_master_files.ttl $O/$B/ndc_companion.ttl $O/$B/outsourcing_facilities.ttl $O/$B/licensed_vaccines.ttl $O/$B/cgt_products.ttl $O/$C/debarment_list.ttl $O/$C/investigator_disqualifications.ttl $O/$F/total_diet_study.ttl; do printf "%-45s " "$(basename $f)"; grep -oE "^    a ex:[A-Za-z]+" $f | sort | uniq -c | tr '\n' ' '; echo; done
rm -rf $W; df -h / | tail -1; echo "DONE build_round4"
