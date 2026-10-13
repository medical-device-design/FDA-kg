#!/usr/bin/env bash
# L0 fetch for the non-openFDA bulk files confirmed on 2026-10-12/13:
#   Drugs@FDA data files zip, Orange Book zip (fda.gov/media ids seen in Chrome),
#   Purple Book monthly CSV (accessdata), warning-letters datatable JSON (fda.gov API).
# Dated snapshots with SHA-256 manifests, never overwrite.
set -euo pipefail
R=/srv/fda-products-kg
STAMP=$(date -u +%F)
fetch() {  # graph source url filename
  local dest=$R/raw/$1/$2/$STAMP
  if [ -f "$dest/SHA256SUMS" ]; then echo "skip $2: exists"; return; fi
  mkdir -p "$dest"
  echo "$3" > "$dest/url.txt"
  curl -fSsL --retry 5 --retry-delay 10 -A "Mozilla/5.0 (FDA-kg pipeline; roche0619@outlook.com)" \
       "$3" -o "$dest/$4.part" && mv "$dest/$4.part" "$dest/$4"
  (cd "$dest" && sha256sum "$4" > SHA256SUMS)
  echo "ok $2 $(du -sh "$dest/$4" | cut -f1)  $(file -b "$dest/$4" | cut -c1-60)"
}
fetch fda-drug-biologic-kg fda-drugsatfda-files "https://www.fda.gov/media/89850/download?attachment" drugsatfda.zip
fetch fda-drug-biologic-kg fda-orangebook-files "https://www.fda.gov/media/76860/download?attachment" EOBZIP.zip
fetch fda-drug-biologic-kg fda-purplebook "https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-September-data-download.csv" purplebook-2026-09.csv
fetch fda-compliance-kg fda-warning-letters "https://www.fda.gov/files/api/datatables/static/warning-letters.json" warning-letters.json
df -h / | tail -1
