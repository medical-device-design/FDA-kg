#!/usr/bin/env bash
# One-step upload of the seven graphs to lakeFS, develop branch only.
#   upload_lakefs.sh --dry-run    list every file, size, destination; check the server, the repos and
#                                 the develop branches; upload nothing
#   upload_lakefs.sh --upload     upload (needs the PI's go-ahead); no commit, no merge, no tag
# Never run without one of the two flags. Credentials come from lakectl's own config file and are
# never read, printed or logged here. MedDRA-derived files are excluded by name (license pending).
set -uo pipefail
R=/srv/fda-products-kg; O=$R/out; M=$R/manifests; L=$R/logs
LAKECTL="$R/tools/lakectl --config /srv/medical-device-kg/.lakectl.yaml"
BRANCH=develop
GRAPHS="fda-substance-kg fda-compliance-kg fda-drug-biologic-kg fda-food-cosmetic-kg fda-animal-health-kg fda-tobacco-kg fda-drug-event-kg"
MODE=${1:-}
[ "$MODE" = "--dry-run" ] || [ "$MODE" = "--upload" ] || { echo "usage: $0 --dry-run | --upload"; exit 2; }
STAMP=$(date +%Y-%m-%d_%H%M); mkdir -p $M $L
PLAN=$M/upload_plan_$STAMP.tsv; LOG=$L/upload_lakefs_$STAMP.log
excluded() { case "$(basename "$1")" in meddra_*|l2_meddra_*|*.report.txt|*.unmapped.tsv) return 0;; esac; return 1; }

exec > >(tee -a "$LOG") 2>&1
echo "== $MODE $STAMP"
echo "-- server"; $LAKECTL repo list >/dev/null 2>&1 && echo "lakectl: server reachable" || { echo "lakectl: cannot reach the server or list repos (check VPN / config)"; exit 1; }
printf "graph\tfile\tbytes\tdestination\n" > $PLAN
total=0; n=0; missing_repo=0; missing_branch=0
for g in $GRAPHS; do
  if $LAKECTL repo list 2>/dev/null | grep -qw "$g"; then
    repo_ok=yes
    if $LAKECTL branch list "lakefs://$g" 2>/dev/null | grep -qw "$BRANCH"; then br_ok=yes; else br_ok=no; missing_branch=$((missing_branch+1)); fi
  else repo_ok=no; br_ok=no; missing_repo=$((missing_repo+1)); fi
  echo "-- $g: repo=$repo_ok branch $BRANCH=$br_ok"
  for f in $O/$g/*.ttl $O/$g/*.ttl.gz; do
    [ -f "$f" ] || continue
    if excluded "$f"; then echo "   skip (licensed) $(basename $f)"; continue; fi
    b=$(stat -c %s "$f"); total=$((total+b)); n=$((n+1))
    printf "%s\t%s\t%s\tlakefs://%s/%s/%s\n" "$g" "$(basename $f)" "$b" "$g" "$BRANCH" "$(basename $f)" >> $PLAN
    printf "   %-45s %9.2f GB -> lakefs://%s/%s/%s\n" "$(basename $f)" "$(echo "$b/1073741824" | bc -l)" "$g" "$BRANCH" "$(basename $f)"
  done
done
echo "-- $n files, $(echo "scale=1; $total/1073741824" | bc) GB; plan: $PLAN"
if [ "$MODE" = "--dry-run" ]; then echo "DRY RUN: nothing uploaded"; exit 0; fi
if [ $missing_repo -gt 0 ] || [ $missing_branch -gt 0 ]; then echo "ABORT: $missing_repo repos and $missing_branch develop branches missing"; exit 1; fi
echo "-- uploading ($(date))"
fail=0
tail -n +2 $PLAN | while IFS=$'\t' read -r g f b dest; do
  src=$O/$g/$f
  sha=$(sha256sum "$src" | cut -c1-64)
  if $LAKECTL fs upload "$dest" --source "$src"; then
    echo "   ok   $g/$f  sha256 $sha"
  else
    echo "   FAIL $g/$f"; fail=1
  fi
done
echo "-- uploaded, nothing committed ($(date)). Commits on $BRANCH wait for the PI."
echo "DONE upload_lakefs"
