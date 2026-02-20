from pathlib import Path
import re
from collections import defaultdict
import json

#srcdir = "/mnt/storage/traces/gtrace_v2_study_results//champsim_core.1.v1.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v1.,_memory.1.v2.,_tlbs.n.v1./"
#outdir = "/mnt/storage/traces/gtrace_v2_study_results//champsim_core.1.v1.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v1.,_memory.1.v2.,_tlbs.n.v1./"
srcdir = "/mnt/storage/traces/spectrace_study/champsim_core.1.v1.,_l1i.n.v1.,_l1d.n.v1.,_l2c.n.v1.,_llc.1.v1.,_memory.1.v2.,_tlbs.n.v1./"
outdir = srcdir

freqs_d = defaultdict(lambda: defaultdict(int))
freqs_i = defaultdict(lambda: defaultdict(int))

def parse_di_string_re(s: str):
    d_map = {}
    i_map = {}

    pattern = re.compile(r'([di])\s(\d+)\s(\d+)')

    for t, a, b in pattern.findall(s):
        a = int(a)
        b = int(b)

        if t == 'd':
            d_map[a] = b
        else:  # t == 'i'
            i_map[a] = b

    return d_map, i_map

workloads = set()
for fil in sorted(Path(srcdir).glob("*.raw")):
    print(fil)
    workload_name = fil.name.split(",")[0]
    workloads |= {workload_name}

    file_freqs_raw = fil.read_text()
    file_freqs_raw = file_freqs_raw.strip().split("\n")[-1]

    d_map, i_map = parse_di_string_re(file_freqs_raw)
    for (cacheline, accesses) in d_map.items():
        freqs_d[workload_name][cacheline] += accesses
    for (cacheline, accesses) in i_map.items():
        freqs_i[workload_name][cacheline] += accesses

for workload in sorted(list(workloads)):
    print(f"Workload {workload}")
    print(f"\tData Lines: {len(freqs_d[workload])}")
    print(f"\tInst Lines: {len(freqs_i[workload])}")

(Path(outdir) / "study_output_d.json").write_text(json.dumps(freqs_d))
(Path(outdir) / "study_output_i.json").write_text(json.dumps(freqs_i))
