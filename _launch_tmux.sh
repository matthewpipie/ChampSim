#!/bin/bash
set -e
set -x

numcores=500
sleeptime="00h"

for wl in google spec; do
#for wl in spec; do
	for fil in $(ls bin/); do
		#if echo $fil | grep 'bandwidth'; then
			#echo "passing pw for now"
		#else
			echo $fil
			tmux_name=$(date +%s_%N)
			tmux new-session -d -s $tmux_name
			if echo $fil | grep core.4; then
				tmux send-keys -t "$tmux_name" Enter Enter "sleep ${sleeptime}; python3 run_${wl}_on.py bin/$fil $numcores"
			else
				tmux send-keys -t "$tmux_name" Enter Enter "sleep ${sleeptime}; python3 run_${wl}_on1.py bin/$fil $numcores"
			fi
		#fi
	done
done
