#!/usr/bin/env bash
# L0 for FDA Import Alerts (accessdata cms_ia): the by-number index and every import alert page it
# lists, one request per second, into a dated snapshot with SOURCE_URL and SHA256SUMS. Never overwrites.
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); UA="Mozilla/5.0"
BASE=https://www.accessdata.fda.gov/cms_ia
dest=$R/raw/fda-compliance-kg/fda-import-alerts/$D; mkdir -p "$dest"; cd "$dest"
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free_gb" -ge 12 ] || { echo "ABORT: only ${free_gb}G free"; exit 1; }
[ -s ialist.html ] || curl -fsSL -A "$UA" --retry 3 -o ialist.html "$BASE/ialist.html" || { echo "FAILED ialist"; exit 1; }
printf '%s\n' "$BASE/ialist.html" > SOURCE_URL
pages=$(grep -oE 'importalert_[0-9]+\.html' ialist.html | sort -u)
n=0; fail=0
for p in $pages; do
  if [ -s "$p" ]; then continue; fi
  curl -fsSL -A "$UA" --retry 3 -o "$p" "$BASE/$p" && n=$((n+1)) || { echo "FAILED $p"; fail=$((fail+1)); rm -f "$p"; }
  sleep 1
done
echo "index lists $(echo "$pages" | wc -w) alerts; fetched $n new, $fail failed, $(ls importalert_*.html | wc -l) on disk"
printf '%s\n' "$BASE/importalert_<number>.html for every alert listed on ialist.html" >> SOURCE_URL
sha256sum $(ls | grep -vE '^(SHA256SUMS|SOURCE_URL)$') > SHA256SUMS
du -sh "$dest"; echo "DONE fetch_l0_import_alerts"
