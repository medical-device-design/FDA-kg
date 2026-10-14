#!/usr/bin/env python3
"""
sample_ttl.py -- the first N node blocks of a (gzipped) Turtle file, prefixes included,
so a shapes run or a query can be tried on a slice of a file too big to load whole.
Blocks are blank-line separated (common.write_block). Children are written before
their parent, so a slice holds whole subtrees plus a few parents cut off at the end,
which is fine for validation (orphans are not violations).

Usage: python3 sample_ttl.py <in.ttl[.gz]> <out.ttl> <n_blocks>
"""
import gzip
import sys


def main(src, dst, n):
    fh = gzip.open(src, "rt", encoding="utf-8") if src.endswith(".gz") else open(src, encoding="utf-8")
    with fh, open(dst, "w", encoding="utf-8", newline="\n") as out:
        blocks = 0
        for line in fh:
            if line.startswith("@prefix"):
                out.write(line)
                continue
            out.write(line)
            if line == "\n":
                blocks += 1
                if blocks >= n:
                    break
    print(f"{dst}: {blocks} blocks")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
