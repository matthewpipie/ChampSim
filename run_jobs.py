#!/bin/python3
from pathlib import Path
import sys, time
from grouper import grouper
from multiprocessing import Pool
import subprocess
import json
import psutil

JOBS_TODO = Path("jobs_todo/")
JOBS_STARTING = Path("jobs_starting/")
JOBS_WIP = Path("jobs_wip/")
JOBS_DONE = Path("jobs_done/")
JOBS_FAILED = Path("jobs_failed/")
NUM_JOBS_OK = 100

ECHO_ONLY = False
DEBUG = False

TRIGGER = 0

def move_to(old, new, jobname):
    jobfile = old / jobname
    jobfile.rename(new / jobfile.name)

def get_mem_util():
    return psutil.virtual_memory().percent / 100

def work(command_outfile):
    jobname = command_outfile["jobname"]
    try:
        move_to(JOBS_STARTING, JOBS_WIP, jobname)
    except FileNotFoundError:
        print("File {jobname} gone, skipping...")
        TRIGGER += 1
        return
    print(f"Launching {jobname}")
    while get_mem_util() > 0.90:
        time.sleep(60)
    command = command_outfile["command"]
    if ECHO_ONLY:
        command = ["/bin/echo"] + command
        #time.sleep(120)
    err = False
    with open(command_outfile["outfile"], "w+") as outfile:
        with subprocess.Popen(command, stdout = outfile, stderr = subprocess.STDOUT) as proc:
            proc.wait()
            if proc.returncode != 0:
                print("ERROR: on command:")
                print(command_outfile)
                err = True
    # done
    # move jobfile
    move_to(JOBS_WIP, JOBS_DONE if not err else JOBS_FAILED, jobname)
    print(f"Finished: {jobname}")
    TRIGGER += 1

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <number_of_real_cores_to_use>")
        sys.exit(1)

    ncores = int(sys.argv[1])
    TRIGGER = NUM_JOBS_OK

    print("Number of cores: ", ncores)
    with Pool(ncores, maxtasksperchild=1) as pool:
        while True:
            all_next = sorted(list(JOBS_TODO.glob("*")))
            if len(all_next) != 0:
                for f in [all_next[0]]:
                    command_outfile = json.loads(f.read_text())
                    jobname = command_outfile["jobname"]
                    move_to(JOBS_TODO, JOBS_STARTING, jobname)
                    h = pool.apply_async(work, (command_outfile,))
                    if DEBUG:
                        h.get()
                    if TRIGGER:
                        TRIGGER -= 1
                    else:
                        time.sleep(10)
            time.sleep(5)
            if get_mem_util() > 0.97:
                print("ERROR: OOM! Quitting...")
                pool.terminate()
                break

