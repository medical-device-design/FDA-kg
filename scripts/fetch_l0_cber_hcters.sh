#!/usr/bin/env bash
# Rerun of the tissue registry only, into the same dated snapshot as the blood run (resumable).
set -uo pipefail
R=/srv/fda-products-kg; S=$(ls -d $R/raw/fda-drug-biologic-kg/cber-establishment-registration/20* | sort | tail -1)
python3 $R/repo/pipeline/cber_fetch.py "$S" hcters 1.0
du -sh "$S"; df -h / | tail -1; echo "DONE fetch_l0_cber_hcters"
