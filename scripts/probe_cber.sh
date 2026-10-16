#!/usr/bin/env bash
# Probe: where the CDER/CBER establishment registration data can be downloaded (read-only, no writes to raw/).
set -u
UA="Mozilla/5.0"
echo "=== DECRS page links"
curl -sS -L -A "$UA" 'https://www.fda.gov/drugs/drug-approvals-and-databases/drug-establishments-current-registration-site' \
  | grep -oiE 'href="[^"]*(media/[0-9]+/download|\.zip|dailymed|drls|decrs)[^"]*"' | sort -u
echo "=== eBER (blood) search page: form + links"
curl -sS -L -A "$UA" 'https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/' | grep -oiE '<form[^>]*>|<a [^>]*href="[^"]*"[^>]*>|<input[^>]*name="[^"]*"[^>]*>|<select[^>]*name="[^"]*"' | head -40
echo "=== HCTERS (tissue) search page: form + inputs"
curl -sS -L -A "$UA" 'https://www.accessdata.fda.gov/scripts/cber/CFAppsPub/tiss/index.cfm' | grep -oiE '<form[^>]*>|<input[^>]*name="[^"]*"[^>]*>|<select[^>]*name="[^"]*"' | head -40
echo "=== shacl_full log tail"
tail -4 /srv/fda-products-kg/logs/shacl_full_2026-10-16.log
