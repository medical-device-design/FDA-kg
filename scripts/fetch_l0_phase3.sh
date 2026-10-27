#!/usr/bin/env bash
# L0 raw fetch of the two openFDA bulk sets deferred until the 1 TB volume: drug/label (SPL, about
# 1.8 GB zipped) and drug/event (FAERS, about 111 GB zipped). Dated snapshot, SHA-256 manifest,
# never overwrite, stop if free space would fall under MIN_FREE_GB. Same layout as phase 1 and 2.
set -euo pipefail
FDAKG=/srv/fda-products-kg
STAMP=$(date -u +%F)
MIN_FREE_GB=150
SOURCES=(
  "fda-drug-biologic-kg|drug|label"
  "fda-drug-event-kg|drug|event"
)
mkdir -p "$FDAKG/manifests"
dl_json="$FDAKG/manifests/openfda_download_${STAMP}.json"
[ -s "$dl_json" ] || curl -fsSL --retry 3 https://api.fda.gov/download.json -o "$dl_json"
for entry in "${SOURCES[@]}"; do
  IFS='|' read -r graph product endpoint <<<"$entry"
  dest="$FDAKG/raw/$graph/openfda-$product-$endpoint/$STAMP"
  if [ -f "$dest/SHA256SUMS" ]; then echo "skip $product/$endpoint: exists"; continue; fi
  mkdir -p "$dest"
  jq -r --arg p "$product" --arg e "$endpoint" '.results[$p][$e].partitions[].file' "$dl_json" > "$dest/urls.txt"
  jq --arg p "$product" --arg e "$endpoint" '.results[$p][$e] | {export_date, total_records}' "$dl_json" > "$dest/meta.json"
  n=$(wc -l < "$dest/urls.txt"); [ "$n" -gt 0 ] || { echo "no partitions for $product/$endpoint" >&2; exit 1; }
  echo "$(date +%T) fetch $product/$endpoint: $n partition(s), $(cat "$dest/meta.json" | tr -d '\n ')"
  i=0
  while read -r url; do
    i=$((i+1))
    free_gb=$(df -BG --output=avail "$FDAKG" | tail -1 | tr -dc '0-9')
    (( free_gb >= MIN_FREE_GB )) || { echo "STOP at partition $i of $product/$endpoint: ${free_gb} GB free" >&2; exit 1; }
    f="$dest/$(echo "$url" | sed -E 's#.*/([^/]+)/([^/]+\.json\.zip)$#\1__\2#; s#^(https?:__)?##')"
    case "$url" in */event/*q[1-4]/*|*/all_other/*) ;; *) f="$dest/$(basename "$url")";; esac
    [ -s "$f" ] && continue                      # resumable
    curl -fSsL --retry 5 --retry-delay 10 -C - "$url" -o "$f.part" && mv "$f.part" "$f"
    (( i % 100 == 0 )) && echo "$(date +%T)   $product/$endpoint: $i of $n partitions, $(du -sh "$dest" | cut -f1)"
  done < "$dest/urls.txt"
  (cd "$dest" && sha256sum *.zip > SHA256SUMS)
  echo "$(date +%T) ok $product/$endpoint $(du -sh "$dest" | cut -f1)"
done
echo "DONE phase 3 openFDA L0 fetch ($STAMP)"; df -h / | tail -1
