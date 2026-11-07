#!/usr/bin/env bash
# VAERS query test (VM only): fresh TDB2 with vaers.ttl.gz + l2_term_text_vaers.ttl.gz as the
# fda-drug-event-kg named graph, the four VAERS queries, class counts, and a check of reports per
# receive year against the raw VAERS CSV row counts. Never deletes, uploads or touches lakeFS.
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2_vaers; O=$R/out/fda-drug-event-kg
W=$R/work/vaers_test; Q=$R/repo/queries; G=https://purl.org/okn/frink/kg/fda-drug-event-kg
export JVM_ARGS=-Xmx4g TMPDIR=$R/work
mkdir -p $W/q
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
avail_gb() { awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }
free_gb() { df --output=avail -BG / | tail -1 | tr -dc 0-9; }
log "== wait: no device loader and >= 9 GB available (now $(avail_gb) GB), $(free_gb) GB free"
while pgrep -f 'medical-device-kg.*xloader' >/dev/null || [ "$(avail_gb)" -lt 9 ]; do sleep 60; done
[ "$(free_gb)" -gt 200 ] || { log "under 200 GB free, stop"; exit 1; }
[ -d $DB ] && { log "$DB exists, stop"; exit 1; }
log "== 1. load VAERS + symptom text into $G"
"$J/tdb2.tdbloader" --loc $DB --graph $G $O/vaers.ttl.gz $O/l2_term_text_vaers.ttl.gz 2>&1 | grep -E "Finished|Error|Exception" | tail -2
log "db $(du -sh $DB | cut -f1), free $(free_gb) GB"
log "== 2. queries"
OUT=$W/query_results_vaers_$(date +%Y-%m-%d).md
{ echo "# VAERS query results, $(date '+%B %d, %Y %H:%M'), store $(du -sh $DB | cut -f1)"; echo; echo "| query | rows | time | status |"; echo "|---|---|---|---|"; } > $OUT
body=$W/body.md; : > $body
run() {
  local t0=$(date +%s)
  "$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --query "$2" > $W/q/$1.txt 2> $W/q/$1.err; local rc=$? t=$(( $(date +%s) - t0 ))
  local rows=$(grep -cE '^\| ' $W/q/$1.txt); rows=$(( rows > 0 ? rows - 1 : 0 ))
  printf "| %s | %s | %s s | %s |\n" "$1" "$rows" "$t" "$([ $rc -eq 0 ] && echo ok || echo "rc $rc: $(head -c 120 $W/q/$1.err)")" >> $OUT
  { echo; echo "## $1 ($rows rows, $t s)"; echo '```'; grep -v '^$' "$2" | head -2; echo '...'; head -40 $W/q/$1.txt | cut -c1-220; echo '```'; } >> $body
}
ns="https://bmedesign.org/fda-drug-event-kg/ns/"
for q in $Q/common_counts.rq $Q/common_provenance.rq; do
  sed -E "s|GRAPH_NS|$ns|; s|WHERE \{ (.*) \}|WHERE { GRAPH <$G> { \1 } }|" $q > $W/q/tmp.rq
  run "vaers__$(basename $q .rq)" $W/q/tmp.rq
done
for q in $Q/fda-drug-event-kg/q7_*.rq $Q/fda-drug-event-kg/q8_*.rq $Q/fda-drug-event-kg/q9_*.rq $Q/fda-drug-event-kg/q10_*.rq; do run "vaers__$(basename $q .rq)" "$q"; done
cat $body >> $OUT; rm -f $body
log "== 3. reports per year: raw VAERSDATA.csv rows (domestic + non-domestic) vs graph"
{ echo; echo "## raw CSV row counts per year (VAERSDATA.csv, minus header) for comparison with q7"; echo '```'
python3 - $R/raw <<'PY'
import csv, io, re, sys, zipfile, glob, collections
root = sys.argv[1]
counts = collections.Counter()
for z in glob.glob(f"{root}/**/*VAERS*.zip", recursive=True):
    with zipfile.ZipFile(z) as zf:
        for name in zf.namelist():
            m = re.search(r"(\d{4}|NonDomestic)VAERSDATA\.csv$", name)
            if not m: continue
            with zf.open(name) as fh:
                rows = sum(1 for _ in csv.reader(io.TextIOWrapper(fh, encoding="latin-1"))) - 1
            counts[m.group(1)] += rows
for k in sorted(counts): print(k, counts[k])
print("total", sum(counts.values()))
PY
echo '```'; } >> $OUT
du -sh $DB; df -h / | tail -1
log "DONE test_vaers -> $OUT"
