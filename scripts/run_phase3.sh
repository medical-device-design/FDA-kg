#!/usr/bin/env bash
# Fetch then build the phase-3 sets in one unattended job.
R=/srv/fda-products-kg
bash $R/repo/fetch_l0_phase3.sh && bash $R/repo/build_phase3.sh
echo "DONE run_phase3"
