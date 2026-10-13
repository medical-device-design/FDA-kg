#!/usr/bin/env bash
# Fetch all Purple Book monthly CSVs (80 files, < 1 MB each) into one dated snapshot,
# then build the four table sources and the gzipped animal-event rebuild. Under nohup.
set -uo pipefail
R=/srv/fda-products-kg; P=$R/repo/pipeline; RIOT=$R/tools/apache-jena-5.2.0/bin/riot
STAMP=$(date -u +%F)
cd "$P"; python3 fda_iri.py && python3 mapper.py || exit 1

PB=$R/raw/fda-drug-biologic-kg/fda-purplebook-all/$STAMP
if [ ! -f "$PB/SHA256SUMS" ]; then
  mkdir -p "$PB"
  curl -sSL --max-time 60 https://purplebooksearch.fda.gov/downloads \
    | grep -oiE '(https:)?//www\.accessdata\.fda\.gov/drugsatfda_docs/PurpleBook/[^" ]*\.csv' \
    | sed 's#^//#https://#' | sort -u > "$PB/urls.txt"
  echo "purple book csv urls: $(wc -l < "$PB/urls.txt")"
  while read -r u; do
    f="$PB/$(echo "$u" | sed -E 's#.*/PurpleBook/([0-9]{4})/purplebook-search-([A-Za-z]+)-data-download\.csv#\1-\2#' | tr 'A-Z' 'a-z').csv"
    curl -fSsL --retry 4 --retry-delay 5 "$u" -o "$f.part" && mv "$f.part" "$f" || echo "FAILED $u"
  done < "$PB/urls.txt"
  (cd "$PB" && sha256sum *.csv > SHA256SUMS); echo "ok purple book $(ls $PB/*.csv | wc -l) files"
fi

run() {  # source snapshot out
  echo "=== $1"; /usr/bin/time -f "   time %es  peakRAM %MKB" python3 l1_tables.py "$1" "$2" "$3" || { echo "FAILED $1"; return; }
  "$RIOT" --validate --count "$3" 2>&1 | tail -1; ls -la "$3" | awk '{print "   size", $5}'
}
latest() { ls -d $1/*/ | sort | tail -1; }
run drugsatfda      "$(latest $R/raw/fda-drug-biologic-kg/fda-drugsatfda-files)" $R/out/fda-drug-biologic-kg/drugsatfda_files.ttl
run orangebook      "$(latest $R/raw/fda-drug-biologic-kg/fda-orangebook-files)" $R/out/fda-drug-biologic-kg/orangebook_files.ttl
run purplebook      "$PB"                                                         $R/out/fda-drug-biologic-kg/purplebook.ttl
run warning-letters "$(latest $R/raw/fda-compliance-kg/fda-warning-letters)"      $R/out/fda-compliance-kg/warning_letters.ttl

echo "=== animal events, gzipped rebuild"
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc '0-9'); (( free_gb >= 4 )) || { echo "STOP: ${free_gb} GB free"; exit 1; }
snap=$(latest $R/raw/fda-animal-health-kg/openfda-animalandveterinary-event)
/usr/bin/time -f "   time %es  peakRAM %MKB" python3 l1_openfda_any.py animalandveterinary/event "$snap" $R/out/fda-animal-health-kg/animal_event.ttl.gz
"$RIOT" --validate --count $R/out/fda-animal-health-kg/animal_event.ttl.gz 2>&1 | tail -1
ls -la $R/out/fda-animal-health-kg/
echo "DONE tables + animal gz"; df -h / | tail -1
