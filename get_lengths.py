import re
import struct
import subprocess
import sys
from pathlib import Path
from typing import Literal

from suites import SUITE_MAP

STUDY_DIR = Path(
    "/mnt/storage/mgiordan/trace_outputs/champsim_core.1.v1.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v1.,_memory.1.v2.,_tlbs.n.v1."
)

# Anchored for use with str.match after startswith("Heartbeat CPU ")
HEARTBEAT_RE = re.compile(
    r"Heartbeat CPU (\d+) instructions: (\d+) cycles: (\d+) heartbeat IPC"
)
END_TRACE_RE = re.compile(
    r"(?:\*\*\* )?Reached end of trace:\s*\((\d+),\s*\"([^\"]*)\"\)"
)

_canonical_cache: dict[str, str] = {}
# canonical resolved path -> uncompressed size in bytes (None = unknown)
_UNC_BYTES_CACHE: dict[str, int | None] = {}


def canonical_trace_key(path_str: str) -> str:
    c = _canonical_cache.get(path_str)
    if c is None:
        c = str(Path(path_str).resolve())
        _canonical_cache[path_str] = c
    return c


def _trace_unc_cache_key(path: Path) -> str:
    return canonical_trace_key(str(path))


def _parse_xz_robot_list(stdout: str) -> dict[str, int]:
    """Map canonical trace path -> uncompressed size from ``xz -l --robot`` output."""
    out: dict[str, int] = {}
    current_name: str | None = None
    for line in stdout.splitlines():
        if line.startswith("name\t"):
            current_name = line.split("\t", 1)[1]
        elif line.startswith("file\t") and current_name is not None:
            parts = line.split("\t")
            if len(parts) >= 5:
                out[canonical_trace_key(current_name)] = int(parts[4])
            current_name = None
    return out


