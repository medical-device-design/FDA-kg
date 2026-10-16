#!/usr/bin/env bash
# Full-coverage SHACL on the three graphs that were validated on slices before: every file is
# streamed through chunks of 400k node blocks, each chunk validated with Jena shacl and
# deleted, so memory stays at one chunk. Also writes the tobacco product -> marketing order
# L2 links. Read-only on raw/ and the L1 files.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/shacl_full
export TMPDIR=$R/work; mkdir -p $W
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
check='JVM_ARGS=-Xmx8g '"$J"'/shacl validate --shapes '"$R"'/repo/shapes/GRAPH.shapes.ttl --data {} 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "'
for g in fda-drug-biologic-kg fda-substance-kg fda-animal-health-kg; do
  echo "################ $g"
  cmd=${check//GRAPH/$g}
  for f in $O/$g/*.ttl $O/$g/*.ttl.gz; do [ -e "$f" ] || continue
    echo "--- $(basename $f)"
    python3 $P/chunk_ttl.py "$f" $W 400000 "$cmd" | tail -1
  done
done
echo "################ tobacco L2 links"
python3 $P/l2_tobacco_links.py $O/fda-tobacco-kg $O/fda-tobacco-kg/l2_tobacco_links.ttl
"$J/riot" --validate --count $O/fda-tobacco-kg/l2_tobacco_links.ttl 2>&1 | tail -1
rm -rf $W; df -h / | tail -1; echo "DONE shacl_full"
