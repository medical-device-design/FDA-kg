#!/usr/bin/env bash
# L0 snapshot of the CBER eBER (blood) and eHCTERS (HCT/P) establishment registries by paging the
# public query apps (no bulk download exists). One request per second, resumable. Approved by
# Roche on October 16, 2026.
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); S=$R/raw/fda-drug-biologic-kg/cber-establishment-registration/$D
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free_gb" -ge 12 ] || { echo "ABORT: only ${free_gb}G free"; exit 1; }
mkdir -p "$S"
python3 $R/repo/pipeline/cber_fetch.py "$S" both 1.0
du -sh "$S"; df -h / | tail -1; echo "DONE fetch_l0_cber"
