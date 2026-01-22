#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess

if len(sys.argv) < 3:
    print(f"Usage: {sys.argv[0]} <champsim_executable_paths> <number_of_real_cores_to_use>")
    sys.exit(1)

executable = Path(sys.argv[1])
ncores = int(sys.argv[2])
executable_name = executable.name


#BASE_DIRs = list(reversed(["/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_cs_1024gb", "/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_cs_3gb", "/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_dr_1024gb", "/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_dr_3gb", "/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_none"]))
BASE_DIRs = list(reversed(["/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_cs_fixed2_1024gb", "/mnt/storage/traces/gtrace_v2_champsim_cachetests_130Minstr_cs_fixed2_3gb"]))

OUT_DIRs = f"myscript_cachetest_results_1/{executable_name}"

#workloads = "arizona bravo.a charlie delta merced sierra.a.3 sierra.a.4 sierra.a.6 tahoe tango whiskey yankee".split(" ")
workloads = "arizona bravo.a charlie delta sierra.a.3 sierra.a.4 sierra.a.6 tahoe tango whiskey".split(" ")

WARMUP = 20000000
SIMTIME = 100000000

N_CORES_PER_PROCESS = 1

ECHO_ONLY = False
NUM_ONLY = False

commands = []

for BASE_DIR in BASE_DIRs:
    OUT_DIR = OUT_DIRs + ",-----" + Path(BASE_DIR).name
    for workload in workloads:
        # get trace files
        trace_files = sorted(list((Path(BASE_DIR) / workload).glob("*.gz")), key = lambda x:
                int(x.name.split("_")[1].split(".")[0]))
        for i, trace_file_batch in enumerate(list(grouper(trace_files, N_CORES_PER_PROCESS, incomplete="strict"))):
            command = []
            command.append(executable.absolute())
            command.extend(["--warmup-instructions", str(WARMUP)])
            command.extend(["--simulation-instructions", str(SIMTIME)])
            command.extend(map(lambda x: x.absolute(), trace_file_batch))

            outname = f"{workload},{i:03},{N_CORES_PER_PROCESS},{i*N_CORES_PER_PROCESS:03}.raw"
            outfile = Path(OUT_DIR) / outname

            commands.append({"command": command, "outfile": outfile.absolute()})

    if not ECHO_ONLY and not NUM_ONLY:
        outdir = Path(OUT_DIR).mkdir()

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
if not NUM_ONLY:
    with Pool(ncores) as pool:
        pool.map(work, commands)
    print("All processes complete!")
