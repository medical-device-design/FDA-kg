#!/usr/bin/env bash
# Rebuild warning_letters.ttl (now mints firm nodes), write L2 stub nodes for the drug and
# compliance graphs, validate, and re-check link resolution.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; RIOT=$R/tools/apache-jena-5.2.0/bin/riot
O=$R/out; W=$R/work/stubs; export TMPDIR=$R/work
latest() { ls -d "$1"/20* | sort | tail -1; }
mkdir -p $W
cd "$P"; python3 fda_iri.py || exit 1

echo "=== warning letters (with firm nodes)"
python3 l1_tables.py warning-letters "$(latest $R/raw/fda-compliance-kg/fda-warning-letters)" $O/fda-compliance-kg/warning_letters.ttl
grep -c '    a ex:RecallingFirm' $O/fda-compliance-kg/warning_letters.ttl

echo "=== L2 stubs"
python3 l2_stubs.py $O/fda-drug-biologic-kg $O/fda-drug-biologic-kg/l2_stubs.ttl
python3 l2_stubs.py $O/fda-compliance-kg  $O/fda-compliance-kg/l2_stubs.ttl

echo "=== validate"
for f in $O/fda-compliance-kg/warning_letters.ttl $O/fda-drug-biologic-kg/l2_stubs.ttl $O/fda-compliance-kg/l2_stubs.ttl; do
  "$RIOT" --validate --count "$f" 2>&1 | tail -1
done

echo "=== link resolution after stubs"
subj() { cat $1/*.ttl | grep -oE '^<[^>]+>$' | sort -u -S 1G; }
subj $O/fda-drug-biologic-kg > $W/drug.subjects
subj $O/fda-compliance-kg   > $W/comp.subjects
check() { cat $2/*.ttl | grep -oE "$3 <[^>]+>" | grep -oE '<[^>]+>' | sort -u -S 1G > $W/refs
  refs=$(wc -l < $W/refs); hit=$(comm -12 $W/refs $4 | wc -l)
  printf '%-48s refs=%-8s exist=%-8s (%s%%)\n' "$1" "$refs" "$hit" "$(( refs ? 100*hit/refs : 0 ))"; }
check "drug -> application"  $O/fda-drug-biologic-kg "ex:hasApplication" $W/drug.subjects
check "drug -> package NDC"  $O/fda-drug-biologic-kg "ex:hasPackageNdc"  $W/drug.subjects
check "compliance -> firm"   $O/fda-compliance-kg   "ex:has(Recalling)?Firm" $W/comp.subjects
rm -rf $W
df -h / | tail -1
echo "DONE stubs_and_firms"
