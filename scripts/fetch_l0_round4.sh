#!/usr/bin/env bash
# L0 round 4: official files and single-table pages found on October 27, 2026. Dated snapshots,
# SOURCE_URL and SHA256SUMS per source, never overwrite. Prints a layout summary at the end.
set -uo pipefail
R=/srv/fda-products-kg; D=$(date +%F); UA="Mozilla/5.0"
free_gb=$(df -BG --output=avail / | tail -1 | tr -dc 0-9); [ "$free_gb" -ge 150 ] || { echo "ABORT: only ${free_gb}G free"; exit 1; }
get() { # graph source url outname pageurl
  local dest=$R/raw/$1/$2/$D; mkdir -p "$dest"
  if [ -s "$dest/$4" ]; then echo "skip $2/$4"; else
    curl -fsSL -A "$UA" --retry 3 -o "$dest/$4" "$3" && echo "ok $2/$4 $(du -h "$dest/$4" | cut -f1)" || echo "FAILED $2/$4"
  fi
  grep -qxF "$5" "$dest/SOURCE_URL" 2>/dev/null || printf '%s\n%s\n' "$5" "$3" >> "$dest/SOURCE_URL"
  (cd "$dest" && sha256sum $(ls | grep -vE '^(SHA256SUMS|SOURCE_URL)$') > SHA256SUMS)
}
B=fda-drug-biologic-kg; C=fda-compliance-kg; F=fda-food-cosmetic-kg
get $B fda-inactive-ingredients 'https://www.fda.gov/media/195788/download?attachment' iig_october_2026.zip 'https://www.fda.gov/drugs/drug-approvals-and-databases/inactive-ingredients-database-download'
get $B fda-drug-master-files 'https://www.fda.gov/media/192069/download?attachment' dmf_list_2026q3.xlsx 'https://www.fda.gov/drugs/drug-master-files-dmfs/list-drug-master-files-dmfs'
get $B fda-ndc-extra 'https://www.accessdata.fda.gov/cder/ndc_unfinished.zip' ndc_unfinished.zip 'https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory'
get $B fda-ndc-extra 'https://www.accessdata.fda.gov/cder/ndc_excluded.zip' ndc_excluded.zip 'https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory'
get $B fda-ndc-extra 'https://www.accessdata.fda.gov/cder/compounders_ndc_directory.zip' compounders_ndc_directory.zip 'https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory'
get $B fda-outsourcing-facilities 'https://www.fda.gov/drugs/human-drug-compounding/registered-outsourcing-facilities' registered_outsourcing_facilities.html 'https://www.fda.gov/drugs/human-drug-compounding/registered-outsourcing-facilities'
get $B fda-licensed-vaccines 'https://www.fda.gov/vaccines-blood-biologics/vaccines/vaccines-licensed-use-united-states' vaccines_licensed.html 'https://www.fda.gov/vaccines-blood-biologics/vaccines/vaccines-licensed-use-united-states'
get $B fda-cellular-gene-therapy 'https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/approved-cellular-and-gene-therapy-products' approved_cgt_products.html 'https://www.fda.gov/vaccines-blood-biologics/cellular-gene-therapy-products/approved-cellular-and-gene-therapy-products'
get $C fda-debarment-list 'https://www.fda.gov/media/185848/download?attachment' debarment_drug_applications.xlsx 'https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/compliance-actions-and-activities/fda-debarment-list-drug-product-applications'
get $C fda-clinical-investigator-disqualification 'https://www.accessdata.fda.gov/scripts/sda/sdExportData.cfm?sd=clinicalinvestigatorsdisqualificationproceedings&exportType=msexcel' disqualification_proceedings.xls 'https://www.accessdata.fda.gov/scripts/sda/sdNavigation.cfm?sd=clinicalinvestigatorsdisqualificationproceedings'
get $F fda-total-diet-study 'https://www.fda.gov/media/159750/download?attachment' tds_fy2018_2020_elements.txt 'https://www.fda.gov/food/fda-total-diet-study-tds/fda-total-diet-study-tds-results'
get $F fda-total-diet-study 'https://www.fda.gov/media/174926/download?attachment' tds_fy2018_2020_radionuclides.txt 'https://www.fda.gov/food/fda-total-diet-study-tds/fda-total-diet-study-tds-results'
get $F fda-total-diet-study 'https://www.fda.gov/media/159749/download?attachment' tds_fy2018_2020_elements.xlsx 'https://www.fda.gov/food/fda-total-diet-study-tds/fda-total-diet-study-tds-results'
df -h / | tail -1; echo "DONE fetch_l0_round4 (layouts: scripts/peek_round4.sh)"
