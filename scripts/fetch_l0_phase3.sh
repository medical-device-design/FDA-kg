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
  # up to 6 passes: a pass skips partitions already on disk, so transient DNS or HTTP
  # failures are retried on the next pass; the manifest is written only when all are present
  for pass in 1 2 3 4 5 6; do
    i=0; missing=0
    while read -r url; do
      i=$((i+1))
      free_gb=$(df -BG --output=avail "$FDAKG" | tail -1 | tr -dc '0-9')
      (( free_gb >= MIN_FREE_GB )) || { echo "STOP at partition $i of $product/$endpoint: ${free_gb} GB free" >&2; exit 1; }
      f="$dest/$(echo "$url" | sed -E 's#.*/([^/]+)/([^/]+\.json\.zip)$#\1__\2#; s#^(https?:__)?##')"
      case "$url" in */event/*q[1-4]/*|*/all_other/*) ;; *) f="$dest/$(basename "$url")";; esac
      [ -s "$f" ] && continue                      # resumable
      if curl -fSsL --retry 8 --retry-delay 15 --retry-all-errors -C - "$url" -o "$f.part"; then mv "$f.part" "$f"; else missing=$((missing+1)); rm -f "$f.part"; fi
      (( i % 100 == 0 )) && echo "$(date +%T)   $product/$endpoint: $i of $n partitions, $(du -sh "$dest" | cut -f1)" || true
    done < "$dest/urls.txt"
    have=$(ls "$dest" | grep -c 'json\.zip$')
    echo "$(date +%T)   pass $pass: $have of $n partitions on disk, $missing failed this pass"
    [ "$have" -ge "$n" ] && break
    sleep 60
  done
  have=$(ls "$dest" | grep -c 'json\.zip$')
  [ "$have" -ge "$n" ] || { echo "FAILED $product/$endpoint: only $have of $n partitions after 6 passes" >&2; exit 1; }
  (cd "$dest" && sha256sum *.zip > SHA256SUMS)
  echo "$(date +%T) ok $product/$endpoint $(du -sh "$dest" | cut -f1)"
done
echo "DONE phase 3 openFDA L0 fetch ($STAMP)"; df -h / | tail -1
