#!/usr/bin/env bash
# L0 fetch: FDA food-inventory exports (fdcc "Download data" buttons) and the tobacco
# marketing-orders attachment. Dated snapshot folders with SHA-256 manifests, as everywhere.
# The exports arrive as CSV text served as application/vnd.ms-excel.
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); UA="Mozilla/5.0 (research; medical-device-design FDA-kg)"
for set in FoodSubstances GRASNotices FCN SCOGS IndirectAdditives ColorAdditives; do
  dir=$R/raw/fda-food-cosmetic-kg/fdcc-$(echo $set | tr 'A-Z' 'a-z')/$D; mkdir -p $dir
  u="https://www.hfpappexternal.fda.gov/scripts/fdcc/cfc/XMLService.cfm?method=downloadxls&set=$set"
  curl -s -A "$UA" -L --max-time 300 -o $dir/$set.csv -w "$set HTTP %{http_code} type %{content_type} size %{size_download}\n" "$u"
  head -c 400 $dir/$set.csv | tr -d '\r' | head -5 | cut -c1-200
  (cd $dir && sha256sum * > SHA256SUMS && echo "$u" > SOURCE_URL)
done
dir=$R/raw/fda-tobacco-kg/fda-marketing-orders/$D; mkdir -p $dir
curl -s -A "$UA" -L --max-time 300 -o $dir/media_112123.csv -w "tobacco media/112123 HTTP %{http_code} type %{content_type} size %{size_download}\n" "https://www.fda.gov/media/112123/download?attachment"
(cd $dir && sha256sum * > SHA256SUMS && echo "https://www.fda.gov/media/112123/download?attachment" > SOURCE_URL)
du -sh $R/raw/fda-food-cosmetic-kg/fdcc-* $dir
