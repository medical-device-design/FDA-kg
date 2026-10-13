#!/usr/bin/env bash
# Phase 0 setup for the FDA regulated-products KG family on the build VM.
# Creates the project root next to the device project. Touches nothing in
# /srv/medical-device-kg. Safe to re-run (idempotent, never deletes).
#
# Run on build-vm as <user> (needs sudo once, for /srv):
#   bash setup_vm.sh
set -euo pipefail

ROOT=/srv/fda-products-kg
GROUP=mdkg                      # reuse the device project group
DEVICE_TOOLS=/srv/medical-device-kg/tools
MIN_FREE_GB=15

free_gb=$(df -BG --output=avail /srv | tail -1 | tr -dc '0-9')
echo "Free on /srv: ${free_gb} GB"
if (( free_gb < MIN_FREE_GB )); then
  echo "STOP: under ${MIN_FREE_GB} GB free. Wait for the new data volume." >&2
  exit 1
fi

sudo mkdir -p "$ROOT"
sudo chgrp "$GROUP" "$ROOT"
sudo chmod 2775 "$ROOT"          # setgid so group ownership is inherited

# raw = L0 snapshots (never edited, never published)
# work = unzipped scratch, safe to regenerate
# out  = L1/L2 TTL per graph
for d in raw work out logs manifests repo tools; do
  mkdir -p "$ROOT/$d"
done
for g in fda-compliance-kg fda-substance-kg fda-drug-biologic-kg \
         fda-food-cosmetic-kg fda-animal-health-kg fda-tobacco-kg; do
  mkdir -p "$ROOT/raw/$g" "$ROOT/out/$g"
done

# Reuse the device project's Jena and lakectl rather than installing twice.
for t in "$DEVICE_TOOLS"/*; do
  [ -e "$t" ] || continue
  ln -sfn "$t" "$ROOT/tools/$(basename "$t")"
done

cat > "$ROOT/env.sh" <<EOF
export FDAKG=$ROOT
export PATH=\$FDAKG/tools/bin:\$PATH
EOF

echo "Done. Add 'source $ROOT/env.sh' to ~/.bashrc."
ls -la "$ROOT"
df -h /srv
