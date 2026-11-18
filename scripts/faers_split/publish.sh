#!/bin/bash
# Publish the corrected FAERS files (Roche's "yes to all", November 18, 2026, 18:01).
set -euo pipefail
cd /srv/fda-products-kg
L="tools/lakectl --config /srv/medical-device-kg/.lakectl.yaml"; R=lakefs://fda-drug-event-kg
O=out/fda-drug-event-kg; W=work/faers_dedup; LOG=logs/lakefs_faers_split_2026-11-18.log
log(){ echo "$(date '+%F %T') $*" | tee -a $LOG; }
log "start; develop $($L branch show $R/develop 2>/dev/null | awk '/Commit ID/{print $NF}' | cut -c1-8)"
for pair in drug_event_v2:drug_event drug_event_part2_v2:drug_event_part2 l2_term_text_faers_v2:l2_term_text_faers; do
  src=${pair%%:*}; dst=${pair##*:}
  md5=$(md5sum $O/$src.ttl.gz | cut -d' ' -f1); size=$(stat -c %s $O/$src.ttl.gz)
  log "upload $src.ttl.gz -> develop/$dst.ttl.gz ($size bytes, md5 $md5)"
  $L fs upload --source $O/$src.ttl.gz $R/develop/$dst.ttl.gz > /dev/null
  $L fs stat $R/develop/$dst.ttl.gz | grep -E '^(Size|Checksum):' > $W/pub_stat_$dst.txt
  grep -q "$size bytes" $W/pub_stat_$dst.txt || { log "SIZE MISMATCH $dst"; exit 1; }
  if grep -q "$md5" $W/pub_stat_$dst.txt; then log "ok $dst: size and md5 match"; else log "ok $dst: size matches ($(grep Checksum $W/pub_stat_$dst.txt), multipart etag, not an md5)"; fi
done
$L commit $R/develop -m "FAERS: the second copy of each of the 1,811 report ids that openFDA lists twice gets its own IRI (report/<id>-2), November 18, 2026" \
  --meta source=FDA-kg/work/faers_dedup --meta reports=20692690 --meta split_ids=1811 | tee -a $LOG
$L merge $R/develop $R/main -m "Merge develop: FAERS report copies split (report/<id>-2), November 18, 2026" | tee -a $LOG
log "main now $($L branch show $R/main 2>/dev/null | awk '/Commit ID/{print $NF}' | cut -c1-8)"
$L fs ls $R/main/ | tee -a $LOG
log "PUBLISH DONE"
