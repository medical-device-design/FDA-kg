# Query battery

`common_counts.rq` and `common_provenance.rq` run against every graph (`GRAPH_NS` is replaced
with the graph's namespace by the runner); `<shortname>/q*.rq` are per graph. They are smoke
tests for the joins the graphs promise (application hub, shared package NDC nodes, name-keyed
firms, UNII and CAS links to fda-substance-kg), not an API. Results of the 2026-10-14 run are
summarised in docs/CHANGES_2026-10-14.md; full output stays in the VM logs.
