# one pass: write every report-node subject line to tops, and every block of a duplicated report
# (base IRI or -n IRI) to blocks
BEGIN { P = "<https://bmedesign.org/fda-drug-event-kg/id/report/"; PL = length(P)
  while ((getline l < dups) > 0) { gsub(/[<>\r ]/, "", l); if (l != "") { sub(/.*\/report\//, "", l); DUP[l] = 1 } } }
substr($0, 1, PL) == P {
  rest = substr($0, PL + 1); e = index(rest, "/"); if (e == 0) e = index(rest, ">")
  rep = substr(rest, 1, e - 1); base = rep; sub(/-[0-9]+$/, "", base)
  if ($0 == P rep ">") print rep > tops
  keep = (base in DUP)
}
/^@prefix/ { if (!hdr) print > blocks; next }
{ if (keep) print > blocks }
