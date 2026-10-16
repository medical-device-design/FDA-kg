#!/usr/bin/env bash
# L1 for DECRS (after fetch_l0_drls.sh): drug establishment registrations into fda-drug-biologic-kg,
# contact-person columns dropped. riot + SHACL on the new file.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out; W=$R/work/drls
export TMPDIR=$R/work; mkdir -p $W
S=$(ls -d $R/raw/fda-drug-biologic-kg/fda-drls-registration/20* | sort | tail -1)
cd "$P"; python3 gen_shapes.py $R/repo/shapes >/dev/null
python3 l1_drls.py "$S" $O/fda-drug-biologic-kg/drls_establishments.ttl || { echo FAILED; exit 1; }
"$J/riot" --validate --count $O/fda-drug-biologic-kg/drls_establishments.ttl 2>&1 | tail -1
JVM_ARGS=-Xmx6g $J/shacl validate --shapes $R/repo/shapes/fda-drug-biologic-kg.shapes.ttl --data $O/fda-drug-biologic-kg/drls_establishments.ttl > $W/rep.ttl 2>$W/err
echo "   shapes: $(grep -oE 'sh:conforms +(true|false)' $W/rep.ttl | head -1)  violations: $(grep -c sh:ValidationResult $W/rep.ttl)"
grep -oE 'sh:resultPath +[^ ;]+' $W/rep.ttl | sort | uniq -c | sort -rn | head -4; head -2 $W/err
echo "=== no contact columns in the published file"
grep -cE 'ex:(establishmentContact|registrantContact|agentDetails)' $O/fda-drug-biologic-kg/drls_establishments.ttl
echo "=== operations"
grep -oE 'ex:operation "[^"]+"' $O/fda-drug-biologic-kg/drls_establishments.ttl | sort | uniq -c | sort -rn | head -12
rm -rf $W; df -h / | tail -1; echo "DONE build_drls"
