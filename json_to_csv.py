import csv
import re
import os
import sys
import json
from pathlib import Path

if len(sys.argv) <= 2:
    print("syntax: ./file.py <input files> <output core file.csv>")
    sys.exit(1)

input_files = sys.argv[1:-1]
coreout = sys.argv[-1]

def flatten(dictionary, parent_key='', separator='.'):
    items = []
    for key, value in dictionary.items():
        new_key = parent_key + separator + key if parent_key else key
        if isinstance(value, dict):
            items.extend(flatten(value, new_key, separator=separator).items())
        else:
            items.append((new_key, value))
    return dict(items)

all_core_output = []
for fil in input_files:
    for run in json.loads(Path(fil).read_text()):
        for cpuid, core in run["cores"].items():
            core["core_local"] = core["core"]
            core["core_global"] = core["core"] + run["metadata"]["core_offset"]
            del core["core"]
            core_output = {}
            core_output |= flatten(run["metadata"], "metadata")
            for cacheid, cache in core["caches"].items():
                cache["from_me"] = cache["source"][cpuid]
                del cache["source"]
            core_output |= flatten(core)
            all_core_output.append(core_output)
#print(all_core_output[0])

def flat_json_to_csv(o):
    ret = ""
    keys = set()
    for item in o:
        keys |= item.keys()
    keys = sorted(list(keys))
    for k in keys:
        if "," in str(k):
            print(f"ERROR: key {k} contains commas")
        ret += k + ","
    ret += "\n"
    for item in o:
        for k in keys:
            if k not in item:
                #print(f"potential KEY ERROR! key {k} not found in {item}")
                ret += "NaN,"
            else:
                if "," in str(item[k]):
                    print(f"ERROR: value {item[k]} contains commas for key {k}")
                ret += str(item[k]) + ","
        ret += "\n"
    return ret

Path(coreout).write_text(flat_json_to_csv(all_core_output))
