#!/usr/bin/env bash
# Gap queries, November 9, 2026 (VM only): VAERS v2, import alerts v2, cross queries x3/x7 as rewritten.
# Fresh TDB2 store tdb2_gaps with four named graphs. Never uploads, never touches lakeFS.
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2_gaps; O=$R/out
W=$R/work/gaps; Q=$R/repo/queries; P=https://purl.org/okn/frink/kg
export JVM_ARGS=-Xmx4g TMPDIR=$R/work
mkdir -p $W/q
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
avail_gb() { awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }
free_gb() { df --output=avail -BG / | tail -1 | tr -dc 0-9; }
log "== wait: no device loader and >= 9 GB RAM available (now $(avail_gb) GB), disk $(free_gb) GB free"
while pgrep -f 'medical-device-kg.*xloader' >/dev/null || [ "$(avail_gb)" -lt 9 ]; do sleep 60; done
[ "$(free_gb)" -gt 230 ] || { log "under 230 GB free, stop (store needs ~115 GB, 100 GB reserved)"; exit 1; }
[ -d $DB ] && { log "$DB exists, stop"; exit 1; }
load() { local g=$1; shift; log "-- load $g ($# files), free $(free_gb) GB"
  [ "$(free_gb)" -gt 120 ] || { log "under 120 GB free, stop before loading $g"; exit 1; }
  "$J/tdb2.tdbloader" --loc $DB --graph $P/$g "$@" 2>&1 | grep -E "Finished|Error|Exception" | tail -2; }
log "== 1. load"
load fda-drug-event-kg $O/fda-drug-event-kg/vaers_v2.ttl.gz $O/fda-drug-event-kg/l2_term_text_vaers_v2.ttl.gz
load fda-compliance-kg $(ls $O/fda-compliance-kg/*.ttl | grep -v '/import_alerts.ttl$')
load fda-substance-kg $O/fda-substance-kg/gsrs_substance.ttl $O/fda-substance-kg/unii.ttl $O/fda-substance-kg/l2_stubs.ttl
load fda-food-cosmetic-kg $O/fda-food-cosmetic-kg/*.ttl $O/fda-food-cosmetic-kg/l2_term_text_*.ttl.gz
log "db $(du -sh $DB | cut -f1), free $(free_gb) GB"
log "== 2. queries"
OUT=$W/gap_results_2026-11-09.md
{ echo "# Gap query results, $(date '+%B %d, %Y %H:%M'), store $(du -sh $DB | cut -f1)"; echo; echo "| query | rows | time | status |"; echo "|---|---|---|---|"; } > $OUT
body=$W/body.md; : > $body
run() {
  local t0=$(date +%s)
  "$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --query "$2" > $W/q/$1.txt 2> $W/q/$1.err; local rc=$? t=$(( $(date +%s) - t0 ))
  local rows=$(grep -cE '^\| ' $W/q/$1.txt); rows=$(( rows > 0 ? rows - 1 : 0 ))
  printf "| %s | %s | %s s | %s |\n" "$1" "$rows" "$t" "$([ $rc -eq 0 ] && echo ok || echo "rc $rc: $(head -c 120 $W/q/$1.err)")" >> $OUT
  { echo; echo "## $1 ($rows rows, $t s)"; echo '```'; head -45 $W/q/$1.txt | cut -c1-230; echo '```'; } >> $body
}
for q in $W/qs/*.rq; do run "$(basename $q .rq)" $q; done
for q in $Q/fda-drug-event-kg/q7_*.rq $Q/fda-drug-event-kg/q8_*.rq $Q/fda-drug-event-kg/q9_*.rq $Q/fda-drug-event-kg/q10_*.rq; do run "$(basename $q .rq)" "$q"; done
cat $body >> $OUT; rm -f $body
log "== 3. raw checks"
# raw_checks.py is scripts/gaps_raw_checks.py in this repo
python3 $W/raw_checks.py $R >> $OUT 2>&1
du -sh $DB; df -h / | tail -1
log "DONE gaps -> $OUT"
