#!/usr/bin/env python3
"""
Parse ChampSim trace conversion logs for "Memory Sharing Statistics" blocks and
emit CSV suitable for pandas (one row per extracted record; use column record_type).

Example log path:
  /mnt/storage/traces/.../arizona/arizona.log

Sections per block:
  - Summary metrics (one row, record_type=summary)
  - Per-thread lines (record_type=thread)
  - Pairwise Jaccard (record_type=pairwise)
  - Threads-per-cacheline histogram (record_type=histogram)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path
from typing import Any, Iterator, TextIO

HEADER_RE = re.compile(
    r"^=== Memory Sharing Statistics for core (\d+)===, instruction info=(\d+)\s*$"
)
SUMMARY_FLAG_RE = re.compile(r"^SUMMARY OF ALL CORES!")
TOTAL_THREADS_RE = re.compile(r"^Total threads:\s+(\d+)\s*$")
CTX_SWITCHES_RE = re.compile(r"^Total context switches:\s+(\d+)\s*$")
UNIQUE_CLINES_RE = re.compile(r"^Total unique cachelines:\s+(\d+)\s*$")
TOTAL_ACCESSES_RE = re.compile(r"^Total accesses:\s+(\d+)\s*$")
SHARED_CLINES_RE = re.compile(
    r"^Shared cachelines:\s+(\d+) \(([\d.]+)%\)\s*$"
)
AVG_THREADS_CLINE_RE = re.compile(r"^Average threads/cline:\s+([\d.]+)\s*$")
AVG_ACC_CLINE_RE = re.compile(r"^Average accesses/cline:\s+([\d.]+)\s*$")
AVG_ACC_THREAD_RE = re.compile(r"^Average accesses/thread:\s+([\d.]+)\s*$")

THREAD_RE = re.compile(
    r"^Thread (\d+): private=(\d+) shared=(\d+) "
    r"\(([\d.]+)% private, ([\d.]+)% shared\) total=(\d+) unique=(\d+)\s*$"
)
PAIRWISE_RE = re.compile(
    r"^Threads (\d+) & (\d+): Jaccard=([\d.]+) \((\d+) shared lines\)\s*$"
)
HIST_RE = re.compile(r"^(\d+) threads -> (\d+) clines\s*$")
END_BLOCK_RE = re.compile(r"^={10,}\s*$")

SECTION_PER_THREAD = "--- Per-thread private vs shared access breakdown ---"
SECTION_PAIRWISE = "--- Pairwise working-set Jaccard overlap ---"
SECTION_HIST = "--- Threads per cacheline histogram ---"


def workload_name(path: Path) -> str:
    """Prefer parent dir name when it matches the log stem (e.g. arizona/arizona.log)."""
    if path.suffix.lower() == ".log" and path.stem == path.parent.name:
        return path.parent.name
    return path.stem


def parse_segments(path: Path) -> Iterator[dict[str, Any]]:
    """
    Yield records as dicts. Each dict includes record_type and segment fields.
    """
    source_path = str(path.resolve())
    wl = workload_name(path)
    segment_index = -1
    core: int | None = None
    instruction_info: int | None = None
    is_aggregate = False

    section: str | None = None
    summary: dict[str, Any] = {}

    def flush_summary() -> Iterator[dict[str, Any]]:
        nonlocal summary
        if not summary:
            return
        row = {
            "record_type": "summary",
            "workload": wl,
            "source_path": source_path,
            "segment_index": segment_index,
            "core": core,
            "instruction_info": instruction_info,
            "is_aggregate_all_cores": is_aggregate,
            **summary,
        }
        summary = {}
        yield row

    with path.open(encoding="utf-8", errors="replace") as f:
        for raw in f:
            line = raw.rstrip("\n")

            m = HEADER_RE.match(line)
            if m:
                for row in flush_summary():
                    yield row
                segment_index += 1
                core = int(m.group(1))
                instruction_info = int(m.group(2))
                is_aggregate = False
                section = None
                summary = {}
                continue

            if segment_index < 0:
                continue

            if SUMMARY_FLAG_RE.match(line):
                is_aggregate = True
                continue

            if line.strip() == SECTION_PER_THREAD:
                for row in flush_summary():
                    yield row
                section = "per_thread"
                continue
            if line.strip() == SECTION_PAIRWISE:
                for row in flush_summary():
                    yield row
                section = "pairwise"
                continue
            if line.strip() == SECTION_HIST:
                for row in flush_summary():
                    yield row
                section = "histogram"
                continue

            if END_BLOCK_RE.match(line):
                for row in flush_summary():
                    yield row
                section = None
                continue

            if section is None:
                m = TOTAL_THREADS_RE.match(line)
                if m:
                    summary["total_threads"] = int(m.group(1))
                    continue
                m = CTX_SWITCHES_RE.match(line)
                if m:
                    summary["total_context_switches"] = int(m.group(1))
                    continue
                m = UNIQUE_CLINES_RE.match(line)
                if m:
                    summary["total_unique_cachelines"] = int(m.group(1))
                    continue
                m = TOTAL_ACCESSES_RE.match(line)
                if m:
                    summary["total_accesses"] = int(m.group(1))
                    continue
                m = SHARED_CLINES_RE.match(line)
                if m:
                    summary["shared_cachelines"] = int(m.group(1))
                    summary["shared_cachelines_pct"] = float(m.group(2))
                    continue
                m = AVG_THREADS_CLINE_RE.match(line)
                if m:
                    summary["avg_threads_per_cline"] = float(m.group(1))
                    continue
                m = AVG_ACC_CLINE_RE.match(line)
                if m:
                    summary["avg_accesses_per_cline"] = float(m.group(1))
                    continue
                m = AVG_ACC_THREAD_RE.match(line)
                if m:
                    summary["avg_accesses_per_thread"] = float(m.group(1))
                    continue
                continue

            if section == "per_thread":
                m = THREAD_RE.match(line)
                if m:
                    yield {
                        "record_type": "thread",
                        "workload": wl,
                        "source_path": source_path,
                        "segment_index": segment_index,
                        "core": core,
                        "instruction_info": instruction_info,
                        "is_aggregate_all_cores": is_aggregate,
                        "thread_id": int(m.group(1)),
                        "private_accesses": int(m.group(2)),
                        "shared_accesses": int(m.group(3)),
                        "pct_private": float(m.group(4)),
                        "pct_shared": float(m.group(5)),
                        "thread_total_accesses": int(m.group(6)),
                        "unique_cachelines": int(m.group(7)),
                    }
                continue

            if section == "pairwise":
                m = PAIRWISE_RE.match(line)
                if m:
                    yield {
                        "record_type": "pairwise",
                        "workload": wl,
                        "source_path": source_path,
                        "segment_index": segment_index,
                        "core": core,
                        "instruction_info": instruction_info,
                        "is_aggregate_all_cores": is_aggregate,
                        "thread_a": int(m.group(1)),
                        "thread_b": int(m.group(2)),
                        "jaccard": float(m.group(3)),
                        "shared_lines": int(m.group(4)),
                    }
                continue

            if section == "histogram":
                m = HIST_RE.match(line)
                if m:
                    yield {
                        "record_type": "histogram",
                        "workload": wl,
                        "source_path": source_path,
                        "segment_index": segment_index,
                        "core": core,
                        "instruction_info": instruction_info,
                        "is_aggregate_all_cores": is_aggregate,
                        "threads_per_cacheline_bin": int(m.group(1)),
                        "cachelines_in_bin": int(m.group(2)),
                    }
                continue

        for row in flush_summary():
            yield row


# Union of all keys we ever emit (stable CSV columns)
ALL_COLUMNS = [
    "record_type",
    "workload",
    "source_path",
    "segment_index",
    "core",
    "instruction_info",
    "is_aggregate_all_cores",
    # summary
    "total_threads",
    "total_context_switches",
    "total_unique_cachelines",
    "total_accesses",
    "shared_cachelines",
    "shared_cachelines_pct",
    "avg_threads_per_cline",
    "avg_accesses_per_cline",
    "avg_accesses_per_thread",
    # thread
    "thread_id",
    "private_accesses",
    "shared_accesses",
    "pct_private",
    "pct_shared",
    "thread_total_accesses",
    "unique_cachelines",
    # pairwise
    "thread_a",
    "thread_b",
    "jaccard",
    "shared_lines",
    # histogram
    "threads_per_cacheline_bin",
    "cachelines_in_bin",
]


def write_csv(rows: Iterator[dict[str, Any]], out: TextIO) -> int:
    w = csv.DictWriter(out, fieldnames=ALL_COLUMNS, extrasaction="ignore")
    w.writeheader()
    n = 0
    for row in rows:
        fill = {k: row.get(k, "") for k in ALL_COLUMNS}
        w.writerow(fill)
        n += 1
    return n


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "inputs",
        nargs="+",
        type=Path,
        help="One or more .log files (trace conversion output)",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output CSV path (default: stdout)",
    )
    args = p.parse_args()

    def all_rows():
        for path in args.inputs:
            if not path.is_file():
                print(f"Not a file: {path}", file=sys.stderr)
                continue
            yield from parse_segments(path)

    rows = all_rows()
    if args.output:
        with args.output.open("w", newline="", encoding="utf-8") as f:
            n = write_csv(rows, f)
        print(f"Wrote {n} rows to {args.output}", file=sys.stderr)
    else:
        n = write_csv(rows, sys.stdout)
        print(f"# {n} rows", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
