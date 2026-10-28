#!/usr/bin/env bash
# L1 for FDA Import Alerts (l1_import_alerts.py) -> out/fda-compliance-kg/import_alerts.ttl, riot, SHACL, counts.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out/fda-compliance-kg
S=$(ls -d $R/raw/fda-compliance-kg/fda-import-alerts/20* | sort | tail -1); F=$O/import_alerts.ttl
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
echo "=== import alerts from $S ($(ls $S/importalert_*.html | wc -l) pages)"
python3 l1_import_alerts.py "$S" $F || { echo FAILED; exit 1; }
"$J/riot" --validate --count $F 2>&1 | tail -1
JVM_ARGS=-Xmx3g "$J/shacl" validate --shapes $R/repo/shapes/fda-compliance-kg.shapes.ttl --data $F 2>/dev/null | grep -oE "sh:conforms +(true|false)" | head -1
echo "=== classes"; grep -oE "^    a ex:[A-Za-z]+" $F | sort | uniq -c
echo "=== alerts by type"; grep -oE 'ex:type "[^"]+"' $F | sort | uniq -c
echo "=== firms by list color"; grep -oE 'ex:listColor "[^"]+"' $F | sort | uniq -c
echo "=== pages with no firm list (count)"; python3 - "$S" <<'PY'
import sys, re, pathlib
n = sum(1 for p in pathlib.Path(sys.argv[1]).glob("importalert_*.html") if 'name="RedFirm"' not in p.read_text(errors="replace"))
print(n)
PY
ls -la $F; echo "DONE build_import_alerts"
