from pathlib import Path
import pandas as pd
import sys

# Bytes per trace record in inc/trace_instruction.h (verified via sizeof with g++):
#   input_instr         -> 64 (default ChampSim trace format)
#   cloudsuite_instr    -> 96 (--cloudsuite)


class SpecSuite:
    BASE_DIR = Path("/mnt/storage/traces/spectrace/")
    WARMUP = 50_000_000
    SIMTIME = 250_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def __init__(self):
        pass
    def get_workloads(self):
        return sorted(map(lambda x: x.name, filter(lambda x: x.is_dir(), (self.BASE_DIR / "speccpu").glob("*"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(list((Path(self.BASE_DIR) / "speccpu" / workload).glob("*.xz")), key = lambda x:
            int(x.name.split("-")[1].split("B")[0]))
        output = []
        norm_factor = 0
        for trace in traces:
            my_start = trace.name.split("-")[1].split("B")[0]
            simpoints = (self.BASE_DIR / "weights" / workload / "simpoints.out").read_text()
            try:
                simpt_idx = simpoints.split("\n").index(my_start)
                weights = (self.BASE_DIR / "weights" / workload / "weights.out").read_text()
                weight = float(weights.split("\n")[simpt_idx])
            except ValueError as v:
                print(f"WARN: no weight found for {workload} trace {trace}")
                weight = 0.1 # idk
            if weight < 0.02:
                print(f"INFO: skipping workload {workload} trace {trace} as weight is low ({weight})")
                continue
            output += [[trace, weight, self.WARMUP, self.SIMTIME, []]]
            norm_factor += weight
        for dub in output:
            dub[1] /= norm_factor
        return output
    def name(self):
        return "spec"
    def out_dir(self, executable_name, is_study):
        if is_study:
            return f"/mnt/storage/traces/analysis/spec/{executable_name}"
        else:
            return f"results_1_spec/{executable_name}" #TODO: consider moving to outputs/executable_name/suite_name? and standardize?

class GoogleSuite:
    BASE_DIR = Path("/mnt/storage/traces/gtrace_v2_champsim_1.3Binstr/")
    WARMUP = 50_000_000
    SIMTIME = 500_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def __init__(self):
        pass
    def get_workloads(self):
        return sorted(map(lambda x: x.name, self.BASE_DIR.glob("*")))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted((self.BASE_DIR / workload).glob("*.gz"), key = lambda x:
            int(x.name.split("_")[1].split(".")[0]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "googleV2"
    def out_dir(self, executable_name, is_study):
        if is_study:
            return f"/mnt/storage/traces/analysis/googleV2/{executable_name}"
        else:
            return f"results_googleV2_1/{executable_name}"

class GooglePerThreadSuite:
    BASE_DIR = Path("/mnt/storage/traces/gtrace_v2_champsim_perthread_1.5Binstr/")
    WARMUP = 50_000_000
    SIMTIME = 100_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def __init__(self):
        self._schedule_df = None
    def _get_schedule_df(self):
        if self._schedule_df is None:
            my_csv = "~/schedule_updated.csv"
            self._schedule_df = pd.read_csv(Path(my_csv).expanduser())
        return self._schedule_df
    def get_workloads(self):
        return sorted(map(lambda x: x.name, self.BASE_DIR.glob("*")))
    def get_traces_and_weights_in_workload(self, workload):
        tids_and_traces = list(sorted(map(lambda x: (x.name.split(".")[1], x), (self.BASE_DIR / workload).glob("*.gz"))))
        traces = list(map(lambda x: x[1], tids_and_traces))

        # Build {thread_id: instructions_ran} for this workload.
        # Rows indicate the NEW thread at a core switch point; thread -1 is a sentinel
        # marking the final switch point/end marker for the preceding real thread.
        df = self._get_schedule_df()
        wl_df = df[df["workload"] == workload].copy()
        wl_df = wl_df.sort_values(["core id", "instruction number"], kind="stable")
        wl_df["next_instruction_number"] = wl_df.groupby("core id")["instruction number"].shift(-1)
        wl_df["instructions_ran"] = (
            wl_df["next_instruction_number"] - wl_df["instruction number"]
        ).fillna(0).clip(lower=0)

        # Attribute each interval to the current row's thread, excluding sentinel -1.
        tid_to_instr = (
            wl_df[wl_df["thread id"] != -1]
            .groupby("thread id")["instructions_ran"]
            .sum()
            .astype("int64")
            .to_dict()
        )

        # Convert file-derived tids from str to int for matching.
        trace_tids = list(map(lambda x: int(x[0]), tids_and_traces))
        missing_tids = [tid for tid in trace_tids if tid not in tid_to_instr]
        assert len(missing_tids) == 0, f"Missing tids in schedule map for workload {workload}: {missing_tids}"
        total_instr = sum(map(lambda tid: tid_to_instr[tid], trace_tids))
        assert total_instr > 0, f"Total instructions for workload {workload} must be > 0"

        out = []
        # sweight = 0
        for tid, trace in tids_and_traces:
            tid_instr = tid_to_instr[int(tid)]
            weight = tid_instr / total_instr
            # if weight < 0.01:
                # print(f"SKIPPING {trace}, weight < 1%")
                # continue
                # pass
            # sweight += weight
            out.append([trace, weight, self.WARMUP, self.SIMTIME, []])
        # print(f"TOTAL WEIGHT {sweight}")
        return out
    def name(self):
        return "googleV2perthread"


class QualcommSuite:
    BASE_DIR = Path("/mnt/storage/traces/qualcomm/ipc1_public/")
    WARMUP = 50_000_000
    SIMTIME = 50_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        # Assuming "client_xyz" refers to different cores of the same workload
        return sorted(set(map(lambda x: x.name.split("_")[0], self.BASE_DIR.glob("*.champsimtrace.xz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(self.BASE_DIR.glob(f"{workload}_*.champsimtrace.xz"), key = lambda x:
            int(x.name.split("_")[1].split(".")[0]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "qualcomm"


class Parsec21Suite:
    BASE_DIR = Path("/mnt/storage/traces/parsec2.1/PARSEC-2.1/")
    WARMUP = 50_000_000
    SIMTIME = 200_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split(".")[2], self.BASE_DIR.glob("*.champsimtrace.xz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(self.BASE_DIR.glob(f"parsec_2.1.{workload}.*.champsimtrace.xz"), key = lambda x:
            int(x.name.split("_")[2].split("M")[0]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "parsec2.1"


class GAPSuite:
    BASE_DIR = Path("/mnt/storage/traces/GAP/allGAP/")
    WARMUP = 50_000_000
    SIMTIME = 250_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split("-")[0], self.BASE_DIR.glob("*.trace.gz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(self.BASE_DIR.glob(f"{workload}-*.trace.gz"), key = lambda x:
            int(x.name.split("-")[1].split(".")[0]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "gap"


class CloudSuite:
    BASE_DIR = Path("/mnt/storage/traces/cloudsuite/")
    WARMUP = 50_000_000
    SIMTIME = 250_000_000
    TRACE_RECORD_BYTES = 96  # sizeof(cloudsuite_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split("_")[0], self.BASE_DIR.glob("*.trace.xz"))))
    def get_traces_and_weights_in_workload(self, workload):
        def sort_cs(name):
            parts = name.split("_")
            parts[2] = parts[2].split(".")[0]
            phase = int(parts[1][len("phase"):])
            core = int(parts[2][len("core"):])
            return phase * 10000 + core
        traces = sorted(self.BASE_DIR.glob(f"{workload}_*.trace.xz"), key = lambda x:
                sort_cs(x.name))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, ["--cloudsuite"]], traces))
    def name(self):
        return "cloudsuite"


class AIMLSuite:
    BASE_DIR = Path("/mnt/storage/traces/dpc4/DPC4-Traces-Full/ai-ml/")
    WARMUP = 50_000_000
    SIMTIME = 250_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split(".")[0].split("_")[0], self.BASE_DIR.glob("*.champsimtrace.gz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces1 = sorted(self.BASE_DIR.glob(f"{workload}.*.champsimtrace.gz"), key = lambda x:
            int(x.name.split(".")[-3]))
        traces2 = sorted(self.BASE_DIR.glob(f"{workload}_trace_*.champsimtrace.gz"), key = lambda x:
            int(x.name.split("_")[2].split(".")[0]))
        assert len(traces1) == 0 or len(traces2) == 0
        traces = traces1
        traces.extend(traces2)
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "aiml"

class GMSSuite:
    BASE_DIR = Path("/mnt/storage/traces/dpc4/DPC4-Traces-Full/Graph/GMS/")
    WARMUP = 50_000_000
    SIMTIME = 200_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split(".")[1], self.BASE_DIR.glob("*.champsimtrace.gz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(self.BASE_DIR.glob(f"gms.{workload}.*.champsimtrace.gz"), key = lambda x:
            int(x.name.split(".")[3].split("-")[1]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "gms"


class LigraSuite:
    BASE_DIR = Path("/mnt/storage/traces/dpc4/DPC4-Traces-Full/Graph/Ligra/")
    WARMUP = 50_000_000
    SIMTIME = 200_000_000
    TRACE_RECORD_BYTES = 64  # sizeof(input_instr)
    def get_workloads(self):
        return sorted(set(map(lambda x: x.name.split(".")[0].split("_")[1], self.BASE_DIR.glob("*.champsimtrace.xz"))))
    def get_traces_and_weights_in_workload(self, workload):
        traces = sorted(self.BASE_DIR.glob(f"ligra_{workload}.*.champsimtrace.xz"), key = lambda x:
            int(x.name.split(".")[-4].split("_")[1].split("M")[0]))
        return list(map(lambda x: [x, 1.0 / len(traces), self.WARMUP, self.SIMTIME, []], traces))
    def name(self):
        return "ligra"


SUITES = [SpecSuite(), GoogleSuite(), GooglePerThreadSuite(), QualcommSuite(), Parsec21Suite(), GAPSuite(), CloudSuite(), AIMLSuite(), GMSSuite(), LigraSuite()]
SUITE_MAP = {x.name(): x for x in SUITES}

if __name__ == "__main__":
    sortem = len(sys.argv) == 2
    wln = 0
    trn = 0
    for k, v in SUITE_MAP.items():
        wls = v.get_workloads()
        print(f"Suite {k} ({len(wls)} workloads)")
        trnl = 0
        for wl in wls:
            wln = wln + 1
            traces = v.get_traces_and_weights_in_workload(wl)
            print(f"\tWorkload {wl} ({len(traces)} traces)")
            if sortem:
                traces.sort(key=lambda x: x[1], reverse=True)
            cumweight = 0
            for trace in traces:
                trn = trn + 1
                trnl = trnl + 1
                file = trace[0]
                weight = trace[1]
                warmup = trace[2]
                simtime = trace[3]
                flags = trace[4]
                cumweight += weight
                print(f"\t\t[{weight} {cumweight}] Trace {file} (warmup {warmup} simtime {simtime})")
        print(f"Suite {k} end, ({len(wls)} workloads) with ({trnl} traces)")
    print(f"Total suites: {len(SUITE_MAP.items())}")
    print(f"Total workloads: {wln}")
    print(f"Total traces: {trn}")
