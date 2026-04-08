import sys
import json
import subprocess
from pathlib import Path 

config_json_files = sys.argv[1:]

full_output = {}
filenames = {}
for fi in config_json_files:
    fi = Path(fi)
    filename = fi.stem
    component = filename.split(".")[0]
    if component in filenames:
        print(f"error: component {component} specified twice")
        sys.exit(1)
    filenames[component] = filename
    fi = json.loads(fi.read_text())
    assert fi["name"].split(",")[0] == filename
    del fi["name"]
    full_output |= fi

executable_name = "champsim_" + ",_".join([filenames[i] for i in ["core", "l1i", "l1d", "l2c", "llc", "memory", "tlbs"]])
full_output["executable_name"] = executable_name

json_out = json.dumps(full_output, indent=2)

#print(json_out)

output_path = f"generated_configs/{executable_name}.json"
Path(output_path).write_text(json_out)

print("Building ", executable_name)
subprocess.run(["./config.sh", output_path], check=True)
subprocess.run(["make", "-j"], check=True)
print("Finished building:", executable_name)
