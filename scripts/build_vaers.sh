#!/usr/bin/env bash
# L1 for VAERS (manual snapshot under raw/fda-drug-biologic-kg/vaers/<date>) into fda-drug-event-kg,
# publish mode (MedDRA SYMPTOM1..5 text dropped). riot, chunked SHACL, counts.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/vaers
export TMPDIR=$R/work; mkdir -p $W $O/fda-drug-event-kg
S=$(ls -d $R/raw/fda-drug-biologic-kg/vaers/20* | sort | tail -1)
F=$O/fda-drug-event-kg/vaers.ttl.gz
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
python3 l1_vaers.py "$S" $F --publish || { echo FAILED; exit 1; }
"$J/riot" --validate --count $F 2>&1 | tail -1
check="JVM_ARGS=-Xmx6g $J/shacl validate --shapes $R/repo/shapes/fda-drug-event-kg.shapes.ttl --data {} 2>/dev/null | grep -oE 'sh:conforms +(true|false)' | head -1 | tr -s ' '"
python3 $P/chunk_ttl.py $F $W 300000 "$check" | tail -1
echo "=== MedDRA term columns in the published file (must be 0)"; zcat $F | grep -cE 'ex:symptom[1-5] ' || true
echo "=== classes"; zcat $F | grep -oE '^    a ex:[A-Za-z]+' | sort | uniq -c
echo "=== reports by receive year (top 8)"; zcat $F | grep -oE 'ex:recvdate "[0-9]{4}' | sort | uniq -c | sort -rn | head -8
echo "=== files"; zcat $F | grep -oE 'ex:sourceDataset "vaers/[^"]+' | sort | uniq -c | wc -l
rm -rf $W; ls -la $F; df -h / | tail -1; echo "DONE build_vaers"
