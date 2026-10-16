#!/usr/bin/env bash
# L0 snapshot of the Drug Establishments Current Registration Site (DECRS) bulk files:
# registered establishments and the excluded list. Official downloads from
# https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); S=$R/raw/fda-drug-biologic-kg/fda-drls-registration/$D
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free_gb" -ge 12 ] || { echo "ABORT: only ${free_gb}G free"; exit 1; }
mkdir -p "$S"; cd "$S"
for f in drls_reg.zip drls_excluded.zip; do
  curl -sS -L -A "Mozilla/5.0" -o "$f" "https://www.accessdata.fda.gov/cder/$f" || echo "FAILED $f"
done
printf '%s\n' 'https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site' \
  'https://www.accessdata.fda.gov/cder/drls_reg.zip' 'https://www.accessdata.fda.gov/cder/drls_excluded.zip' > SOURCE_URL
sha256sum *.zip > SHA256SUMS
ls -la; for f in *.zip; do echo "== $f"; unzip -l "$f"; done
for f in *.zip; do n=$(unzip -Z1 "$f" | head -1); echo "== head of $n"; unzip -p "$f" "$n" | head -3 | cut -c1-600; echo "   lines: $(unzip -p "$f" "$n" | wc -l)"; done
df -h / | tail -1; echo "DONE fetch_l0_drls"
