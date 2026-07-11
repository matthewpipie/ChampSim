#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess
import json
from datetime import datetime, timezone
from suites import SUITE_MAP

if len(sys.argv) != 4 and len(sys.argv) != 5:
    print(f"Usage: {sys.argv[0]} <champsim_executable_path> <suite> <study_mode> [workload filter]")
    sys.exit(1)

executable = Path(sys.argv[1])
suite_name = sys.argv[2]
study_mode = int(sys.argv[3]) # 0 = off, 1 = yes, 2 = 100M all (no warm)
filt = sys.argv[4] if len(sys.argv) > 4 else None

executable_name = executable.name

def executable_num_cpus(exe_name):
    """Number of cores the binary was compiled for.

    Authoritative source is the generated config's ``num_cores``; fall back to
    the naming convention ``champsim_core.<N>.<ver>...`` (see build.py/CLAUDE.md).
    """
    cfg = Path("generated_configs") / f"{exe_name}.json"
    if cfg.exists():
        try:
            n = json.loads(cfg.read_text()).get("num_cores")
            if n:
                return int(n)
        except (ValueError, KeyError, json.JSONDecodeError):
            pass
    # champsim_core.2.v2.,_l1i... -> ['champsim_core','2','v2',''] -> 2
    try:
        return int(exe_name.split(",")[0].split(".")[1])
    except (IndexError, ValueError):
        return 1

NUM_CPUS = executable_num_cpus(executable_name)

if suite_name == "all":
    suites = list(SUITE_MAP.values())
    input("u sure you want all?")
elif suite_name == "mini":
#SUITES = [SpecSuite(), GoogleSuite(), QualcommSuite(), Parsec21Suite(), GAPSuite(), CloudSuite(), AIMLSuite(), GMSSuite(), LigraSuite()]
    suites = list(map(lambda x: SUITE_MAP[x], ["spec", "googleV2", "qualcomm", "parsec2.1", "gap", "cloudsuite"]))
else:
    suites = [SUITE_MAP[suite_name]]

for suite in suites:
    suite_name = suite.name()
    print(f"Begin suite {suite_name} study={study_mode}")
    if study_mode == 2:
        OUT_DIR = Path("/mnt/storage/mgiordan/trace_analysis_standard/") / executable_name / suite_name
    elif study_mode == 1:
        OUT_DIR = Path("/mnt/storage/mgiordan/trace_analysis/") / executable_name / suite_name
    else:
        assert study_mode == 0
        OUT_DIR = Path("/mnt/storage/mgiordan/trace_outputs/") / executable_name / suite_name

    workloads = suite.get_workloads()
    assert len(workloads) != 0

    JOBS = Path("jobs_todo")

    ECHO_ONLY = False

    commands = []

    outdir = Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    for workload in workloads:
        if filt:
            if filt not in workload:
                print(f"Skipping {workload}")
                continue
            else:
                print(f"Running {workload}")
        # get trace files
        trace_files = list(suite.get_traces_and_weights_in_workload(workload))
        #print(f"\tWorkload {workload}: {len(trace_files)} traces found")
        assert len(trace_files) != 0

        # Group traces into jobs. For suites whose per-workload traces are the
        # concurrent per-core threads of one program (GoogleSuite: whiskey_0000,
        # whiskey_0001, ...), a multicore binary runs them together as ONE job
        # of NUM_CPUS positional traces. Otherwise (simpoints, single-core) each
        # trace is its own single-core job -- the original behavior.
        per_core = getattr(suite, "multicore_workload", lambda: False)()
        if study_mode == 0 and NUM_CPUS > 1 and per_core:
            if len(trace_files) != NUM_CPUS:
                print(f"\tSkipping {workload}: {len(trace_files)} core traces but "
                      f"executable has {NUM_CPUS} cores (need an exact match)")
                continue
            groups = [trace_files]              # one multicore job for the workload
        else:
            groups = [[tf] for tf in trace_files]  # one single-core job per trace

        for i, group in enumerate(groups):
            n_cores = len(group)
            # warmup/simtime/flags are shared across the group's cores
            warmup = group[0][2]
            simtime = group[0][3]
            flags = group[0][4]
            command = []
            command.append(str(executable.absolute()))
            if study_mode:
                command.extend(["--study-performance"])
            if study_mode == 2:
                warmup = 0
                simtime = 100_000_000
            command.extend(["--warmup-instructions", str(warmup)])
            command.extend(["--simulation-instructions", str(simtime)])
            command.extend(flags)
            # DynamoRIO online feed (googleDR): the trace is delivered via
            # --dynamorio-trace-dir in `flags`, and a positional trace file is
            # mutually exclusive with it at the CLI, so don't append one.
            # Otherwise append one positional trace per core in the group.
            if "--dynamorio-trace-dir" not in flags:
                command.extend([str(tf[0].absolute()) for tf in group])

            name_p = f"{workload},{i:03},{n_cores},{i*n_cores:03},{warmup},{simtime}"
            outname = f"{name_p}.raw"
            #jobname = f"{suite_name}---{study_mode}---{executable_name}---{name_p}.job"[:255]
            s = 's' if study_mode else 'y' if "google" in suite_name else 'z'
            jobname = f"{s}---{executable_name}---{suite_name}---{name_p}.job"[:255]
            outfile = Path(OUT_DIR) / outname

            commands.append({"command": command, "outfile": str(outfile.absolute()), "jobname": jobname, "subtime": datetime.now(timezone.utc).isoformat()})

    print("\tNumber of tasks: ", len(commands))
    for cmd in commands:
        (JOBS / cmd["jobname"]).write_text(json.dumps(cmd))
