#!/usr/bin/env bash
# L0 fetch for the round-3 sources. Dated snapshot folders with SHA-256 manifests.
#   NDI notifications      fda.gov/media/193535 (xlsx, 1995 to present)
#   Recall announcements   FDA Recalls, Market Withdrawals & Safety Alerts, xlsx export paged 60 rows
#                          per call; pages are fetched until one repeats (3-year rolling list)
#   Tobacco products       Searchable Tobacco Products Database, CSV export
#   Animal Drugs @ FDA     the site's own public REST API: catalogue, one preview per application,
#                          code lists and the monthly-update index (polite 0.25 s spacing)
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); UA="Mozilla/5.0 (research; medical-device-design FDA-kg)"
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9'); echo "free: ${free_gb} GB"; [ "$free_gb" -ge 12 ] || { echo "STOP: under 12 GB free"; exit 1; }
seal() { (cd "$1" && sha256sum $(ls | grep -v -E '^SHA256SUMS$|^SOURCE_URL$') > SHA256SUMS && echo "$2" > SOURCE_URL); }

echo "=== NDI notifications"
d=$R/raw/fda-food-cosmetic-kg/fda-ndi-notifications/$D; mkdir -p $d
curl -s -A "$UA" -L --max-time 300 -o $d/ndi_notifications.xlsx -w "HTTP %{http_code} type %{content_type} size %{size_download}\n" "https://www.fda.gov/media/193535/download?attachment"
file -b $d/ndi_notifications.xlsx | cut -c1-60; seal $d "https://www.fda.gov/media/193535/download?attachment"

echo "=== Recall announcements (paged xlsx)"
d=$R/raw/fda-compliance-kg/fda-recall-announcements/$D; mkdir -p $d
B="https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts/datatables-data"
prev=""; for p in $(seq 0 400); do
  f=$d/page$(printf '%03d' $p).xlsx
  curl -s -A "$UA" -L --max-time 120 -o $f "$B?page=$p&_format=xlsx" || break
  h=$(sha256sum $f | cut -c1-16); sz=$(stat -c %s $f)
  if [ "$h" = "$prev" ] || [ "$sz" -lt 3000 ]; then rm -f $f; echo "   stopped at page $p (repeat or empty)"; break; fi
  prev=$h; sleep 0.5
done
echo "   pages: $(ls $d/*.xlsx | wc -l)"; seal $d "$B?page=N&_format=xlsx"

echo "=== Searchable Tobacco Products Database"
d=$R/raw/fda-tobacco-kg/fda-tobacco-products-database/$D; mkdir -p $d
curl -s -A "$UA" -L --max-time 300 -o $d/tobacco_products.csv -w "HTTP %{http_code} type %{content_type} size %{size_download}\n" "https://www.accessdata.fda.gov/scripts/searchtobacco/index.cfm?action=export.viewFile"
head -2 $d/tobacco_products.csv | cut -c1-160; echo "   rows: $(wc -l < $d/tobacco_products.csv)"; seal $d "https://www.accessdata.fda.gov/scripts/searchtobacco/index.cfm?action=export.viewFile"

echo "=== Animal Drugs @ FDA (public REST API)"
d=$R/raw/fda-animal-health-kg/fda-animal-drugs-at-fda/$D; mkdir -p $d/previews
API="https://animaldrugsatfda.fda.gov/adafda/app/search/public"
body='{"basicSearchTerm":null,"applicationNumber":null,"sponsorName":null,"activeIngredientName":null,"applicationStatusCode":null,"applicationStatusValue":null,"indication":null,"proprietaryName":null,"doseFormName":null,"routeName":null,"speciesName":null,"isExact":false,"sortField":"applicationNumber","sortDirection":"false","pageSize":null,"pageNumber":null}'
curl -s -A "$UA" --max-time 300 -H "Content-Type: application/json" -X POST -d "$body" -o $d/catalogue.json -w "catalogue HTTP %{http_code} size %{size_download}\n" "$API/advancedSearchForExcelPdf"
for c in application_type application_status; do curl -s -A "$UA" --max-time 60 -o $d/codes_$c.json "$API/codes/$c"; done
curl -s -A "$UA" --max-time 60 -o $d/monthlyUpdates.json "$API/monthlyUpdates"
ids=$(python3 -c "
import json,sys
c=json.load(open('$d/catalogue.json'))
items=c if isinstance(c,list) else (c.get('content') or c.get('results') or c.get('data') or [])
print('\n'.join(str(x.get('applicationId') or x.get('id')) for x in items if x.get('applicationId') or x.get('id')))")
n=$(echo "$ids" | grep -c .); echo "   applications in catalogue: $n"
i=0; for id in $ids; do
  [ -s $d/previews/$id.json ] && continue
  curl -s -A "$UA" --max-time 60 -o $d/previews/$id.json "$API/retrievePreviewBean/$id"; i=$((i+1)); sleep 0.25
  [ $((i % 500)) -eq 0 ] && echo "   $i previews"
done
echo "   previews: $(ls $d/previews | wc -l)"; seal $d "$API (advancedSearchForExcelPdf, retrievePreviewBean/{id}, codes/*, monthlyUpdates)"
du -sh $R/raw/*/fda-ndi-notifications $R/raw/*/fda-recall-announcements $R/raw/*/fda-tobacco-products-database $R/raw/*/fda-animal-drugs-at-fda 2>/dev/null
df -h / | tail -1; echo "DONE fetch_l0_round3"
