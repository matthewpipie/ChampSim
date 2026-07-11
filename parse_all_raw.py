import csv
import re
import os
import sys
import json
from collections import defaultdict
from pathlib import Path
from file_read_backwards import FileReadBackwards
from suites import SUITE_MAP

#filter_caches = ["LLC", "L1D", "L2C"]
filter_caches = False

OUT_DIR = Path("/mnt/storage/mgiordan/trace_parses")
#STUDY_DIR = Path("/mnt/storage/mgiordan/trace_analysis/champsim_core.1.v1.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v1.,_memory.1.v2.,_tlbs.n.v1.")
STUDY_DIR = Path("/mnt/storage/mgiordan/trace_analysis/champsim_core.1.v2.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v2.,_memory.1.v2.,_tlbs.n.v1.")
STUDY_DIR_STANDARD = Path("/mnt/storage/mgiordan/trace_analysis_standard/champsim_core.1.v2.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v2.,_memory.1.v2.,_tlbs.n.v1.")

def mean(l):
    return sum(l) / len(l)

def median(l):
    return sorted(l)[len(l)//2]

def parse_study_output(fi):
    # The study output is optional (e.g. runs without a corresponding trace
    # analysis, such as the live googleDR feed). If the study file/dir isn't
    # present, default to nothing rather than erroring.
    if not Path(fi).exists():
        return {}
    ret = {"branch": {"freq": {}}, "taken_branch": {"freq": {}}, "data": {"lines": {}, "reuse": {}, "reuse_access": {}}, "instruction": {"lines": {}, "reuse": {}}}
    with open(fi, 'r') as f:
        for line in f:
            line = line.strip()

            match = re.search(r"Warmup Instructions: (\d+)", line)
            if match:
                ret["warmup_instrs"] = int(match.group(1))

            match = re.search(r"Simulation Instructions: (\d+)", line)
            if match:
                ret["sim_instrs"] = int(match.group(1))

            match = re.search(r"(branch|taken_branch|data|instruction) (freq|lines|reuse|reuse_access) (\w+) (\d+)$", line)
            if match:
                ret[match.group(1)][match.group(2)][match.group(3)] = int(match.group(4))

            match = re.search(r"(branch|taken_branch|data|instruction) (freq|lines|reuse|reuse_access) p(\d+) (\d+) (\d+)", line)
            if match:
                ret[match.group(1)][match.group(2)]["pp" + match.group(3)] = int(match.group(4))
                ret[match.group(1)][match.group(2)]["pc" + match.group(3)] = int(match.group(5))
    return ret

def parse_one_output_file(fi, metadata, suite_workload_weights):
    active = 0
    trace_infos = {}
    cores_ret = {}
    caches_ret = {}
    total_missed_reads = {}
    total_hit_reads = {}
    ipc_log = defaultdict(list)
    occupancy_log = defaultdict(list)
    warmup_endtime = {}
    cpu = None
    with open(fi, 'r') as f:
        for line in f:
            line = line.strip()

            match = re.search(r"Warmup complete CPU (\d+) instructions: (\d+) cycles: (\d+) cumulative IPC:", line)
            if match:
                cpu = int(match.group(1))
                instrs = int(match.group(2))
                cycles = int(match.group(3))
                warmup_endtime[cpu] = [instrs, cycles]

            match = re.search(r"Heartbeat CPU (\d+) instructions: (\d+) cycles: (\d+) heartbeat IPC", line)
            if match:
                cpu = int(match.group(1))
                instrs = int(match.group(2))
                cycles = int(match.group(3))
                ipc_log[cpu].append([instrs, cycles])
            """
            Heartbeat CPU 0 cache LLC inv: 54832 pf: 6565 data: 2891 instr: 1248
            Heartbeat CPU 0 cache cpu0_DTLB inv: 0 pf: 0 data: 64 instr: 0
            Heartbeat CPU 0 cache cpu0_ITLB inv: 44 pf: 0 data: 0 instr: 20
            Heartbeat CPU 0 cache cpu0_L1D inv: 0 pf: 66 data: 702 instr: 0
            Heartbeat CPU 0 cache cpu0_L1I inv: 0 pf: 56 data: 0 instr: 456
            Heartbeat CPU 0 cache cpu0_L2C inv: 22072 pf: 3801 data: 3813 instr: 3082
            Heartbeat CPU 0 cache cpu0_STLB inv: 1198 pf: 0 data: 318 instr: 20
            """
            match = re.search(r"Heartbeat CPU (\d+) cache (\w+) inv: (\d+) pf: (\d+) data: (\d+) instr: (\d+)", line)
            if match:
                cpu = int(match.group(1))
                if cpu in warmup_endtime:
                    # warmup complete
                    cache = match.group(2)
                    invalid = int(match.group(3))
                    prefetched = int(match.group(4))
                    datas = int(match.group(5))
                    instructs = int(match.group(6))
                    occupancy_log[cache].append([instrs,cycles,invalid,prefetched,datas,instructs])

            if line.startswith("=== Simulation ==="):
                active = 1
            if active == 0: continue

            match = re.search(r"CPU (\d+) runs (.+)", line)
            if match:
                cpu = int(match.group(1))
                simulation_file_path = match.group(2)
                simulation_file = Path(simulation_file_path)
                if simulation_file_path.startswith("dynamorio:"):
                    # Online DynamoRIO feed (googleDR): ChampSim prints a synthetic
                    # per-CPU name ("dynamorio:coreN") because no real per-core trace
                    # file exists -- the whole workload is delivered via
                    # --dynamorio-trace-dir. The suite map holds one real entry per
                    # workload (the trace dir, weight 1.0); the N cores are concurrent
                    # threads of that one program, not simpoints. Credit each core
                    # weight 1.0 and drain the single entry so the completeness check
                    # (all workload maps empty) passes.
                    weight = 1.0
                    wl_map = suite_workload_weights[metadata["workload"]]
                    if wl_map:
                        wl_map.clear()
                    print("\tSource (DR feed): "+ simulation_file_path)
                elif simulation_file not in suite_workload_weights[metadata["workload"]]:
                    weight = 0
                    print("WARN: Source no longer in suite: "+ str(simulation_file))
                else:
                    weight = suite_workload_weights[metadata["workload"]][simulation_file]
                    print("\tSource: "+ str(simulation_file))
                    del suite_workload_weights[metadata["workload"]][simulation_file]
                # first, look for study output of same section
                #study_output_file = STUDY_DIR / fi.parent.parent.name / fi.parent.name / fi.name
                if metadata["champsim_config"]["is_base"]:
                    study_output_file = STUDY_DIR / fi.parent.name / fi.name
                    study_output_standard_file = STUDY_DIR_STANDARD / fi.parent.name / fi.name.replace(str(metadata["warmup_instrs"]) + "," + str(metadata["roi_instrs"]) + ".", "0,100000000.")
                    study_output = parse_study_output(study_output_file)
                    study_output_standard = parse_study_output(study_output_standard_file)
                else:
                    study_output = {}
                    study_output_standard = {}
                # then, look for champsim conversion script output
                match = re.search(r".+(_(\d+)\.champsim\.gz)", line)
                if match:
                    logfile = simulation_file.with_name(simulation_file.name.replace(match.group(1), ".log"))
                    prefix="1.5Binstr"
                    logfile_ideal = str(logfile.absolute()).replace(prefix, "forever")
                    logfile_sharing = str(logfile.absolute()).replace(prefix, "100M_mem_sharing_info")
                    logfile_pt = str(logfile.absolute()).replace(prefix, "forever_withtid2")
                    if "perthread" in str(logfile.absolute()) or True: # tmp, cannot figure out rn
                        logfile_tids = None
                        switch_times = [1]
                    else:
                        logfile_tids = str(logfile.absolute()).replace(prefix, "forever_withtid")
                    scheduled_coreid = int(match.group(2))
                    instructions_processed = None
                    instructions_processed_ideal = None
                    with FileReadBackwards(str(logfile.absolute()), encoding="ascii") as logf:
                        for logline in logf:
                            if logline.startswith("Thread"):
                                match = re.search(f"Thread {scheduled_coreid} processed (-?\\d+) instructions", logline)
                                if match:
                                    instructions_processed = match.group(1)
                                    break
                    if logfile.lstat().st_size == 0:
                        print(f"Empty conversion file: {logfile}", file=sys.stderr)
                        pass
                    elif instructions_processed is None:
                        print(f"Conversion crashed: {logfile}", file=sys.stderr)
                        #raise Exception(fi, line, logfile, scheduled_coreid)

                    with FileReadBackwards(logfile_ideal, encoding="ascii") as logf:
                    #with open(logfile_ideal, "r") as logf:
                        for logline in logf:
                            if logline.startswith("Thread"):
                                match = re.search(f"Thread {scheduled_coreid} processed (-?\\d+) instructions", logline)
                                if match:
                                    instructions_processed_ideal = match.group(1)
                                    break
                    if Path(logfile_ideal).lstat().st_size == 0:
                        print(f"Empty conversion file: {logfile}", file=sys.stderr)
                        pass
                    elif instructions_processed_ideal is None:
                        print(f"Ideal conversion crashed: {logfile}", file=sys.stderr)
                        #raise Exception(fi, line, logfile, scheduled_coreid)
                    if logfile_tids is not None:
                        #print(logfile_tids)
                        switch_times = []
                        with open(logfile_tids, "r") as logf:
                            looking_start = f"***{scheduled_coreid},"
                            for logline in logf:
                                if logline.startswith(looking_start):
                                    if "Processed" in logline: continue
                                    splitt = logline.split(",")
                                    instr = int(splitt[1])
                                    #tid = int(splitt[2])
                                    switch_times.append(instr)
                    if instructions_processed is not None and instructions_processed_ideal is not None:
                        switch_times_diff = []
                        switch_times_diff_ideal = []
                        last = 0
                        for i in range(len(switch_times)-1):
                            switch_times_diff_ideal.append(switch_times[i+1] - switch_times[i])
                            if switch_times[i+1] < int(instructions_processed):
                                last = i+1
                                switch_times_diff.append(switch_times[i+1] - switch_times[i])

                        # close it out
                        if len(switch_times) == 0:
                            switch_times_diff = [0]
                            switch_times_diff_ideal = [0]
                        else:
                            switch_times_diff.append(int(instructions_processed) - switch_times[last])
                            switch_times_diff_ideal.append(int(instructions_processed_ideal) - switch_times[-1])
                    else:
                        switch_times_diff = [0]
                        switch_times_diff_ideal = [0]
                    threads_in_100M_core_info = {}
                    if Path(logfile_sharing).exists():
                        sharing_data = Path(logfile_sharing).read_text()
                        # look line by line for this core number
                        hot = False
                        for line in sharing_data.split("\n"):
                            if hot:
                                if line.startswith("Total threads:"):
                                    threads_in_100M_core_info["total threads"] = int(line.split(":")[1])
                                elif line.startswith("Total context switches:"):
                                    threads_in_100M_core_info["total context switches"] = int(line.split(":")[1])
                                elif line.startswith("Total unique cachelines:"):
                                    threads_in_100M_core_info["total unique cachelines"] = int(line.split(":")[1])
                                elif line.startswith("Total accesses:"):
                                    threads_in_100M_core_info["total accesses"] = int(line.split(":")[1])
                                elif line.startswith("Shared cachelines:"):
                                    threads_in_100M_core_info["shared cachelines raw"] = int(line.split(":")[1].split("(")[0])
                                    threads_in_100M_core_info["shared cachelines percent"] = float(line.split("(")[1].split("%")[0]) / 100 # convert to 0->1 scale
                                elif line.startswith("Average threads/cline:"):
                                    threads_in_100M_core_info["average threads/cline"] = float(line.split(":")[1])
                                elif line.startswith("Average accesses/cline:"):
                                    threads_in_100M_core_info["average accesses/cline"] = float(line.split(":")[1])
                                elif line.startswith("Average accesses/thread:"):
                                    threads_in_100M_core_info["average accesses/thread"] = float(line.split(":")[1])
                                    break
#Total threads:             19
#Total context switches:    121
#Total unique cachelines:   339986
#Total accesses:            39839119
#Shared cachelines:         3803 (1.12%)
#Average threads/cline:     1.02
#Average accesses/cline:    117.18
#Average accesses/thread:   2096795.74

                            elif line.startswith(f"=== Memory Sharing Statistics for core {scheduled_coreid}==="):
                                hot = True


                    trace_infos[cpu] = {
                        "file": simulation_file_path,
                        "weight": weight,
                        "study_output": study_output,
                        "study_output_standard": study_output_standard,
                        "was_converted": True,
                        "conversion_log": str(logfile),
                        "converted_instructions": instructions_processed,
                        "converted_instructions_ideal": instructions_processed_ideal,
                        "ctx_switches": len(switch_times_diff),
                        "ctx_switches_ideal": len(switch_times_diff_ideal),
                        "avg_thread_len": mean(switch_times_diff),
                        "avg_thread_len_ideal": mean(switch_times_diff_ideal),
                        "med_thread_len": median(switch_times_diff),
                        "med_thread_len_ideal": median(switch_times_diff_ideal),
                        "threads_in_100M_core_info": threads_in_100M_core_info,
                        "logfile_pt": logfile_pt,
                    }
                else:
                    trace_infos[cpu] = {
                        "file": simulation_file_path,
                        "weight": weight,
                        "study_output": study_output,
                        "study_output_standard": study_output_standard,
                        "was_converted": False,
                    }
            # /mnt/storage/traces/gtrace_v2_champsim_perthread_1.5Binstr/arizona/16362031984258116688.2763650.memtrace_0000.champsim.gz

            if line.startswith("Region of Interest Statistics"):
                active = 2
            if active == 1: continue

            match = re.search(r"CPU (\d+) cumulative IPC: ([\d.]+) instructions: (\d+) cycles: (\d+)", line)
            if match:
                cpu = int(match.group(1))
                instructions = int(match.group(3))
                cores_ret[cpu] = {
                        "core": cpu,
                        "cumulative_IPC": float(match.group(2)),
                        "instructions": instructions,
                        "cycles": int(match.group(4)),
                        "branch_predictor": {},
                }
                    
            match = re.search(r"CPU (\d+) Branch Prediction Accuracy: ([\d.]+)% MPKI: ([\d.]+) Average ROB Occupancy at Mispredict: ([-\d.]+) BTB Misses: (\d+) Branches: (\d+) Mispredicted: (\d+)", line)
            if match:
                assert(int(match.group(1)) == cpu)
                cores_ret[cpu]["branch_predictor"]["branch_prediction_accuracy"] = float(match.group(2)) / 100
                cores_ret[cpu]["branch_predictor"]["branch_MPKI"] = float(match.group(3))
                try:
                    cores_ret[cpu]["branch_predictor"]["average_ROB_occupancy_at_mispredict"] = float(match.group(4))
                except ValueError:
                    cores_ret[cpu]["branch_predictor"]["average_ROB_occupancy_at_mispredict"] = float(0)
                cores_ret[cpu]["branch_predictor"]["btb_misses"] = int(match.group(5))
                cores_ret[cpu]["branch_predictor"]["branches"] = int(match.group(6))
                cores_ret[cpu]["branch_predictor"]["branches_mispredicted"] = int(match.group(7))
            match = re.search(r"CPU (\d+) TopDown Slots Retiring: (\d+) FrontendBound: (\d+) BackendBound: (\d+) BadSpec: (\d+)", line)
            if match:
                assert(int(match.group(1)) == cpu)
                cores_ret[cpu]["topdown"] = {}
                cores_ret[cpu]["topdown"]["retiring"] = int(match.group(2))
                cores_ret[cpu]["topdown"]["frontend_bound"] = int(match.group(3))
                cores_ret[cpu]["topdown"]["backend_bound"] = int(match.group(4))
                cores_ret[cpu]["topdown"]["bad_spec"] = int(match.group(5))
            match = re.search(r"CPU (\d+) TopDown BackendBound Breakdown ROBFull: (\d+) LQShort: (\d+) SQShort: (\d+)", line)
            if match:
                assert(int(match.group(1)) == cpu)
                cores_ret[cpu]["topdown"]["backend_robfull"] = int(match.group(2))
                cores_ret[cpu]["topdown"]["backend_lqshort"] = int(match.group(3))
                cores_ret[cpu]["topdown"]["backend_sqshort"] = int(match.group(4))
            match = re.search(r"^([A-Z_]+): ([\d.]+) (\d+) (\d+) (\d+) (\d+) (\d+)", line)
            if match:
                bname = match.group(1)
                cores_ret[cpu]["branch_predictor"][bname] = {}
                cores_ret[cpu]["branch_predictor"][bname][f"mpki"] = float(match.group(2))
                cores_ret[cpu]["branch_predictor"][bname][f"branches"] = int(match.group(3))
                cores_ret[cpu]["branch_predictor"][bname][f"misses"] = int(match.group(4))
                cores_ret[cpu]["branch_predictor"][bname][f"bp_only_misses"] = int(match.group(5))
                cores_ret[cpu]["branch_predictor"][bname][f"btb_only_misses"] = int(match.group(6))
                cores_ret[cpu]["branch_predictor"][bname][f"both_misses"] = int(match.group(7))

            match = re.search(r"^CPU \d+ Portion (\w+): (\d+): (\d+)$", line)
            if match:
                portion = match.group(1)
                if "portion_distribution" not in cores_ret[cpu]:
                    cores_ret[cpu]["portion_distribution"] = {}
                if portion not in cores_ret[cpu]["portion_distribution"]:
                    cores_ret[cpu]["portion_distribution"][portion] = {}
                cores_ret[cpu]["portion_distribution"][portion][match.group(2)] = int(match.group(3))

            match = re.search(r"^CPU \d+ Buffer (\w+): (\d+): (\d+)$", line)
            if match:
                buffer = match.group(1)
                if "buffer_distribution" not in cores_ret[cpu]:
                    cores_ret[cpu]["buffer_distribution"] = {}
                if buffer not in cores_ret[cpu]["buffer_distribution"]:
                    cores_ret[cpu]["buffer_distribution"][buffer] = {}
                cores_ret[cpu]["buffer_distribution"][buffer][f"{int(match.group(2)):03d}"] = int(match.group(3))

            match = re.search(r"^(cpu(\d+)->(\w+)) (\w+)\s+ACCESS:\s+(\d+) HIT:\s+(\d+) MISS:\s+(\d+) MISS_MERGE:\s+(\d+)", line)
            if match:
                cpu = int(match.group(2))
                source_to_dest = match.group(1)
                dest_cache = match.group(3)
                dest_cache_type = dest_cache.split("_")[-1]
                if filter_caches and dest_cache_type not in filter_caches: continue
                request_type = match.group(4)
                if dest_cache not in caches_ret:
                    caches_ret[dest_cache] = {
                        "cache_name": dest_cache,
                        "cache_type": dest_cache_type,
                        "source": {},
                        "total_missed_reads": 0,
                        "total_hit_reads": 0,
                        "mshr_distribution": {},
                        "__occupancy_log": occupancy_log[dest_cache],
                    }

                access = int(match.group(5))
                hit = int(match.group(6))
                miss = int(match.group(7))
                mshr_merge = int(match.group(8))

                if request_type in ["LOAD", "RFO"]:
                    caches_ret[dest_cache]["total_missed_reads"] += miss
                    caches_ret[dest_cache]["total_hit_reads"] += hit

                if access != 0:
                    hit_rate = hit / access
                    miss_rate = miss / access
                    mshr_rate = mshr_merge / access
                    mpki = miss / (cores_ret[cpu]["instructions"] / 1000)
                    if cpu not in caches_ret[dest_cache]["source"]:
                        caches_ret[dest_cache]["source"][cpu] = {}
                    caches_ret[dest_cache]["source"][cpu][request_type] = {
                        "access": access,
                        "hit": hit,
                        "miss": miss,
                        "mshr_merge": mshr_merge,
                        "hit_rate": hit_rate,
                        "miss_rate": miss_rate,
                        "mshr_rate": mshr_rate,
                        "mpki": mpki,
                    }
                    if request_type != "TOTAL":
                        caches_ret[dest_cache]["source"][cpu][request_type]["access_proportion"] = access / caches_ret[dest_cache]["source"][cpu]["TOTAL"]["access"]

            match = re.search(r"^(cpu(\d+)->(\w+)) AVERAGE MISS LATENCY: ([\d.]+) cycles", line)
            if match:
                cpu = int(match.group(2))
                source_to_dest = match.group(1)
                dest_cache = match.group(3)
                dest_cache_type = dest_cache.split("_")[-1]
                if filter_caches and dest_cache_type not in filter_caches: continue
                average_miss_latency = float(match.group(4))
                if cpu not in caches_ret[dest_cache]["source"]:
                    caches_ret[dest_cache]["source"][cpu] = {}
                caches_ret[dest_cache]["source"][cpu]["average_miss_latency"] = average_miss_latency

            match = re.search(r"^(\w+) MSHR_OCCUPANCY: (\d+): (\d+)$", line)
            if match:
                cache = match.group(1)
                if cache not in caches_ret:
                    cache_type = cache.split("_")[-1]
                    caches_ret[cache] = {
                        "cache_name": cache,
                        "cache_type": cache_type,
                        "source": {},
                        "total_missed_reads": 0,
                        "total_hit_reads": 0,
                        "mshr_distribution": {},
                        "__occupancy_log": occupancy_log[cache],
                    }
                caches_ret[cache]["mshr_distribution"][f"{int(match.group(2)):03d}"] = int(match.group(3))

            match = re.search(r"^(cpu(\d+)->(\w+)) PREFETCH REQUESTED:\s+(\d+) ISSUED:\s+(\d+) USEFUL:\s+(\d+) USELESS:\s+(\d+)", line)
            if match:
                dest_cache = match.group(3)
                dest_cache_type = dest_cache.split("_")[-1]
                if filter_caches and dest_cache_type not in filter_caches: continue
                pref_req = int(match.group(4))
                pref_iss = int(match.group(5))
                pref_useful = int(match.group(6))
                pref_useless = int(match.group(7))
                if "prefetches" in caches_ret[dest_cache]:
                    #print(dest_cache)
                    #print(caches_ret[dest_cache])
                    assert(caches_ret[dest_cache]["prefetches"]["issued"] == pref_iss)
                    continue
                caches_ret[dest_cache]["prefetches"] = {
                    "requested": pref_req,
                    "issued": pref_iss,
                    "useful": pref_useful,
                    "useless": pref_useless,

                }
    # postprocess cache stuffs
    for (cname, cdata) in caches_ret.items():
        if len(cdata["source"]) == 0: continue
        read_hitrate = 0.0
        try:
            read_hitrate = cdata["total_hit_reads"] / (cdata["total_hit_reads"] + cdata["total_missed_reads"])
        except ZeroDivisionError: pass
        cdata["read_hitrate"] = read_hitrate

        pfdata = cdata["prefetches"]
        accuracy = None
        coverage = None
        try:
            accuracy = pfdata["useful"] / (pfdata["useful"] + pfdata["useless"]) # doesn't count mshr merges
        except ZeroDivisionError: pass
        try:
            coverage = pfdata["useful"] / (pfdata["useful"] + cdata["total_missed_reads"]) # TODO: think more about this. copying from https://github.com/Quangmire/ChampSim/blob/master/get_stats.py#L50
        except ZeroDivisionError: pass

        cdata["prefetches"]["accuracy"] = accuracy
        cdata["prefetches"]["coverage"] = coverage
        
        sumdata = {}
        for sourcecpu, sourcestat in cdata["source"].items():
            for atype, adata in sourcestat.items():
                if atype == "average_miss_latency": continue
                if atype not in sumdata:
                    sumdata[atype] = {"access": 0, "hit": 0, "miss": 0, "mshr_merge": 0}

                sumdata[atype]["access"] += adata["access"]
                sumdata[atype]["hit"] += adata["hit"]
                sumdata[atype]["miss"] += adata["miss"]
                sumdata[atype]["mshr_merge"] += adata["mshr_merge"]

        for atype, adata in sumdata.items():
            access = sumdata[atype]["access"]
            hit = sumdata[atype]["hit"]
            miss = sumdata[atype]["miss"]
            mshr_merge = sumdata[atype]["mshr_merge"]

            hit_rate = hit / access
            miss_rate = miss / access
            mshr_rate = mshr_merge / access
            mpki = miss / (cores_ret[cpu]["instructions"] / 1000)

            adata["hit_rate"] = hit_rate
            adata["miss_rate"] = miss_rate
            adata["mshr_rate"] = mshr_rate
            adata["mpki"] = mpki

            if atype != "TOTAL":
                adata["access_proportion"] = access / sumdata["TOTAL"]["access"]

        cdata["source"]["sum"] = sumdata
        
        def avg(biglist, dim):
            n = 0
            summ = 0
            for item in biglist:
                toavg = item[dim]
                summ += toavg
                n += 1
            return summ / n

        if len(occupancy_log[cname]) == 0:
            cdata["occupancy_avg"] = {"inv": 1, "pf": 0, "data": 0, "instr": 0}
        else:
            cdata["occupancy_avg"] = {
                "inv": avg(occupancy_log[cname], 2),
                "pf": avg(occupancy_log[cname], 3),
                "data": avg(occupancy_log[cname], 4),
                "instr": avg(occupancy_log[cname], 5),
            }

    for (coreid, core) in cores_ret.items():
        core["caches"] = {}
        core["__ipc_log"] = ipc_log[coreid]
        core["warmup_endtime_instrs"] = warmup_endtime[coreid][0]
        core["warmup_endtime_cycles"] = warmup_endtime[coreid][1]
        core["trace_info"] = trace_infos[coreid]
        for (cname, cdata) in caches_ret.items():
            if coreid in cdata["source"]:
                core["caches"][cdata["cache_type"]] = cdata

    ret = {
        "metadata": metadata,
        "cores": cores_ret,
    }

    return ret

def round_floats(o):
    if isinstance(o, float): return round(o, 10)
    if isinstance(o, dict): return {k: round_floats(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [round_floats(x) for x in o]
    return o

def parse_champsim_config(dir_name):
    ret = {}
    commas = list(map(lambda x: x[1:], dir_name[len("champsim"):].split(",")))
    is_base = True
    for comma in commas:
        # champsim_tlbs,_memory,_llc.8M.drrip.no,_l2c.2M.drrip.newbop,_l1i.32K.drrip.next_line,_l1d.48K.drrip.newstride,_core.tage,
        if comma.startswith("tlb"):
            #ret["tlb_config"] = {"raw": comma} 
            dots = comma.split(".")
            ret["tlb_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("memory"):
            #ret["mem_config"] = {"raw": comma}
            dots = comma.split(".")
            ret["mem_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("llc"):
            dots = comma.split(".")
            #ret["llc_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["llc_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("l2c"):
            dots = comma.split(".")
            #ret["l2c_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l2c_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("l1i"):
            dots = comma.split(".")
            #ret["l1i_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l1i_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("l1d"):
            dots = comma.split(".")
            #ret["l1d_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l1d_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif comma.startswith("core"):
            dots = comma.split(".")
            #ret["core_config"] = {"raw": comma, "branch_predictor": dots[1]}
            ret["core_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
            if len(dots[3]) != 0: is_base = False
        elif len(comma) == 0:
            pass
        else:
            #print("ERROR PARSIN CHAMPSIM CONFIG")
            #print(comma)
            #sys.exit(1)
            return parse_champsim_config("champsim_core.UNKNOWN.UNKNOWN.UNKNOWN,_l1i.UNKNOWN.UNKNOWN.UNKNOWN,_l1d.UNKNOWN.UNKNOWN.UNKNOWN,_l2c.UNKNOWN.UNKNOWN.UNKNOWN,_llc.UNKNOWN.UNKNOWN.UNKNOWN,_memory.UNKNOWN.UNKNOWN.UNKNOWN,_tlbs.UNKNOWN.UNKNOWN.UNKNOWN")
    ret["is_base"] = is_base
    return ret

def parse_filename(file_name): 
    ret = {"filename_raw_no_commas": file_name.replace(",","_")}
    #print(file_name)
    commas = file_name[:-len(".raw")].split(",")
    #print(commas)
    ret["workload"] = commas[0]
    ret["run_num"] = int(commas[1])
    ret["cores_per_run"] = int(commas[2])
    ret["core_offset"] = int(commas[3])
    ret["warmup_instrs"] = int(commas[4])
    ret["roi_instrs"] = int(commas[5])
    return ret

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("syntax: ./file.py <champsim folder(s)>")
        sys.exit(1)

    input_files = sys.argv[1:]

    for suite_name, suite in SUITE_MAP.items():
        print(f"Starting suite {suite_name}")
        res = []
        
        workloads = suite.get_workloads()
        for fi in input_files:
            suite_workload_weights = {}

            for workload in workloads:
                traces = suite.get_traces_and_weights_in_workload(workload)
                suite_workload_weights[workload] = {}
                for trace in traces:
                    trace_file = trace[0]
                    weight = trace[1]
                    suite_workload_weights[workload][trace_file] = weight

            cs_dir = Path(fi)
            if not cs_dir.is_dir():
                raise Exception("needs champsim dir")
            if not "champsim" in cs_dir.name:
                raise Exception("needs champsim dir")
            champsim_config = cs_dir.name
            cfg_dict = parse_champsim_config(champsim_config)
            #print(fi)
            res_tmp = []
            seen_workloads = set()
            for outfile in (cs_dir / suite_name).glob("*.raw"):
                meta = parse_filename(Path(outfile).name)
                if meta["workload"] not in workloads:
                    print(f"Workload {meta['workload']} not real! skipping")
                    continue
                seen_workloads.add(meta["workload"])
                meta |= {"champsim_config": cfg_dict, "suite": suite_name}
                print(f"Parsing: {outfile}")
                #print(f"Parsing: {outfile} with meta {meta}")
                res_tmp += [parse_one_output_file(outfile, meta, suite_workload_weights)]

            # Accept this folder's results as long as every workload that actually
            # produced .raw output here was fully consumed (all its simpoints/cores
            # matched and were drained). Workloads with no .raw in this folder are
            # simply absent and must not gate out the ones that did run -- e.g. the
            # googleDR experiment splits one workload per core-count folder instead
            # of running the whole suite in a single folder. For a normal full-suite
            # folder, seen_workloads == every workload, so this is identical to the
            # old "all traces got ran" check.
            incomplete = {w: suite_workload_weights[w] for w in seen_workloads if len(suite_workload_weights[w]) != 0}
            if seen_workloads and not incomplete:
                # every workload that ran was fully covered
                res += res_tmp
            elif seen_workloads:
                # something ran but a workload was missing simpoints/cores
                print(f"*** Missing simpoints/cores for {fi} in:")
                print(incomplete)
        output = OUT_DIR / (suite_name + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(round_floats(res), indent=2))
