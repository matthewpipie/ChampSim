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
STUDY_DIR = Path("/mnt/storage/mgiordan/trace_analysis")

def mean(l):
    return sum(l) / len(l)

def median(l):
    return sorted(l)[len(l)//2]

def parse_study_output(fi):
    ret = {"data": {}, "instructions": {}} 
    isDataL = ["data", "instructions"]
    isDataC = -1
    with open(fi, 'r') as f:
        for line in f:
            line = line.strip()

            match = re.search(r"Warmup Instructions: (\d+)", line)
            if match:
                ret["warmup_instrs"] = int(match.group(1))

            match = re.search(r"Simulation Instructions: (\d+)", line)
            if match:
                ret["sim_instrs"] = int(match.group(1))

            match = re.search(r"Over (\d+) clines, Reuse dists (\d+), num_uses (\d+)", line)
            if match:
                isDataC += 1
                isData = isDataL[isDataC]
                ret[isData]["num_clines"] = int(match.group(1))
                ret[isData]["reuse_dists"] = int(match.group(2))
                ret[isData]["num_uses"] = int(match.group(3))

            match = re.search(r"p(\d+) (\d+)", line)
            if match:
                ret[isData]["p" + match.group(1)] = int(match.group(2))
                if match.group(1) == "99" and isData == "instructions":
                    break
    return ret

def parse_one_output_file(fi, metadata, suite_workload_weights):
    active = 0
    trace_infos = {}
    cores_ret = {}
    caches_ret = {}
    total_missed_reads = {}
    total_hit_reads = {}
    ipc_log = defaultdict(list)
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


            if line.startswith("=== Simulation ==="):
                active = 1
            if active == 0: continue

            match = re.search(r"CPU (\d+) runs (.+)", line)
            if match:
                cpu = int(match.group(1))
                simulation_file_path = match.group(2)
                simulation_file = Path(simulation_file_path)
                weight = suite_workload_weights[metadata["workload"]][simulation_file]
                del suite_workload_weights[metadata["workload"]][simulation_file]
                # first, look for study output of same section
                study_output_file = STUDY_DIR / fi.parent.parent.name / fi.parent.name / fi.name
                study_output = parse_study_output(study_output_file)
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
                                match = re.search(f"Thread {scheduled_coreid} processed (-?\d+) instructions", logline)
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
                                match = re.search(f"Thread {scheduled_coreid} processed (-?\d+) instructions", logline)
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
                    
            match = re.search(r"CPU (\d+) Branch Prediction Accuracy: ([\d.]+)% MPKI: ([\d.]+) Average ROB Occupancy at Mispredict: ([-\d.]+)", line)
            if match:
                assert(int(match.group(1)) == cpu)
                cores_ret[cpu]["branch_predictor"]["branch_prediction_accuracy"] = float(match.group(2)) / 100
                cores_ret[cpu]["branch_predictor"]["branch_MPKI"] = float(match.group(3))
                try:
                    cores_ret[cpu]["branch_predictor"]["average_ROB_occupancy_at_mispredict"] = float(match.group(4))
                except ValueError:
                    cores_ret[cpu]["branch_predictor"]["average_ROB_occupancy_at_mispredict"] = float(0)
            match = re.search(r"^([A-Z_]+): ([\d.]+)", line)
            if match:
                bname = match.group(1)
                cores_ret[cpu]["branch_predictor"][f"mpki_{bname}"] = float(match.group(2))

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
                caches_ret[dest_cache]["source"][cpu]["average_miss_latency"] = average_miss_latency

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
    if isinstance(o, float): return round(o, 4)
    if isinstance(o, dict): return {k: round_floats(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)): return [round_floats(x) for x in o]
    return o

def parse_champsim_config(dir_name):
    ret = {}
    commas = list(map(lambda x: x[1:], dir_name[len("champsim"):].split(",")))
    for comma in commas:
        # champsim_tlbs,_memory,_llc.8M.drrip.no,_l2c.2M.drrip.newbop,_l1i.32K.drrip.next_line,_l1d.48K.drrip.newstride,_core.tage,
        if comma.startswith("tlb"):
            #ret["tlb_config"] = {"raw": comma} 
            dots = comma.split(".")
            ret["tlb_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("memory"):
            #ret["mem_config"] = {"raw": comma}
            dots = comma.split(".")
            ret["mem_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("llc"):
            dots = comma.split(".")
            #ret["llc_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["llc_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("l2c"):
            dots = comma.split(".")
            #ret["l2c_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l2c_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("l1i"):
            dots = comma.split(".")
            #ret["l1i_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l1i_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("l1d"):
            dots = comma.split(".")
            #ret["l1d_config"] = {"raw": comma, "size": dots[1], "replacement": dots[2], "prefetcher": dots[3]}
            ret["l1d_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif comma.startswith("core"):
            dots = comma.split(".")
            #ret["core_config"] = {"raw": comma, "branch_predictor": dots[1]}
            ret["core_config"] = {"raw": comma, "component": dots[0], "ncores": dots[1], "version": dots[2], "base_diff": dots[3]}
        elif len(comma) == 0:
            pass
        else:
            #print("ERROR PARSIN CHAMPSIM CONFIG")
            #print(comma)
            #sys.exit(1)
            return parse_champsim_config("champsim_core.UNKNOWN.UNKNOWN.UNKNOWN,_l1i.UNKNOWN.UNKNOWN.UNKNOWN,_l1d.UNKNOWN.UNKNOWN.UNKNOWN,_l2c.UNKNOWN.UNKNOWN.UNKNOWN,_llc.UNKNOWN.UNKNOWN.UNKNOWN,_memory.UNKNOWN.UNKNOWN.UNKNOWN,_tlbs.UNKNOWN.UNKNOWN.UNKNOWN")
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
    return ret

if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print("syntax: ./file.py <champsim folder(s)>")
        sys.exit(1)

    input_files = sys.argv[1:]

    for suite_name, suite in SUITE_MAP.items():
        res = []
        
        suite_workload_weights = {}
        workloads = suite.get_workloads()
        for workload in workloads:
            traces = suite.get_traces_and_weights_in_workload(workload)
            suite_workload_weights[workload] = {}
            for trace in traces:
                trace_file = trace[0]
                weight = trace[1]
                suite_workload_weights[workload][trace_file] = weight

        for fi in input_files:
            cs_dir = Path(fi)
            if not cs_dir.is_dir():
                raise Exception("needs champsim dir")
            if not "champsim" in cs_dir.name:
                raise Exception("needs champsim dir")
            champsim_config = cs_dir.name
            cfg_dict = parse_champsim_config(champsim_config)
            #print(fi)
            for outfile in (cs_dir / suite_name).glob("*.raw"):
                meta = parse_filename(Path(outfile).name)
                meta |= {"champsim_config": cfg_dict, "suite": suite_name}
                print(f"Parsing: {outfile}")
                #print(f"Parsing: {outfile} with meta {meta}")
                res += [parse_one_output_file(outfile, meta, suite_workload_weights)]
        output = OUT_DIR / (suite_name + ".json")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(round_floats(res), indent=2))
        assert all([len(v) == 0 for k, v in suite_workload_weights.items()]) # ensure all traces actually got ran
