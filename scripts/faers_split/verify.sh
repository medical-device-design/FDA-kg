#!/bin/bash
set -uo pipefail
cd /srv/fda-products-kg
W=work/faers_dedup/verify; mkdir -p $W; O=out/fda-drug-event-kg; D=work/faers_links/dups_faers_reports.txt
RIOT=tools/apache-jena-5.2.0/bin/riot; export JVM_ARGS=-Xmx3g
log(){ echo "$(date '+%F %T') $*" | tee -a $W/verify.log; }
for f in drug_event_v2 drug_event_part2_v2 l2_term_text_faers_v2; do pigz -t $O/$f.ttl.gz && log "gzip ok $f" || log "GZIP FAIL $f"; done
: > $W/tops.txt; : > $W/blocks.ttl
for f in drug_event_v2 drug_event_part2_v2; do
  pigz -dc $O/$f.ttl.gz | mawk -v dups=$D -v tops=$W/tops_$f.txt -v blocks=$W/blocks_$f.ttl -f work/faers_dedup/verify_extract.awk
  cat $W/tops_$f.txt >> $W/tops.txt; log "extracted $f"
done
log "report nodes (occurrences): $(wc -l < $W/tops.txt)"
log "distinct report IRIs: $(LC_ALL=C sort -u -S 2G -T $W $W/tops.txt | wc -l)"
log "suffixed -2 report nodes: $(grep -c -- '-2$' $W/tops.txt)"
# the duplicated reports parse and each report node has one transmission date
cat $W/blocks_drug_event_v2.ttl > $W/blocks.ttl; grep -v '^@prefix' $W/blocks_drug_event_part2_v2.ttl >> $W/blocks.ttl
$RIOT --validate $W/blocks.ttl > $W/riot.txt 2>&1 && log "riot ok on the duplicated-report blocks ($(grep -c '^<' $W/blocks.ttl) blocks)" || log "RIOT PROBLEMS: $(head -3 $W/riot.txt)"
$RIOT --output=nt $W/blocks.ttl > $W/blocks.nt 2>/dev/null
mawk '$2=="<https://bmedesign.org/fda-drug-event-kg/ns/transmissiondate>" {c[$1]++} END {for (k in c) {n++; if (c[k]>1) m++}; print "report nodes with a transmission date:", n, "with more than one:", m+0}' $W/blocks.nt | tee -a $W/verify.log
mawk '$2=="<https://bmedesign.org/fda-drug-event-kg/ns/medicinalproduct>" {c[$1]++} END {for (k in c) if (c[k]>1) m++; print "drug nodes with two product names:", m+0}' $W/blocks.nt | tee -a $W/verify.log
pigz -dc $O/l2_term_text_faers_v2.ttl.gz | grep -c -- '/report/[^/]*-2/patient/reaction/' | sed 's/^/term text reaction subjects on -2 reports: /' | tee -a $W/verify.log
log "VERIFY DONE"
