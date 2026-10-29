#!/usr/bin/env python3
"""
chunk_ttl.py -- stream a (gzipped) Turtle file through consecutive chunks of N node blocks,
prefixes repeated in each, and run a command on every chunk, so a whole graph can be
validated when it does not fit in memory. Every block lands in exactly one chunk (full
coverage, no sampling). Node-level shapes (label, provenance, datatypes, link namespaces)
hold per block, so chunking does not change the verdict. Each chunk is deleted after its
command returns, so disk use stays at one chunk.

Usage: python3 chunk_ttl.py <in.ttl[.gz]> <work_dir> <n_blocks> <command with {} for the chunk path> [--every K]
Prints one line per chunk with the command's last output line, then a summary.
--every K runs the command on every K-th chunk only (chunks 1, 1+K, 1+2K, ...); the other chunks
are streamed past without being written, so a file too big for a full pass can be sampled evenly
from start to end. The summary then says how many chunks were checked out of how many.
"""
import gzip
import subprocess
import sys
from pathlib import Path


def run_chunk(path, cmd):
    r = subprocess.run(cmd.replace("{}", str(path)), shell=True, capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    print(f"{path.name}: {last}", flush=True)
    path.unlink()
    return last


def main(src, work, n, cmd, every=1):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    fh = gzip.open(src, "rt", encoding="utf-8") if src.endswith(".gz") else open(src, encoding="utf-8")
    prefixes, k, blocks, out, results, content = [], 0, 0, None, [], False
    path = None
    with fh:
        for line in fh:
            if line.startswith("@prefix"):
                prefixes.append(line)
                continue
            if out is None:
                k += 1
                path = work / f"chunk_{k:04d}.ttl"
                keep = (k - 1) % every == 0
                out = open(path, "w", encoding="utf-8", newline="\n") if keep else _Sink()
                out.write("".join(prefixes) + "\n")
                blocks, content = 0, False
            if line == "\n" and blocks == 0 and not content:
                continue                      # blank line after the prefixes, not a block end
            out.write(line)
            content = True
            if line == "\n":
                blocks += 1
                if blocks >= n:
                    out.close()
                    if keep:
                        results.append(run_chunk(path, cmd))
                    out = None
    if out is not None:
        out.close()
        if keep:
            results.append(run_chunk(path, cmd))
    print(f"chunks: {k}; checked: {len(results)}; results: " + ", ".join(sorted(set(results))))


class _Sink:
    """A chunk that is streamed past, not written (--every)."""
    def write(self, s):
        pass

    def close(self):
        pass


if __name__ == "__main__":
    ev = int(sys.argv[sys.argv.index("--every") + 1]) if "--every" in sys.argv else 1
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4], ev)
