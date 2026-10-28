#!/usr/bin/env bash
# Layout peek for round-4 L0 files (read-only). Streams the workbooks.
R=/srv/fda-products-kg; D=${1:-$(date +%F)}
B=fda-drug-biologic-kg; C=fda-compliance-kg; F=fda-food-cosmetic-kg
cd $R/raw
echo "--- IID zip members"; unzip -l $B/fda-inactive-ingredients/$D/iig_october_2026.zip | tail -n +4 | head -5
echo "--- IID change log csv"; unzip -p $B/fda-inactive-ingredients/$D/iig_october_2026.zip Change_Log_Data.csv | head -4 | cut -c1-300
echo "--- compounders txt"; unzip -p $B/fda-ndc-extra/$D/compounders_ndc_directory.zip compounders_ndc_directory.txt | head -3 | cut -c1-400
for f in unfinished_product unfinished_package; do echo "--- $f"; unzip -p $B/fda-ndc-extra/$D/ndc_unfinished.zip $f.txt | head -2 | cut -c1-400; echo "   lines $(unzip -p $B/fda-ndc-extra/$D/ndc_unfinished.zip $f.txt | wc -l)"; done
for f in Products_excluded Packages_excluded; do echo "--- $f"; unzip -p $B/fda-ndc-extra/$D/ndc_excluded.zip $f.txt | head -2 | cut -c1-400; echo "   lines $(unzip -p $B/fda-ndc-extra/$D/ndc_excluded.zip $f.txt | wc -l)"; done
mkdir -p $R/work/peek && unzip -o -q $B/fda-inactive-ingredients/$D/iig_october_2026.zip IIR_OCOMM.xlsx -d $R/work/peek
cd $R/repo/pipeline && python3 - "$D" <<'PY'
import sys, xlsx_min
D = sys.argv[1]; R = "/srv/fda-products-kg"
for p in [f"{R}/work/peek/IIR_OCOMM.xlsx",
          f"{R}/raw/fda-drug-biologic-kg/fda-drug-master-files/{D}/dmf_list_2026q3.xlsx",
          f"{R}/raw/fda-compliance-kg/fda-debarment-list/{D}/debarment_drug_applications.xlsx",
          f"{R}/raw/fda-food-cosmetic-kg/fda-total-diet-study/{D}/tds_fy2018_2020_elements.xlsx"]:
    print("---", p.rsplit("/", 1)[1])
    n = 0
    for i, r in enumerate(xlsx_min.rows(p)):
        n += 1
        if i < 5:
            print("   ", [str(c)[:28] if c is not None else None for c in r[:14]])
    print("    rows", n)
PY
cd $R/raw
for h in $B/fda-outsourcing-facilities/$D/*.html $B/fda-licensed-vaccines/$D/*.html $B/fda-cellular-gene-therapy/$D/*.html $C/fda-clinical-investigator-disqualification/$D/*.xls; do
  echo "--- $h: tables $(grep -ci '<table' "$h"), rows $(grep -ci '<tr' "$h")"
  python3 - "$h" <<'PY'
import re, html, sys
s = open(sys.argv[1], encoding="utf-8", errors="replace").read()
for ti, t in enumerate(re.findall(r"<table\b.*?</table>", s, re.S | re.I)):
    trs = re.findall(r"<tr\b.*?</tr>", t, re.S | re.I)
    print(f"   table {ti}: {len(trs)} rows")
    for tr in trs[:3]:
        cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", tr, re.S | re.I)
        print("     ", [" ".join(html.unescape(re.sub(r"<[^>]+>", " ", c)).split())[:40] for c in cells])
PY
done
rm -rf $R/work/peek; echo "DONE peek_round4"
