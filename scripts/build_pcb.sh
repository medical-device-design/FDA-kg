#!/usr/bin/env bash
# L1 for the Product Code Builder snapshot (l1_pcb.py) -> out/fda-compliance-kg/product_codes.ttl,
# riot, chunked SHACL, counts. Outputs only; raw/ untouched. The API key is never read here.
# On the VM this lives at repo/build_pcb.sh.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out/fda-compliance-kg; W=$R/work/pcb
export TMPDIR=$R/work; mkdir -p $W
S=$(ls -d $R/raw/fda-compliance-kg/fda-pcb/20* | sort | tail -1); F=$O/product_codes.ttl
[ -s "$S/MANIFEST.json" ] || { echo "no MANIFEST.json in $S (fetch not finished)"; exit 1; }
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
echo "=== product codes from $S"; python3 -c "import json; m=json.load(open('$S/MANIFEST.json')); print({k: v['rows'] for k, v in m['lists'].items()}, {k: v['rows'] for k, v in m['by_industry'].items()})"
python3 l1_pcb.py "$S" $F || { echo FAILED; exit 1; }
"$J/riot" --validate --count $F 2>&1 | tail -1
check='JVM_ARGS=-Xmx3g '"$J"'/shacl validate --shapes '"$R"'/repo/shapes/fda-compliance-kg.shapes.ttl --data {} 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1 | tr -s " "'
python3 $P/chunk_ttl.py $F $W 200000 "$check" | tail -1
echo "=== classes"; grep -oE "^    a ex:[A-Za-z]+" $F | sort | uniq -c
echo "=== product codes per industry (top 10)"; grep -oE '^    ex:productCode "[0-9]{2}' $F | sort | uniq -c | sort -rn | head -10
rm -rf $W; ls -la $F; echo "DONE build_pcb"
