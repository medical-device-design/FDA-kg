#!/usr/bin/env bash
# L1 for the MedDRA MedAscii release (l1_meddra.py) -> out/fda-drug-event-kg/meddra_<ver>.ttl
# LICENSED: this output stays on the build VM. It is never uploaded, committed or copied out.
# riot, SHACL (one file, fits in one JVM), streaming check, counts. raw/ untouched.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out/fda-drug-event-kg; W=$R/work/meddra
export TMPDIR=$R/work; mkdir -p $W $O
REL=${1:-$(ls -d $R/raw/licensed/meddra/*/ | sort -V | tail -1)}; REL=${REL%/}
VER=$(basename "$REL"); RETRIEVED=${2:-2026-11-03}; F=$O/meddra_${VER//./_}.ttl
[ -s "$REL/MedAscii/pt.asc" ] || { echo "no MedAscii/pt.asc in $REL"; exit 1; }
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
echo "=== MedDRA $VER from $REL (retrieved $RETRIEVED)"; file "$REL"/MedAscii/pt.asc "$REL"/MedAscii/smq_list.asc
python3 l1_meddra.py "$REL" $F "$RETRIEVED" || { echo FAILED; exit 1; }
chmod 640 $F
"$J/riot" --validate --count $F 2>&1 | tail -1
JVM_ARGS=-Xmx6g "$J/shacl" validate --shapes $R/repo/shapes/fda-drug-event-kg.shapes.ttl --data $F 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "
python3 $P/stream_check.py fda-drug-event-kg $F 2>/dev/null | tail -4
echo "=== classes"; grep -oE "^    a ex:[A-Za-z]+" $F | sort | uniq -c
echo "=== non-current LLTs"; grep -c 'ex:lltCurrency "N"' $F
rm -rf $W; ls -la $F; echo "DONE build_meddra"
