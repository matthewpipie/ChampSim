#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess
import json

JOBS_TODO = Path("jobs_todo/")
JOBS_WIP = Path("jobs_wip/")
JOBS_DONE = Path("jobs_done/")

ECHO_ONLY = False
DEBUG = False

def work(command_outfile):
    jobname = command_outfile["jobname"]
    jobfile = JOBS_TODO / jobname
    jobfile.rename(JOBS_WIP / jobfile.name)
    print(f"Launching {jobname}")
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
    # done
    # move jobfile
    jobfile = JOBS_WIP / jobname
    print(f"Finished: {jobname}")
    jobfile.rename(JOBS_DONE / jobfile.name)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <number_of_real_cores_to_use>")
        sys.exit(1)

    ncores = int(sys.argv[1])

    print("Number of cores: ", ncores)
    pool = Pool(ncores)
    while True:
        for f in JOBS_TODO.glob("*"):
            h = pool.apply_async(work, (json.loads(f.read_text()),))
            if DEBUG:
                h.get()
        time.sleep(10)

