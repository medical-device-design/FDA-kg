#!/usr/bin/env bash
# Query test for fda-drug-event-kg on the shared VM (VM only). Adds VAERS in full and a contiguous
# FAERS sample to the existing six-graph TDB2 as the named graph .../fda-drug-event-kg, then runs
# queries/fda-drug-event-kg/*.rq and checks three sampled FAERS reports against the live openFDA API.
# Waits until the device project's loader has exited and 9 GB of memory is available (its two
# Fuseki servers are permanent). Never deletes, uploads or touches lakeFS.
#   test_drug_event.sh [sample_bytes=7000000000]
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2; O=$R/out/fda-drug-event-kg
W=$R/work/drug_event_test; Q=$R/repo/queries; G=https://purl.org/okn/frink/kg/fda-drug-event-kg
BYTES=${1:-7000000000}; SKIP_VAERS=${SKIP_VAERS:-0}; MIN_FREE=${MIN_FREE:-250}; REUSE_SAMPLE=${REUSE_SAMPLE:-0}
export JVM_ARGS=-Xmx4g TMPDIR=$R/work
mkdir -p $W $W/q
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*"; }
avail_gb() { awk '/MemAvailable/ {printf "%d", $2/1048576}' /proc/meminfo; }
free_gb() { df --output=avail -BG / | tail -1 | tr -dc 0-9; }

log "== wait for memory: device loader gone and >= 9 GB available (now $(avail_gb) GB)"
while pgrep -f 'medical-device-kg.*xloader' >/dev/null || [ "$(avail_gb)" -lt 9 ]; do sleep 60; done
log "memory ok: $(avail_gb) GB available, $(free_gb) GB disk free"
[ "$(free_gb)" -gt $MIN_FREE ] || { log "under $MIN_FREE GB free, stop"; exit 1; }

if [ "$SKIP_VAERS" = 1 ]; then log "== 1. VAERS skipped (SKIP_VAERS=1, disk)"; else
log "== 1. VAERS full load (vaers.ttl.gz + l2_term_text_vaers.ttl.gz) into $G"
"$J/tdb2.tdbloader" --loc $DB --graph $G $O/vaers.ttl.gz $O/l2_term_text_vaers.ttl.gz 2>&1 | grep -E "Finished|Error|Exception" | tail -2
fi
log "db now $(du -sh $DB | cut -f1), free $(free_gb) GB"

if [ "$REUSE_SAMPLE" = 1 ]; then log "== 2. FAERS sample reused (already in the store); re-deriving report ids"; cp $W/faers_sample.ttl $W/faers_raw.ttl; else
log "== 2. FAERS sample: first $BYTES bytes of the uncompressed stream, cut at a record boundary"
zcat $O/drug_event.ttl.gz | head -c $BYTES > $W/faers_raw.ttl; fi
python3 - "$W" <<'PY'
import re, sys
w = sys.argv[1]
data = open(f"{w}/faers_raw.ttl", "rb").read()
cut = data.rfind(b"\n\n")
data = data[:cut + 2]
open(f"{w}/faers_sample.ttl", "wb").write(data)
ids = sorted(set(re.findall(rb"/id/report/([^/>]+)", data)))   # safety report ids are slugs such as 6078344_x
open(f"{w}/report_ids.txt", "wb").write(b"\n".join(ids) + b"\n")
# the last report may be partial: drop it from the id list used for the openFDA check
print(f"sample bytes {len(data)}, report ids {len(ids)}, first {ids[0].decode()}, last {ids[-1].decode()}")
PY
rm -f $W/faers_raw.ttl
log "== 2b. term text for the sampled reports (streaming filter of l2_term_text_faers.ttl.gz)"
python3 - "$W" "$O/l2_term_text_faers.ttl.gz" <<'PY'
import gzip, re, sys
w, src = sys.argv[1], sys.argv[2]
ids = set(open(f"{w}/report_ids.txt").read().split())
pat = re.compile(r"/id/report/([^/>]+)/")
n = kept = 0; keep = False
with gzip.open(src, "rt", encoding="utf-8") as fh, open(f"{w}/faers_sample_text.ttl", "w", encoding="utf-8") as out:
    for line in fh:
        if line.startswith("@prefix") or line.startswith("PREFIX"):
            out.write(line); continue
        if line.startswith("<"):
            m = pat.search(line); keep = bool(m and m.group(1) in ids); n += 1
            kept += keep
        if keep:
            out.write(line)
        if n and n % 10000000 == 0:
            print(f"  {n} reaction blocks scanned, {kept} kept", file=sys.stderr, flush=True)
