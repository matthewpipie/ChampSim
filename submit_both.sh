#!/bin/bash

set -euo pipefail

csbin="$1"

python3 submit_googleV2_on1.py "$csbin"
python3 submit_spec_on1.py "$csbin"
