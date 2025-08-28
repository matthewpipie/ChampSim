import csv
import re
import os
import sys
import json
from pathlib import Path

if len(sys.argv) <= 2:
    print("syntax: ./file.py <input folders> <workload suite source>")
    sys.exit(1)

input_files = sys.argv[1:-1]
suite = sys.argv[-1]
#filter_caches = ["LLC", "L1D", "L2C"]
filter_caches = False

def parse_one_output_file(fi, metadata):
    active = False
    cores_ret = {}
    caches_ret = {}
    total_missed_reads = {}
    total_hit_reads = {}
    cpu = None
    with open(fi, 'r') as f:
        for line in f:
            line = line.strip()

            if line.startswith("Region of Interest Statistics"):
                active = True
            if not active: continue

            match = re.search(r"CPU (\d+) cumulative IPC: ([\d.]+) instructions: (\d+) cycles: (\d+)", line)
            if match:
                cpu = int(match.group(1))
                cores_ret[cpu] = {
                        "core": cpu,
                        "cumulative_IPC": float(match.group(2)),
                        "instructions": int(match.group(3)),
                        "cycles": int(match.group(4)),
                        "branch_predictor": {},
                }
            match = re.search(r"CPU (\d+) Branch Prediction Accuracy: ([\d.]+)% MPKI: ([\d.]+) Average ROB Occupancy at Mispredict: ([\d.]+)", line)
            if match:
                assert(int(match.group(1)) == cpu)
                cores_ret[cpu]["branch_predictor"]["branch_prediction_accuracy"] = float(match.group(2)) / 100
                cores_ret[cpu]["branch_predictor"]["branch_MPKI"] = float(match.group(3))
                cores_ret[cpu]["branch_predictor"]["average_ROB_occupancy_at_mispredict"] = float(match.group(4))
            match = re.search(r"^([A-Z_]+): ([\d.]+)", line)
            if match:
                bname = match.group(1)
                cores_ret[cpu]["branch_predictor"][f"mpki_{bname}"] = float(match.group(2))

            match = re.search(r"^(cpu(\d+)->(\w+)) (\w+)\s+ACCESS:\s+(\d+) HIT:\s+(\d+) MISS:\s+(\d+) MSHR_MERGE:\s+(\d+)", line)
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
            print("ERROR PARSIN CHAMPSIM CONFIG")
            print(comma)
            sys.exit(1)
    return ret

def parse_filename(file_name): 
    ret = {"filename_raw_no_commas": file_name.replace(",","_")}
    commas = file_name[:-len(".raw")].split(",")
    ret["workload"] = commas[0]
    ret["run_num"] = int(commas[1])
    ret["cores_per_run"] = int(commas[2])
    ret["core_offset"] = int(commas[3])
    return ret

res = []
for fi in input_files:
    if not Path(fi).is_dir():
        raise Exception("needs dir")
    champsim_config = Path(fi).name
    cfg_dict = parse_champsim_config(champsim_config)
    for fi2 in Path(fi).glob("*"):
        meta = parse_filename(Path(fi2).name)
        meta |= {"champsim_config": cfg_dict, "suite": suite}
        res += [parse_one_output_file(fi2, meta)]
print(json.dumps(round_floats(res), indent=2))