print(f"term text: {n} reaction blocks scanned, {kept} kept")
PY
"$J/riot" --validate $W/faers_sample.ttl $W/faers_sample_text.ttl 2>&1 | grep -iE "error|warn" | head -3; log "riot done"
log "== 3. load the FAERS sample into $G"
if [ "$REUSE_SAMPLE" = 1 ]; then files=$W/faers_sample_text.ttl; else files="$W/faers_sample.ttl $W/faers_sample_text.ttl"; fi
"$J/tdb2.tdbloader" --loc $DB --graph $G $files 2>&1 | grep -E "Finished|Error|Exception" | tail -2
log "db now $(du -sh $DB | cut -f1), free $(free_gb) GB"

log "== 4. queries"
OUT=$W/query_results_drug_event_$(date +%Y-%m-%d).md
{ echo "# fda-drug-event-kg query results, $(date '+%B %d, %Y %H:%M'): VAERS full, FAERS sample of $(wc -l < $W/report_ids.txt) reports"; echo; echo "| query | rows | time | status |"; echo "|---|---|---|---|"; } > $OUT
body=$W/body.md; : > $body
run() {
  local t0=$(date +%s)
  "$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --query "$2" > $W/q/$1.txt 2> $W/q/$1.err; local rc=$? t=$(( $(date +%s) - t0 ))
  local rows=$(grep -cE '^\| ' $W/q/$1.txt); rows=$(( rows > 0 ? rows - 1 : 0 ))
  printf "| %s | %s | %s s | %s |\n" "$1" "$rows" "$t" "$([ $rc -eq 0 ] && echo ok || echo "rc $rc: $(head -c 120 $W/q/$1.err)")" >> $OUT
  { echo; echo "## $1 ($rows rows, $t s)"; echo '```'; grep -v '^$' "$2" | head -2; echo '...'; head -22 $W/q/$1.txt | cut -c1-220; echo '```'; } >> $body
}
ns="https://bmedesign.org/fda-drug-event-kg/ns/"
for q in $Q/common_counts.rq $Q/common_provenance.rq; do
  sed -E "s|GRAPH_NS|$ns|; s|WHERE \{ (.*) \}|WHERE { GRAPH <$G> { \1 } }|" $q > $W/q/tmp.rq
  run "drug_event__$(basename $q .rq)" $W/q/tmp.rq
done
for q in $Q/fda-drug-event-kg/*.rq; do run "drug_event__$(basename $q .rq)" "$q"; done
cat $body >> $OUT; rm -f $body

log "== 5. three sampled reports: graph vs live openFDA"
{
echo; echo "## openFDA check"
n=$(wc -l < $W/report_ids.txt)
for id in $(sed -n "2p;$((n/2))p;$((n-2))p" $W/report_ids.txt); do
  echo; echo "### report $id"
  echo "graph:"
  "$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --query <(cat <<SP
PREFIX e: <https://bmedesign.org/fda-drug-event-kg/ns/>
SELECT (SAMPLE(?d) AS ?received) (SAMPLE(?s) AS ?serious) (COUNT(DISTINCT ?drug) AS ?drugs) (COUNT(DISTINCT ?rx) AS ?reactions) (GROUP_CONCAT(DISTINCT ?t; separator="; ") AS ?terms) WHERE {
  BIND(<https://bmedesign.org/fda-drug-event-kg/id/report/$id> AS ?r)
  OPTIONAL { ?r e:receivedate ?d } OPTIONAL { ?r e:serious ?s }
  OPTIONAL { ?r e:patient ?pt . OPTIONAL { ?pt e:drug ?drug } OPTIONAL { ?pt e:reaction ?rx . OPTIONAL { ?rx e:reactionmeddrapt ?t } } } }
SP
) | cut -c1-400
  raw=$("$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --results=CSV --query <(echo "PREFIX e: <https://bmedesign.org/fda-drug-event-kg/ns/> SELECT ?s WHERE { <https://bmedesign.org/fda-drug-event-kg/id/report/$id> e:safetyreportid ?s }") | tail -1 | tr -d '"\r')
  echo "openFDA (safetyreportid $raw):"
  curl -s --max-time 60 "https://api.fda.gov/drug/event.json?search=safetyreportid:%22$raw%22&limit=1" > $W/q/api_$id.json
  python3 - $W/q/api_$id.json <<'PY'
import json, sys
try:
    d = json.load(open(sys.argv[1]))["results"][0]
    p = d.get("patient", {})
    print("  receivedate", d.get("receivedate"), "serious", d.get("serious"), "drugs", len(p.get("drug", [])), "reactions", len(p.get("reaction", [])))
    print("  terms:", "; ".join(x.get("reactionmeddrapt", "") for x in p.get("reaction", [])))
except Exception as ex:
    print("  api error:", ex)
PY
done
} >> $OUT
du -sh $DB; df -h / | tail -1
log "DONE test_drug_event -> $OUT"
