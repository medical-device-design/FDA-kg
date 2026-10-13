#!/usr/bin/env bash
# L0 raw fetch for Phase 1 (fda-substance-kg, fda-compliance-kg).
# Reads openFDA's live manifest (download.json) so URLs and partition counts
# are never hardcoded. Writes dated snapshots plus a SHA-256 manifest.
# Never unzips into raw, never edits or deletes an existing snapshot.
#
# Run on build-vm:
#   source /srv/fda-products-kg/env.sh
#   nohup bash fetch_l0_phase1.sh > $FDAKG/logs/fetch_$(date +%F).log 2>&1 &
set -euo pipefail

: "${FDAKG:?source env.sh first}"
STAMP=$(date -u +%F)
MANIFEST_URL=https://api.fda.gov/download.json
MIN_FREE_GB=10

# graph|openFDA product|endpoint
SOURCES=(
  "fda-substance-kg|other|substance"
  "fda-substance-kg|other|unii"
  "fda-compliance-kg|food|enforcement"
  "fda-compliance-kg|drug|enforcement"
)

command -v jq >/dev/null || { echo "jq missing: sudo apt-get install -y jq" >&2; exit 1; }

dl_json="$FDAKG/manifests/openfda_download_${STAMP}.json"
[ -s "$dl_json" ] || curl -fsSL --retry 3 "$MANIFEST_URL" -o "$dl_json"

for entry in "${SOURCES[@]}"; do
  IFS='|' read -r graph product endpoint <<<"$entry"
  dest="$FDAKG/raw/$graph/openfda-$product-$endpoint/$STAMP"

  if [ -f "$dest/SHA256SUMS" ]; then
    echo "skip $product/$endpoint: snapshot $STAMP exists"
    continue
  fi

  free_gb=$(df -BG --output=avail "$FDAKG" | tail -1 | tr -dc '0-9')
  if (( free_gb < MIN_FREE_GB )); then
    echo "STOP before $product/$endpoint: ${free_gb} GB free" >&2
    exit 1
  fi

  mkdir -p "$dest"
  jq -r --arg p "$product" --arg e "$endpoint" \
     '.results[$p][$e].partitions[].file' "$dl_json" > "$dest/urls.txt"
  jq --arg p "$product" --arg e "$endpoint" \
     '.results[$p][$e] | {export_date, total_records}' "$dl_json" > "$dest/meta.json"

  n=$(wc -l < "$dest/urls.txt")
  [ "$n" -gt 0 ] || { echo "no partitions for $product/$endpoint" >&2; exit 1; }
  echo "fetch $product/$endpoint: $n partition(s) -> $dest"

  while read -r url; do
    f="$dest/$(basename "$url")"
    curl -fSL --retry 5 --retry-delay 10 -C - "$url" -o "$f.part"
    mv "$f.part" "$f"
  done < "$dest/urls.txt"

  (cd "$dest" && sha256sum *.zip > SHA256SUMS)
  echo "ok $product/$endpoint $(du -sh "$dest" | cut -f1)"
done

echo "Phase 1 openFDA L0 fetch complete ($STAMP)."
df -h "$FDAKG"
