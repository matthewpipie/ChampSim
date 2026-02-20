#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess
import json

if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <champsim_executable_paths>")
    sys.exit(1)

executable = Path(sys.argv[1])
executable_name = executable.name

BASE_DIR = "/mnt/storage/traces/spectrace/speccpu/"
OUT_DIR = f"results_1_spec/{executable_name}"

#workloads = "arizona bravo.a charlie delta merced sierra.a.3 sierra.a.4 sierra.a.6 tahoe tango whiskey yankee".split(" ")
BASE_DIR_PATH = Path(BASE_DIR)
workloads = list(filter(lambda x: x.is_dir(), list(BASE_DIR_PATH.glob("*"))))

WARMUP = 200000000
SIMTIME = 1000000000

JOBS = Path("jobs_todo")

N_CORES_PER_PROCESS = 1

ECHO_ONLY = False

commands = []

for workload in workloads:
    # get trace files
    workload = workload.name
    trace_files_all = sorted(list((Path(BASE_DIR) / workload).glob("*.xz")), key = lambda x:
            int(x.name.split("-")[1].split("B")[0]))
    trace_files = []
    if len(trace_files_all) == 0: continue
    for i in range(N_CORES_PER_PROCESS):
        trace_files.append(trace_files_all[-1])
    for i, trace_file_batch in enumerate(list(grouper(trace_files, N_CORES_PER_PROCESS, incomplete="strict"))):
        command = []
        command.append(str(executable.absolute()))
        command.extend(["--warmup-instructions", str(WARMUP)])
        command.extend(["--simulation-instructions", str(SIMTIME)])
        command.extend(map(lambda x: str(x.absolute()), trace_file_batch))

        name_p = f"{workload},{i:03},{N_CORES_PER_PROCESS},{i*N_CORES_PER_PROCESS:03}"
        outname = f"{name_p}.raw"
        jobname = f"{executable_name}---{name_p}.job"
        outfile = Path(OUT_DIR) / outname

        commands.append({"command": command, "outfile": str(outfile.absolute()), "jobname": jobname})

outdir = Path(OUT_DIR).mkdir(exist_ok=True)

print("Number of tasks: ", len(commands))
for cmd in commands:
    (JOBS / cmd["jobname"]).write_text(json.dumps(cmd))
