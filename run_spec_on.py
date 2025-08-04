#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess

if len(sys.argv) < 3:
    print(f"Usage: {sys.argv[0]} <champsim_executable_paths> <number_of_real_cores_to_use>")
    sys.exit(1)

ncores = int(sys.argv[-1])

BASE_DIR = "/mnt/storage/traces/spectrace/speccpu"

workloads = filter(lambda x: x.is_dir(), Path(BASE_DIR).glob("*"))

WARMUP = 200000000
SIMTIME = 1000000000

N_CORES_PER_PROCESS = 4

ECHO_ONLY = False

commands = []

executables_nopath = sys.argv[1:-1]
for executable_nopath in executables_nopath:
    executable = Path(executable_nopath)
    executable_name = executable.name
    OUT_DIR = f"results/{executable_name}"
    for workload in workloads:
        # get trace files
        trace_files = sorted(list((Path(BASE_DIR) / workload).glob("*.xz")), key = lambda x:
                int(x.name.split("-")[1].split("B.")[0]))
        trace_files = [trace_files[-1]] * N_CORES_PER_PROCESS
        for i, trace_file_batch in enumerate(list(grouper(trace_files, N_CORES_PER_PROCESS, incomplete="strict"))):
            command = []
            command.append(executable.absolute())
            command.extend(["--warmup-instructions", str(WARMUP)])
            command.extend(["--simulation-instructions", str(SIMTIME)])
            command.extend(map(lambda x: x.absolute(), trace_file_batch))

            outname = f"{workload},{i:03},{N_CORES_PER_PROCESS},{i*N_CORES_PER_PROCESS:03}.raw"
            outfile = Path(OUT_DIR) / outname

            commands.append({"command": command, "outfile": outfile.absolute()})

    outdir = Path(OUT_DIR).mkdir(exists_ok=True)


def work(command_outfile):
    print("Launching " + Path(command_outfile["outfile"]).name)
    command = command_outfile["command"]
    if ECHO_ONLY:
        command = ["/bin/echo"] + command
        #time.sleep(120)
    with open(command_outfile["outfile"], "w+") as outfile:
        with subprocess.Popen(command, stdout = outfile, stderr = subprocess.STDOUT) as proc:
            proc.wait()
            if proc.returncode != 0:
                print("ERROR: on command:")
                print(command_outfile)

# ty https://stackoverflow.com/questions/26774781/python-multiple-subprocess-with-a-pool-queue-recover-output-as-soon-as-one-finis
print("Number of tasks: ", len(commands))
print("Number of cores: ", ncores)
with Pool(ncores) as pool:
    pool.map(work, commands)
print("All processes complete!")
