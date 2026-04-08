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
study_mode = bool(int(sys.argv[3]))
filt = sys.argv[4] if len(sys.argv) > 4 else None

executable_name = executable.name

if suite_name == "all":
    suites = list(SUITE_MAP.values())
else:
    suites = [SUITE_MAP[suite_name]]

for suite in suites:
    suite_name = suite.name()
    print(f"Begin suite {suite_name} study={study_mode}")
    if study_mode:
        OUT_DIR = Path("/mnt/storage/mgiordan/trace_analysis/") / executable_name / suite_name
    else:
        OUT_DIR = Path("/mnt/storage/mgiordan/trace_outputs/") / executable_name / suite_name

    workloads = suite.get_workloads()
    assert len(workloads) != 0

    JOBS = Path("jobs_todo")

    ECHO_ONLY = False

    commands = []

    outdir = Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    N_CORES_PER_PROCESS = 1

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
        for i, trace_file_and_weight_and_instrs in enumerate(trace_files):
            trace_file = trace_file_and_weight_and_instrs[0]
            weight = trace_file_and_weight_and_instrs[1]
            warmup = trace_file_and_weight_and_instrs[2]
            simtime = trace_file_and_weight_and_instrs[3]
            flags = trace_file_and_weight_and_instrs[4]
            command = []
            command.append(str(executable.absolute()))
            if study_mode:
                command.extend(["--study-performance"])
            command.extend(["--warmup-instructions", str(warmup)])
            command.extend(["--simulation-instructions", str(simtime)])
            command.extend(flags)
            command.extend([str(trace_file.absolute())])

            name_p = f"{workload},{i:03},{N_CORES_PER_PROCESS},{i*N_CORES_PER_PROCESS:03},{warmup},{simtime}"
            outname = f"{name_p}.raw"
            #jobname = f"{suite_name}---{study_mode}---{executable_name}---{name_p}.job"[:255]
            s = 's' if study_mode else 'z'
            jobname = f"{s}---{executable_name}---{suite_name}---{name_p}.job"[:255]
            outfile = Path(OUT_DIR) / outname

            commands.append({"command": command, "outfile": str(outfile.absolute()), "jobname": jobname, "subtime": datetime.now(timezone.utc).isoformat()})

    print("\tNumber of tasks: ", len(commands))
    for cmd in commands:
        (JOBS / cmd["jobname"]).write_text(json.dumps(cmd))
