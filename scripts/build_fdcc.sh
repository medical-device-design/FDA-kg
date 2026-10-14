#!/usr/bin/env bash
# L1 for the six fdcc food inventories (fda-food-cosmetic-kg) and tobacco marketing orders
# (fda-tobacco-kg). Builds a CAS -> substance IRI map from fda-substance-kg first so CAS
# columns link across graphs.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; RIOT=$R/tools/apache-jena-5.2.0/bin/riot
O=$R/out; W=$R/work/fdcc; export TMPDIR=$R/work
mkdir -p $W
latest() { ls -d "$1"/20* | sort | tail -1; }
cd "$P"; python3 fda_iri.py && python3 mapper.py || exit 1

echo "=== CAS -> substance map from fda-substance-kg (GsrsCodes with codeSystem CAS)"
# a GsrsCodes block: subject <.../id/unii/<unii>/codes/<uuid>> or <.../id/gsrs/<uuid>/codes/<uuid>>
awk '
  /^<https:\/\/bmedesign.org\/fda-substance-kg\/id\/[^>]*\/codes\/[^>]*>$/ { subj=$0; sub(/^</,"",subj); sub(/>$/,"",subj); code=""; sys=""; next }
  subj && /^    ex:code "/        { code=$0; sub(/^    ex:code "/,"",code); sub(/" ;$/,"",code); sub(/" \.$/,"",code) }
  subj && /^    ex:codeSystem "CAS"/ { sys="CAS" }
  subj && /\.$/ { if (sys=="CAS" && code!="") { parent=subj; sub(/\/codes\/.*$/,"",parent); print code "\t" parent } subj="" }
' $O/fda-substance-kg/gsrs_substance.ttl | sort -u > $W/cas_map.tsv
echo "   $(wc -l < $W/cas_map.tsv) CAS codes, $(cut -f1 $W/cas_map.tsv | sort -u | wc -l) distinct"

for set in foodsubstances grasnotices fcn scogs indirectadditives coloradditives; do
  echo "=== $set"
  python3 l1_fdcc.py $set "$(latest $R/raw/fda-food-cosmetic-kg/fdcc-$set)" $O/fda-food-cosmetic-kg/fdcc_$set.ttl --cas-map $W/cas_map.tsv
  "$RIOT" --validate --count $O/fda-food-cosmetic-kg/fdcc_$set.ttl 2>&1 | tail -1
done
echo "=== marketing orders"
python3 l1_fdcc.py marketingorders "$(latest $R/raw/fda-tobacco-kg/fda-marketing-orders)" $O/fda-tobacco-kg/tobacco_marketing_orders.ttl
"$RIOT" --validate --count $O/fda-tobacco-kg/tobacco_marketing_orders.ttl 2>&1 | tail -1
rm -rf $W
df -h / | tail -1
echo "DONE build_fdcc"
