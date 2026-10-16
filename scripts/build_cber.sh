#!/usr/bin/env bash
# L1 for the CBER eBER and eHCTERS registries (after fetch_l0_cber.sh): parse the saved detail
# pages into fda-drug-biologic-kg, people in the reporting-official and US-agent sections dropped.
# riot + SHACL on the new file, then a few counts.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/cber
export TMPDIR=$R/work; mkdir -p $W
S=$(ls -d $R/raw/fda-drug-biologic-kg/cber-establishment-registration/20* | sort | tail -1)
F=$O/fda-drug-biologic-kg/cber_establishments.ttl
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
python3 l1_cber.py "$S" $F || { echo FAILED; exit 1; }
"$J/riot" --validate --count $F 2>&1 | tail -1
JVM_ARGS=-Xmx6g $J/shacl validate --shapes $R/repo/shapes/fda-drug-biologic-kg.shapes.ttl --data $F > $W/rep.ttl 2>$W/err
echo "   shapes: $(grep -oE 'sh:conforms +(true|false)' $W/rep.ttl | head -1)  violations: $(grep -c sh:ValidationResult $W/rep.ttl)"
grep -oE 'sh:resultPath +[^ ;]+' $W/rep.ttl | sort | uniq -c | sort -rn | head -4; head -2 $W/err
echo "=== people fields present (must be 0)"; grep -cE 'ex:(reportingOfficialName|usAgentName|email) ' $F
echo "=== classes"; grep -oE '^    a ex:[A-Za-z]+' $F | sort | uniq -c
echo "=== statuses"; grep -oE 'ex:currentStatus "[^"]+"' $F | sort | uniq -c
echo "=== establishment types (eBER), top"; grep -oE 'ex:establishmentType "[^"]+"' $F | sort | uniq -c | sort -rn | head -8
echo "=== notes (unparsed single-cell rows), top"; grep -oE 'ex:note "[^"]{0,60}' $F | sort | uniq -c | sort -rn | head -8
echo "=== FEI overlap with DECRS"; comm -12 <(grep -oE 'ex:feiNumber "[0-9]+"' $F | sort -u) <(grep -oE 'ex:feiNumber "[0-9]+"' $O/fda-drug-biologic-kg/drls_establishments.ttl | sort -u) | wc -l
rm -rf $W; df -h / | tail -1; echo "DONE build_cber"
