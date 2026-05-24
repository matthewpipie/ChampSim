#!/bin/bash

# 1. Define the directory to monitor
TARGET_DIR="./jobs_todo"

# 2. Check if the directory even exists first
if [ ! -d "$TARGET_DIR" ]; then
    echo "Error: Directory $TARGET_DIR does not exist."
    exit 1
fi

echo "Monitoring $TARGET_DIR... script will resume once it is empty."

# 3. The Loop
# ls -A list all files including hidden ones, but excludes . and ..
# We check if the output of that command is NOT empty
while [ "$(ls -A "$TARGET_DIR")" ]; do
    sleep 300  # Wait 300 seconds before checking again
done

echo "Directory is now empty! Resuming execution..."
# Add your next commands here
