# faers_split_versions.awk -- give the second copy of a FAERS report that openFDA lists twice
# its own IRI (report/<id>-2), in an L1 or L2 Turtle stream (mawk or gawk).
# openFDA serves both copies (old AERS reports without a version number; they differ in
# transmission date). The L1 build gave both the same IRI, so their values merged on one node.
# Each report is one contiguous group of blocks: its child nodes, then the report node itself.
# Occurrences are counted in file order (the sorted partition order of the source). Occurrence
# 1 keeps the base IRI; occurrence n > 1 gets "-n" on the report segment, in every IRI of the group.
# Variables: dups=<file, one report IRI (no angle brackets) per line>,
#            init=<counts carried over from an earlier file>, state=<counts out>, stats=<summary out>
function repl(s, old, new,    out, i) {
  out = ""
  while ((i = index(s, old)) > 0) { out = out substr(s, 1, i - 1) new; s = substr(s, i + length(old)) }
  return out s
}
BEGIN {
  P = "<https://bmedesign.org/fda-drug-event-kg/id/report/"; PL = length(P)
  while ((getline l < dups) > 0) { sub(/[ \t\r]+$/, "", l); gsub(/[<>]/, "", l); if (l != "") DUP[l] = 1 }
  if (init != "") while ((getline l < init) > 0) { split(l, a, "\t"); OCC[a[1]] = a[2] + 0 }
  cur = ""; top = 0; suf = ""
}
substr($0, 1, PL) == P {
  rest = substr($0, PL + 1); e = index(rest, "/"); if (e == 0) e = index(rest, ">")
  rep = substr(rest, 1, e - 1); iri = substr(P, 2) rep
  istop = ($0 == P rep ">")
  if (rep != cur || top) {
    cur = rep; top = 0; suf = ""; groups++
    if (iri in DUP) {
      OCC[iri]++; dupgroups++
      if (OCC[iri] > 1) { suf = "-" OCC[iri]; renamed++; OLD = P rep; OLD2 = substr(OLD, 2); NEW = P rep suf; NEW2 = substr(NEW, 2) }
    }
  }
  if (istop) top = 1
}
{
  if (suf != "") {
    # report IRI followed by "/" or ">" only, so 123_4 never matches inside 123_45
    line = repl($0, OLD2 "/", NEW2 "/"); line = repl(line, OLD2 ">", NEW2 ">")
    if (line != $0) changed++
    print line
  } else print
}
END {
  if (state != "") for (k in OCC) print k "\t" OCC[k] > state
  if (stats != "") print "groups=" groups+0, "dup_groups=" dupgroups+0, "renamed_groups=" renamed+0, "changed_lines=" changed+0 > stats
}
