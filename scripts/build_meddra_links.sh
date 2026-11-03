#!/usr/bin/env bash
# L2: MedDRA term text in the raw adverse event snapshots -> links to meddra-pt / meddra-llt IRIs
# (l2_meddra_terms.py). Small sources first (VAERS, CAERS, cosmetic), then FAERS with 4 workers.
# Outputs hold codes only (no term text); the *.report.txt / *.unmapped.tsv next to them list the
# strings that did not match. Until the MSSO answers, these files stay on the VM like meddra_*.ttl.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin
export TMPDIR=$R/work
REL=${1:-$(ls -d $R/raw/licensed/meddra/*/ | sort -V | tail -1)}; REL=${REL%/}
snap() { ls -d $R/raw/$1/$2/20* | sort | tail -1; }
run() {   # mode graph source-dir out-name [extra args]
  local mode=$1 g=$2 s=$3 o=$R/out/$2/$4; shift 4
  echo "=== $mode from $s ($(date +%H:%M))"
  python3 $P/l2_meddra_terms.py "$REL" $mode "$s" $o "$@" || { echo "FAILED $mode"; return 1; }
  chmod 640 $o $o.report.txt $o.unmapped.tsv
  "$J/riot" --validate --count $o 2>&1 | tail -1
  echo "linked nodes: $(zcat $o | grep -c '^<')"
}
run vaers    fda-drug-event-kg    "$(snap fda-drug-biologic-kg vaers)"                 l2_meddra_vaers.ttl.gz
run caers    fda-food-cosmetic-kg "$(snap fda-food-cosmetic-kg openfda-food-event)"     l2_meddra_caers.ttl.gz
run cosmetic fda-food-cosmetic-kg "$(snap fda-food-cosmetic-kg openfda-cosmetic-event)" l2_meddra_cosmetic.ttl.gz
run faers    fda-drug-event-kg    "$(snap fda-drug-event-kg openfda-drug-event)"        l2_meddra_faers.ttl.gz --workers 4
echo "DONE build_meddra_links ($(date +%H:%M))"
