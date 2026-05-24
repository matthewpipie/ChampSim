#!/usr/bin/env python3
"""Extract ChampSim simulation times from log files and write a CSV."""

import argparse
import csv
import re
import sys
from pathlib import Path

LOG_DIR = Path(
    "/mnt/storage/mgiordan/trace_outputs/"
    "champsim_core.1.v2.,_l1i.n.v1.prefetcher--eip,"
    "_l1d.n.v1.prefetcher--berti_4kb,_l2c.n.v1.prefetcher--pythia_4kb,"
    "_llc.1.v2.,_memory.1.v2.,_tlbs.n.v1./googleV2/"
)

SIM_COMPLETE_RE = re.compile(
    r"Simulation complete CPU \d+ instructions: \d+ cycles: \d+ "
    r"cumulative IPC: [\d.]+ \(Simulation time: (.+)\)"
)
SIMTIME_RE = re.compile(r"(\d+) hr (\d+) min (\d+) sec")


def parse_simtime_seconds(simtime: str) -> int:
    """Parse '02 hr 04 min 04 sec' into total seconds."""
    match = SIMTIME_RE.fullmatch(simtime.strip())
    if not match:
        raise ValueError(f"unrecognized simulation time format: {simtime!r}")
    hours, minutes, seconds = (int(x) for x in match.groups())
    return hours * 3600 + minutes * 60 + seconds


def parse_filename(file_name):
    ret = {"filename_raw_no_commas": file_name.replace(",", "_")}
    commas = file_name[:-len(".raw")].split(",")
    ret["workload"] = commas[0]
    ret["run_num"] = int(commas[1])
    ret["cores_per_run"] = int(commas[2])
    ret["core_offset"] = int(commas[3])
    ret["warmup_instrs"] = int(commas[4])
    ret["roi_instrs"] = int(commas[5])
    return ret


def extract_simtime(path: Path) -> int | None:
    """Return simulation time in seconds from the last matching line in a log file."""
    simtime = None
    with path.open("r", errors="replace") as f:
        for line in f:
            match = SIM_COMPLETE_RE.search(line)
            if match:
                simtime = parse_simtime_seconds(match.group(1))
    return simtime


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract simulation times from ChampSim log files."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("googleV2_simtimes.csv"),
        help="Output CSV path (default: googleV2_simtimes.csv)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=LOG_DIR,
        help=f"Directory containing ChampSim logs (default: {LOG_DIR})",
    )
    args = parser.parse_args()

    log_dir = args.log_dir
    if not log_dir.is_dir():
        print(f"error: log directory not found: {log_dir}", file=sys.stderr)
        return 1

    fieldnames = [
        "workload",
        "run_num",
        "cores_per_run",
        "core_offset",
        "warmup_instrs",
        "roi_instrs",
        "simtime",
    ]

    log_files = sorted(p for p in log_dir.iterdir() if p.is_file())
    rows: list[dict] = []
    missing: list[str] = []

    for path in log_files:
        simtime = extract_simtime(path)
        if simtime is None:
            missing.append(path.name)
            continue
        row = parse_filename(path.name)
        row["simtime"] = simtime
        rows.append(row)

    with args.output.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {args.output}", file=sys.stderr)
    if missing:
        print(f"warning: no simulation-complete line in {len(missing)} file(s)", file=sys.stderr)
        for name in missing:
            print(f"  {name}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
