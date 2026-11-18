#!/bin/bash
# Option A (Roche, November 18, 2026): second copies of the 1,811 FAERS report ids get report/<id>-2.
# Inputs streamed from lakeFS main (byte-identical to the deleted local copies, md5 checked November 5).
set -euo pipefail
cd /srv/fda-products-kg
L="tools/lakectl --config /srv/medical-device-kg/.lakectl.yaml"; M=lakefs://fda-drug-event-kg/main
W=work/faers_dedup; O=out/fda-drug-event-kg; A=$W/faers_split_versions.awk
D=work/faers_links/dups_faers_reports.txt
log(){ echo "$(date '+%F %T') $*" | tee -a $W/split.log; }
# 1. the lakeFS copies must exist with the local sizes before anything is deleted
for f in drug_event.ttl.gz drug_event_part2.ttl.gz l2_term_text_faers.ttl.gz; do
  ls_size=$(stat -c %s $O/$f)
  $L fs stat $M/$f > $W/stat_$f.txt
  grep -q "$ls_size" $W/stat_$f.txt || { log "size mismatch for $f, stopping"; exit 1; }
  log "lakeFS copy of $f has the local size $ls_size"
done
# 2. delete the three local originals (Roche's word, November 18, 12:15)
rm $O/drug_event.ttl.gz $O/drug_event_part2.ttl.gz $O/l2_term_text_faers.ttl.gz
free=$(df --output=avail -BG /srv | tail -1 | tr -dc 0-9); log "deleted the three originals, free ${free}G"
[ "$free" -gt 250 ] || { log "not enough free space"; exit 1; }
# 3. stream from lakeFS, relabel, write v2
log "start drug_event.ttl.gz"
$L fs cat $M/drug_event.ttl.gz | pigz -dc | mawk -v dups=$D -v state=$W/occ1.tsv -v stats=$W/stats1.txt -f $A | pigz -p 4 -6 > $O/drug_event_v2.ttl.gz
log "done drug_event: $(cat $W/stats1.txt)"
$L fs cat $M/drug_event_part2.ttl.gz | pigz -dc | mawk -v dups=$D -v init=$W/occ1.tsv -v state=$W/occ2.tsv -v stats=$W/stats2.txt -f $A | pigz -p 4 -6 > $O/drug_event_part2_v2.ttl.gz
log "done part2: $(cat $W/stats2.txt)"
$L fs cat $M/l2_term_text_faers.ttl.gz | pigz -dc | mawk -v dups=$D -v state=$W/occ_tt.tsv -v stats=$W/stats_tt.txt -f $A | pigz -p 4 -6 > $O/l2_term_text_faers_v2.ttl.gz
log "done term text: $(cat $W/stats_tt.txt)"
pigz -dc $O/l2_meddra_faers.ttl.gz | mawk -v dups=$D -v state=$W/occ_md.tsv -v stats=$W/stats_md.txt -f $A | pigz -p 4 -6 > $O/l2_meddra_faers_v2.ttl.gz
chmod 640 $O/l2_meddra_faers_v2.ttl.gz
log "done meddra (VM only): $(cat $W/stats_md.txt)"
log "ALL DONE"
