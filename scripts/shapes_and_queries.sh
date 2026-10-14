#!/usr/bin/env bash
# SHACL shapes (Jena shacl) and the SPARQL query battery (TDB2) for every graph.
# Graphs under ~1.3 GB of Turtle are checked whole; larger ones on a slice (first N blocks
# per file, N = 1.2 M / files), which still exercises every class and link rule.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin
O=$R/out; W=$R/work/shapes; Q=$R/repo/queries; SH=$R/repo/shapes
export JVM_ARGS="-Xmx10g"; export TMPDIR=$R/work
rm -rf $W; mkdir -p $W $SH
cd "$P"; python3 fda_iri.py || exit 1
python3 gen_shapes.py $SH || exit 1

GRAPHS="${@:-fda-tobacco-kg fda-compliance-kg fda-food-cosmetic-kg fda-drug-biologic-kg fda-substance-kg fda-animal-health-kg}"
for g in $GRAPHS; do
  echo; echo "################ $g"
  files=$(ls $O/$g/*.ttl $O/$g/*.ttl.gz 2>/dev/null)
  n=$(echo "$files" | wc -l)
  bytes=$(du -cb $files | tail -1 | cut -f1)
  case "$files" in *.gz*) bytes=$((bytes * 20));; esac     # gzip ratio ~20:1 on these files
  data=$W/$g.ttl; : > $data
  if [ "$bytes" -lt 1300000000 ]; then
    mode="whole"; for f in $files; do case "$f" in *.gz) zcat "$f";; *) cat "$f";; esac >> $data; done
  else
    mode="slice"; per=$((1200000 / n))
    for f in $files; do python3 $P/sample_ttl.py "$f" $W/part.ttl $per >&2; cat $W/part.ttl >> $data; done
  fi
  echo "data: $mode, $(du -h $data | cut -f1)"
  echo "--- shacl"
  $J/shacl validate --shapes $SH/$g.shapes.ttl --data $data > $W/$g.report.ttl 2> $W/$g.shacl.err
  echo "conforms: $(grep -oE 'sh:conforms +(true|false)' $W/$g.report.ttl | head -1)   violations: $(grep -c 'sh:ValidationResult' $W/$g.report.ttl)"
  grep -oE 'sh:resultPath +[^ ;]+' $W/$g.report.ttl | sort | uniq -c | sort -rn | head -8
  grep -oE 'sh:resultMessage +"[^"]{0,160}' $W/$g.report.ttl | sort | uniq -c | sort -rn | head -5
  head -3 $W/$g.shacl.err
  echo "--- queries (TDB2)"
  rm -rf $W/tdb; $J/tdb2.tdbloader --loc $W/tdb $data > $W/load.log 2>&1 || { tail -3 $W/load.log; }
  ns="https://bmedesign.org/$g/ns/"
  for q in $Q/common_counts.rq $Q/common_provenance.rq $(ls $Q/$g/*.rq 2>/dev/null); do
    echo "=== $(basename $q)"
    sed "s|GRAPH_NS|$ns|" $q > $W/q.rq
    $J/tdb2.tdbquery --loc $W/tdb --query $W/q.rq 2>&1 | head -30
  done
  rm -rf $W/tdb $data $W/part.ttl
done
echo; df -h / | tail -1
echo "DONE shapes_and_queries"