def _xz_uncompressed_one(path: Path) -> int | None:
    try:
        proc = subprocess.run(
            ["xz", "-l", "--robot", str(path)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    m = _parse_xz_robot_list(proc.stdout)
    return m.get(_trace_unc_cache_key(path))


def prefetch_xz_uncompressed_sizes(paths: list[Path]) -> None:
    """Batch ``xz -l --robot`` so we do not spawn one process per .xz trace."""
    xz_pending = []
    for p in paths:
        if p.suffix.lower() != ".xz":
            continue
        k = _trace_unc_cache_key(p)
        if k not in _UNC_BYTES_CACHE:
            xz_pending.append(p)
    chunk_size = 256
    for i in range(0, len(xz_pending), chunk_size):
        chunk = xz_pending[i : i + chunk_size]
        try:
            proc = subprocess.run(
                ["xz", "-l", "--robot", *[str(p) for p in chunk]],
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            for p in chunk:
                k = _trace_unc_cache_key(p)
                if k not in _UNC_BYTES_CACHE:
                    _UNC_BYTES_CACHE[k] = _xz_uncompressed_one(p)
            continue
        got = _parse_xz_robot_list(proc.stdout)
        for p in chunk:
            k = _trace_unc_cache_key(p)
            if k in got:
                _UNC_BYTES_CACHE[k] = got[k]
            elif k not in _UNC_BYTES_CACHE:
                _UNC_BYTES_CACHE[k] = _xz_uncompressed_one(p)


def uncompressed_trace_bytes(path: Path) -> int | None:
    """Uncompressed byte length without full decompress (best-effort).

    Use this instead of ``stat().st_size`` for compressed traces: instruction count
    is *not* ``compressed_size / RECORD_BYTES``.

    - .xz: metadata via ``xz -l --robot`` (prefer :func:`prefetch_xz_uncompressed_sizes`).
    - .gz: gzip trailer ISIZE (uncompressed mod 2**32 only; unreliable above ~4 GiB).
    - other: ``stat().st_size`` (assumed uncompressed).
    """
    k = _trace_unc_cache_key(path)
    if k in _UNC_BYTES_CACHE:
        return _UNC_BYTES_CACHE[k]
    try:
        if not path.is_file():
            _UNC_BYTES_CACHE[k] = None
            return None
    except OSError:
        _UNC_BYTES_CACHE[k] = None
        return None
    suf = path.suffix.lower()
    if suf == ".xz":
        u = _xz_uncompressed_one(path)
        _UNC_BYTES_CACHE[k] = u
        return u
    if suf == ".gz":
        try:
            with open(path, "rb") as f:
                f.seek(-4, 2)
                (isize,) = struct.unpack("<I", f.read(4))
            n = int(isize)
        except (OSError, struct.error):
            n = None
        _UNC_BYTES_CACHE[k] = n
        return n
    try:
        n = path.stat().st_size
    except OSError:
        n = None
    _UNC_BYTES_CACHE[k] = n
    return n


def approx_instructions_from_trace_file(trace_path: Path, record_bytes: int) -> str | None:
    """Rough instruction count ``uncompressed_bytes // TRACE_RECORD_BYTES`` (full trace, not simulation)."""
    if record_bytes <= 0:
        return None
    unc = uncompressed_trace_bytes(trace_path)
    if unc is None:
        return None
    return str(unc // record_bytes)


def scan_raw_all_first_eot(raw_path: Path) -> dict[str, int | Literal["no_hb"]]:
    """For each trace path, outcome at the *first* EoT line in this file (CPU must match)."""
    last_instr_for_cpu: dict[int, int] = {}
    first_eot: dict[str, int | Literal["no_hb"]] = {}
    try:
        with open(raw_path, "r", errors="replace", buffering=1024 * 1024) as f:
            for line in f:
                if line.startswith("Heartbeat CPU "):
                    m = HEARTBEAT_RE.match(line)
                    if m:
                        last_instr_for_cpu[int(m.group(1))] = int(m.group(2))
                    continue
                if "Reached end of trace" not in line:
                    continue
                m = END_TRACE_RE.search(line)
                if not m:
                    continue
                ckey = canonical_trace_key(m.group(2))
                if ckey in first_eot:
                    continue
                cpu = int(m.group(1))
                first_eot[ckey] = (
                    last_instr_for_cpu[cpu] if cpu in last_instr_for_cpu else "no_hb"
                )
    except OSError as e:
        print(f"WARN: could not open {raw_path}: {e}", file=sys.stderr)
    return first_eot


def collect_suite_outcomes(suite_dir: Path) -> dict[str, str]:
    """One pass per .raw; first file (sorted) that mentions a path’s EoT wins."""
    merged: dict[str, str] = {}
    if not suite_dir.is_dir():
        print(f"WARN: study directory missing: {suite_dir}", file=sys.stderr)
        return merged
    for raw in sorted(suite_dir.glob("*.raw")):
        for path_key, v in scan_raw_all_first_eot(raw).items():
            if path_key in merged:
                continue
            merged[path_key] = (
                "No heartbeat before EoT" if v == "no_hb" else str(v)
            )
    return merged


def main() -> None:
    for suite_name, suite in sorted(SUITE_MAP.items()):
        print(f"Suite: {suite_name}")
        suite_dir = STUDY_DIR / suite_name
        outcomes = collect_suite_outcomes(suite_dir)
        all_trace_paths: list[Path] = []
        for wl in suite.get_workloads():
            for entry in suite.get_traces_and_weights_in_workload(wl):
                all_trace_paths.append(entry[0])
        prefetch_xz_uncompressed_sizes(all_trace_paths)
        for workload in suite.get_workloads():
            traces = suite.get_traces_and_weights_in_workload(workload)
            if not traces:
                continue
            print(f"  Workload: {workload}")
            for entry in traces:
                trace_path = entry[0]
                key = canonical_trace_key(str(trace_path))
                disp = outcomes.get(key, "No EoT")
                approx = approx_instructions_from_trace_file(
                    trace_path, suite.TRACE_RECORD_BYTES
                )
                if approx is not None:
                    print(
                        f"    {trace_path}    {disp}    "
                        f"file≈{approx}_instr (uncompressed÷{suite.TRACE_RECORD_BYTES}B)"
                    )
                else:
                    print(f"    {trace_path}    {disp}")


if __name__ == "__main__":
    main()
