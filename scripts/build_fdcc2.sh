#!/usr/bin/env bash
# Fetch (L0) and convert (L1) eight more fdcc food inventories into fda-food-cosmetic-kg,
# then validate the graph's new files with riot and the SHACL shapes. Disk guard first.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; J=$R/tools/apache-jena-5.2.0/bin; O=$R/out
D=$(date +%F); UA="Mozilla/5.0 (research; medical-device-design FDA-kg)"; W=$R/work/fdcc2; export TMPDIR=$R/work
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9'); echo "free: ${free_gb} GB"; [ "$free_gb" -ge 12 ] || { echo "STOP: under 12 GB free"; exit 1; }
mkdir -p $W
latest() { ls -d "$1"/20* | sort | tail -1; }
declare -A SETS=( [cedi]=CEDI [postmarket]=Postmarket [tor]=TOR [recycledplastics]=RecycledPlastics [seafoodlist]=SeafoodList
                  [newplantvarietyconsultations]=NewPlantVarietyConsultations [newproteinconsultations]=NewProteinConsultations [genomeeditedplants]=GenomeEditedPlants )
echo "=== L0"
for set in "${!SETS[@]}"; do
  dir=$R/raw/fda-food-cosmetic-kg/fdcc-$set/$D; mkdir -p $dir
  u="https://www.hfpappexternal.fda.gov/scripts/fdcc/cfc/XMLService.cfm?method=downloadxls&set=${SETS[$set]}"
  curl -s -A "$UA" -L --max-time 300 -o $dir/${SETS[$set]}.csv -w "$set HTTP %{http_code} size %{size_download}\n" "$u"
  (cd $dir && sha256sum * > SHA256SUMS && echo "$u" > SOURCE_URL)
done
echo "=== CAS map"; cd "$P"; python3 fda_iri.py >/dev/null || exit 1
awk '
  /^<https:\/\/bmedesign.org\/fda-substance-kg\/id\/[^>]*\/codes\/[^>]*>$/ { subj=$0; sub(/^</,"",subj); sub(/>$/,"",subj); code=""; sys=""; next }
  subj && /^    ex:code "/        { code=$0; sub(/^    ex:code "/,"",code); sub(/" ;$/,"",code); sub(/" \.$/,"",code) }
  subj && /^    ex:codeSystem "CAS"/ { sys="CAS" }
  subj && /\.$/ { if (sys=="CAS" && code!="") { parent=subj; sub(/\/codes\/.*$/,"",parent); print code "\t" parent } subj="" }
' $O/fda-substance-kg/gsrs_substance.ttl | sort -u > $W/cas_map.tsv; wc -l < $W/cas_map.tsv
echo "=== L1"
for set in cedi postmarket tor recycledplastics seafoodlist newplantvarietyconsultations newproteinconsultations genomeeditedplants; do
  python3 l1_fdcc.py $set "$(latest $R/raw/fda-food-cosmetic-kg/fdcc-$set)" $O/fda-food-cosmetic-kg/fdcc_$set.ttl --cas-map $W/cas_map.tsv
  "$J/riot" --validate --count $O/fda-food-cosmetic-kg/fdcc_$set.ttl 2>&1 | tail -1
done
echo "=== shapes on the new files"
python3 gen_shapes.py $R/repo/shapes >/dev/null
cat $O/fda-food-cosmetic-kg/fdcc_*.ttl > $W/new.ttl
JVM_ARGS=-Xmx6g $J/shacl validate --shapes $R/repo/shapes/fda-food-cosmetic-kg.shapes.ttl --data $W/new.ttl > $W/report.ttl 2>$W/err
echo "conforms: $(grep -oE 'sh:conforms +(true|false)' $W/report.ttl | head -1)  violations: $(grep -c sh:ValidationResult $W/report.ttl)"; grep -oE 'sh:resultPath +[^ ;]+' $W/report.ttl | sort | uniq -c | head -5; head -2 $W/err
rm -rf $W; df -h / | tail -1; echo "DONE build_fdcc2"
