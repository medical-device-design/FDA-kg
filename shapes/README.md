# SHACL shapes

Generated, not hand-written: `python3 pipeline/gen_shapes.py shapes/` writes one
`<shortname>.shapes.ttl` per graph from the record table in `gen_shapes.py`. Regenerate after
any change to that table rather than editing the Turtle.

Run on the build VM with Jena: `scripts/shapes_and_queries.sh [graph ...]` validates each graph
(whole when the Turtle is under about 1.3 GB, otherwise a slice of about 1.2 M node blocks from
`pipeline/sample_ttl.py`) and then runs the query battery in `queries/` through TDB2.

Status 2026-10-14: all six graphs conform, 0 violations (see docs/CHANGES_2026-10-14.md).
