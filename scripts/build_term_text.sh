#!/usr/bin/env bash
# L2 public term-text files (l2_term_text.py): the FDA-published reaction term text attached to the
# reaction, symptom-set and report nodes of the publish-mode L1 files. Small sources first, FAERS last.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin
export TMPDIR=$R/work
snap() { ls -d $R/raw/$1/$2/20* | sort | tail -1; }
run() { local mode=$1 g=$2 s=$3 o=$R/out/$2/$4; shift 4
  echo "=== $mode from $s ($(date +%H:%M))"
  python3 $P/l2_term_text.py $mode "$s" $o "$@" || { echo "FAILED $mode"; return 1; }
  "$J/riot" --validate --count $o 2>&1 | tail -1; ls -la $o; }
cd $P && python3 gen_shapes.py $R/repo/shapes >/dev/null
run vaers    fda-drug-event-kg    "$(snap fda-drug-biologic-kg vaers)"                 l2_term_text_vaers.ttl.gz
run caers    fda-food-cosmetic-kg "$(snap fda-food-cosmetic-kg openfda-food-event)"     l2_term_text_caers.ttl.gz
run cosmetic fda-food-cosmetic-kg "$(snap fda-food-cosmetic-kg openfda-cosmetic-event)" l2_term_text_cosmetic.ttl.gz
run faers    fda-drug-event-kg    "$(snap fda-drug-event-kg openfda-drug-event)"        l2_term_text_faers.ttl.gz --workers 4
echo "DONE build_term_text ($(date +%H:%M))"
