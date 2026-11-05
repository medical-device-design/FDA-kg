#!/usr/bin/env bash
# Run the SPARQL battery (queries/<graph>/*.rq, queries/cross/*.rq, queries/common_*.rq per graph)
# against the local TDB2 dataset with the union default graph, and write one results file:
# query name, rows returned, seconds, and the first 25 rows. VM only.
#   run_queries.sh [out.md]
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2; Q=$R/repo/queries
export JVM_ARGS=-Xmx4g
OUT=${1:-$R/work/query_results_$(date +%Y-%m-%d).md}; mkdir -p $(dirname $OUT) $R/work/q
GRAPHS="fda-substance-kg fda-compliance-kg fda-drug-biologic-kg fda-food-cosmetic-kg fda-animal-health-kg fda-tobacco-kg"
run() {  # name file
  local t0=$(date +%s)
  "$J/tdb2.tdbquery" --loc $DB --set tdb:unionDefaultGraph=true --time --query "$2" > $R/work/q/$1.txt 2> $R/work/q/$1.err
  local rc=$? t=$(( $(date +%s) - t0 ))
  local rows=$(grep -cE '^\| ' $R/work/q/$1.txt); rows=$(( rows > 0 ? rows - 1 : 0 ))
  printf "| %s | %s | %s s | %s |\n" "$1" "$rows" "$t" "$([ $rc -eq 0 ] && echo ok || echo "rc $rc: $(head -c 120 $R/work/q/$1.err)")" >> $OUT.summary
  { echo; echo "## $1 ($rows rows, $t s)"; echo '```'; grep -v '^$' "$2" | head -3; echo '...'; head -28 $R/work/q/$1.txt | cut -c1-200; [ $rows -gt 25 ] && echo "(first 25 of $rows rows)"; echo '```'; } >> $OUT.body
}
: > $OUT.summary; : > $OUT.body
for g in $GRAPHS; do
  ns="https://bmedesign.org/$g/ns/"
  for q in $Q/common_counts.rq $Q/common_provenance.rq; do
    sed -E "s|GRAPH_NS|$ns|; s|WHERE \{ (.*) \}|WHERE { GRAPH <https://purl.org/okn/frink/kg/$g> { \1 } }|" $q > $R/work/q/tmp.rq
    run "${g}__$(basename $q .rq)" $R/work/q/tmp.rq
  done
  for q in $Q/$g/*.rq; do [ -f "$q" ] && run "${g}__$(basename $q .rq)" "$q"; done
done
for q in $Q/cross/*.rq; do run "cross__$(basename $q .rq)" "$q"; done
{ echo "# Query results, $(date '+%B %d, %Y %H:%M'), TDB2 $(du -sh $DB | cut -f1), union default graph"; echo; echo "| query | rows | time | status |"; echo "|---|---|---|---|"; cat $OUT.summary; cat $OUT.body; } > $OUT
rm -f $OUT.summary $OUT.body
echo "DONE run_queries -> $OUT"
