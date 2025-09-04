#!/bin/bash
set -e
set -x

numcores=24

for fil in $(ls bin/); do
	if echo $fil | grep 'bandwidth'; then
		echo "passing pw for now"
	else
		echo $fil
		tmux_name=$(date +%s_%N)
		tmux new-session -d -s $tmux_name
		if echo $fil | grep core.4; then
			tmux send-keys -t "$tmux_name" Enter Enter "python3 run_google_on.py bin/$fil $numcores"
		else
			tmux send-keys -t "$tmux_name" Enter Enter "python3 run_google_on1.py bin/$fil $numcores"
		fi
	fi
done
