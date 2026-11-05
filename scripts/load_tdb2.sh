#!/usr/bin/env bash
# Local TDB2 dataset for query testing (VM only, never uploaded): six graphs plus VAERS, one named
# graph per shortname (https://purl.org/okn/frink/kg/<shortname>, the FRINK convention), MedDRA
# files included because the dataset is internal. FAERS (19 B triples) is skipped: too big for
# TDB2 here, its joins are checked on a sampled chunk instead.
# Lesson from November 4, 2026: this full set took 253 GB (long literals), three times the
# estimate. Size with one graph first and keep the dataset under 100 GB on the shared volume.
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2; O=$R/out
export JVM_ARGS=-Xmx8g TMPDIR=$R/work
GRAPHS="fda-substance-kg fda-compliance-kg fda-drug-biologic-kg fda-food-cosmetic-kg fda-animal-health-kg fda-tobacco-kg fda-drug-event-kg"
free=$(df --output=avail -BG / | tail -1 | tr -dc 0-9); [ "$free" -gt 150 ] || { echo "only ${free}G free, need 150G"; exit 1; }
[ -d $DB ] && { echo "$DB exists; remove it by hand first (nothing is deleted here)"; exit 1; }
mkdir -p $DB
echo "== tdb2 load start $(date)"
for g in $GRAPHS; do
  files=""
  for f in $O/$g/*.ttl $O/$g/*.ttl.gz; do
    [ -f "$f" ] || continue
    case "$(basename $f)" in drug_event*.ttl.gz|*.report.txt|*.unmapped.tsv) continue;; esac
    files="$files $f"
  done
  echo "-- $g ($(date +%H:%M)):$(echo $files | wc -w) files"
  "$J/tdb2.tdbloader" --loc $DB --graph "https://purl.org/okn/frink/kg/$g" $files 2>&1 | grep -E "Total|Finish|Error|Exception" | tail -3
done
echo "== counts per graph"
"$J/tdb2.tdbquery" --loc $DB 'SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g'
du -sh $DB
echo "DONE load_tdb2 $(date)"
