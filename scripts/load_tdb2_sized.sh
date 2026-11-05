#!/usr/bin/env bash
# Sized TDB2 load for query testing (VM only). Loads one graph at a time, smallest first, and
# stops before the dataset passes the budget or the volume drops under the reserve. Excludes
# FAERS, VAERS and the MedDRA files (the November 4 full load took 253 GB). Re-running resumes:
# a graph with a marker in work/tdb2_loaded/ is not loaded twice.
#   load_tdb2_sized.sh [budget_GB=100] [reserve_GB=150]
# Size estimate: 5x the gzipped source. Observed November 5: compliance 4.0 GB gz -> 29 GB, substance 4.4 GB -> 23 GB,
# drug-biologic 4.4 GB -> 21 GB, animal health 0.5 GB -> 58 GB (148 M short triples: the index, not the node table, dominates).
set -uo pipefail
R=/srv/fda-products-kg; J=$R/tools/apache-jena-5.2.0/bin; DB=$R/tdb2; O=$R/out; M=$R/work/tdb2_loaded
BUDGET=${1:-100}; RESERVE=${2:-150}
export JVM_ARGS=-Xmx4g TMPDIR=$R/work     # 4 GB: the device project's JVMs are up, rule in VM_WORKFLOW.md
GRAPHS="fda-tobacco-kg fda-animal-health-kg fda-food-cosmetic-kg fda-compliance-kg fda-substance-kg fda-drug-biologic-kg"
mkdir -p $DB $M
free_gb() { df --output=avail -BG / | tail -1 | tr -dc 0-9; }
db_gb() { du -sBG $DB | cut -f1 | tr -dc 0-9; }
echo "== sized tdb2 load start $(date), budget ${BUDGET}G, reserve ${RESERVE}G, db $(db_gb)G, free $(free_gb)G"
for g in $GRAPHS; do
  [ -f $M/$g ] && { echo "-- $g: already loaded ($(cat $M/$g))"; continue; }
  files=""; bytes=0
  for f in $O/$g/*.ttl $O/$g/*.ttl.gz; do
    [ -f "$f" ] || continue
    case "$(basename $f)" in drug_event*|vaers*|meddra_*|l2_meddra_*|*.report.txt|*.unmapped.tsv) continue;; esac
    files="$files $f"; bytes=$((bytes + $(stat -c %s "$f")))
  done
  est_gb=$(( bytes * 5 / 1073741824 + 1 ))
  echo "-- $g ($(date +%H:%M)): $(echo $files | wc -w) files, $((bytes / 1048576)) MB on disk, estimate ${est_gb}G; db now $(db_gb)G, free $(free_gb)G"
  if [ $(( $(db_gb) + est_gb )) -gt $BUDGET ]; then echo "   skip: would pass the ${BUDGET}G budget"; continue; fi
  if [ $(( $(free_gb) - est_gb )) -lt $RESERVE ]; then echo "   skip: would leave under ${RESERVE}G free"; continue; fi
  "$J/tdb2.tdbloader" --loc $DB --graph "https://purl.org/okn/frink/kg/$g" $files 2>&1 | grep -E "Finished|Error|Exception" | tail -2
  echo "$(date '+%Y-%m-%d %H:%M') db $(db_gb)G" > $M/$g
  echo "   db after: $(db_gb)G"
done
echo "== counts per graph"
"$J/tdb2.tdbquery" --loc $DB 'SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g ORDER BY ?g'
du -sh $DB; df -h / | tail -1
echo "DONE load_tdb2_sized $(date)"
