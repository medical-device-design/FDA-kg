#!/usr/bin/env bash
# L0 raw fetch for the remaining openFDA sources that fit on the current disk.
# Deferred until the new data volume: drug/label (1.8 GB zipped), drug/event (111 GB).
# Same rules as fetch_l0_phase1.sh: dated snapshot, SHA-256 manifest, never overwrite.
set -euo pipefail
FDAKG=/srv/fda-products-kg
STAMP=$(date -u +%F)
MIN_FREE_GB=8

SOURCES=(
  "fda-drug-biologic-kg|drug|drugsfda"
  "fda-drug-biologic-kg|drug|ndc"
  "fda-drug-biologic-kg|drug|orangebook"
  "fda-drug-biologic-kg|drug|shortages"
  "fda-drug-biologic-kg|transparency|crl"
  "fda-drug-biologic-kg|other|nsde"
  "fda-food-cosmetic-kg|food|event"
  "fda-food-cosmetic-kg|cosmetic|event"
  "fda-tobacco-kg|tobacco|problem"
  "fda-tobacco-kg|research|tobaccodigitalads"
  "fda-tobacco-kg|research|tobaccoharmmenthol"
  "fda-tobacco-kg|research|tobaccopreventionads"
  "fda-tobacco-kg|research|tobaccosmokefree"
  "fda-compliance-kg|other|historicaldocument"
  "fda-animal-health-kg|animalandveterinary|event"
)

dl_json="$FDAKG/manifests/openfda_download_${STAMP}.json"
[ -s "$dl_json" ] || curl -fsSL --retry 3 https://api.fda.gov/download.json -o "$dl_json"

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r graph product endpoint <<<"$entry"
  dest="$FDAKG/raw/$graph/openfda-$product-$endpoint/$STAMP"
  if [ -f "$dest/SHA256SUMS" ]; then echo "skip $product/$endpoint: exists"; continue; fi
  free_gb=$(df -BG --output=avail "$FDAKG" | tail -1 | tr -dc '0-9')
  (( free_gb >= MIN_FREE_GB )) || { echo "STOP before $product/$endpoint: ${free_gb} GB free" >&2; exit 1; }
  mkdir -p "$dest"
  jq -r --arg p "$product" --arg e "$endpoint" '.results[$p][$e].partitions[].file' "$dl_json" > "$dest/urls.txt"
  jq --arg p "$product" --arg e "$endpoint" '.results[$p][$e] | {export_date, total_records}' "$dl_json" > "$dest/meta.json"
  n=$(wc -l < "$dest/urls.txt"); [ "$n" -gt 0 ] || { echo "no partitions for $product/$endpoint" >&2; exit 1; }
  echo "fetch $product/$endpoint: $n partition(s)"
  while read -r url; do
    # keep the quarter folder (e.g. 2004q3/) in the file name so partitions never collide
    f="$dest/$(echo "$url" | sed -E 's#.*/([^/]+)/([^/]+\.json\.zip)$#\1__\2#; s#^(https?:__)?##')"
    case "$url" in */event/*q[1-4]/*|*/all_other/*) ;; *) f="$dest/$(basename "$url")";; esac
    curl -fSsL --retry 5 --retry-delay 10 -C - "$url" -o "$f.part" && mv "$f.part" "$f"
  done < "$dest/urls.txt"
  (cd "$dest" && sha256sum *.zip > SHA256SUMS)
  echo "ok $product/$endpoint $(du -sh "$dest" | cut -f1)"
done
echo "DONE phase 2 openFDA L0 fetch ($STAMP)"
du -sh $FDAKG/raw/*; df -h / | tail -1
