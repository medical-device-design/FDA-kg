#!/bin/bash
# the one duplicated report whose two copies are adjacent in one partition: in the L2 files (no
# report node to close a group) both copies fell into one group, so the second run of reactions
# kept the base IRI. Rename that second run (the reaction index restarts at 0).
set -euo pipefail
cd /srv/fda-products-kg; W=work/faers_dedup; O=out/fda-drug-event-kg
id=$(python3 - <<'PY'
import collections
by=collections.defaultdict(list)
for l in open("/srv/fda-products-kg/work/faers_dedup/dup_versions.tsv"):
    r=l.rstrip("\n").split("\t"); by[r[0]].append(r)
for k,v in by.items():
    if v[0][2]==v[1][2] and abs(int(v[0][3])-int(v[1][3]))==1: print(k)
PY
)
echo "adjacent pair: $id" | tee $W/fix_adj.log
for f in l2_term_text_faers_v2 l2_meddra_faers_v2; do
  pigz -dc $O/$f.ttl.gz | mawk -v base="$id" '
    BEGIN { pre = "<" base "/patient/reaction/"; n = 0 }
    index($0, pre) == 1 { if (substr($0, length(pre) + 1, 2) == "0>") n++; if (n == 2) { sub("<" base "/", "<" base "-2/"); c++ } }
    { print } END { print "renamed lines " c+0 > "/dev/stderr" }' 2>>$W/fix_adj.log | pigz -p 4 -6 > $O/$f.tmp.gz
  mv $O/$f.tmp.gz $O/$f.ttl.gz; echo "fixed $f" >> $W/fix_adj.log
done
chmod 640 $O/l2_meddra_faers_v2.ttl.gz
cat $W/fix_adj.log
