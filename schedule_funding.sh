#!/bin/bash

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Change to the script directory
cd "$SCRIPT_DIR"

# Get current date information
CURRENT_DAY=$(date +%d)
CURRENT_DOW=$(date +%u)  # 1-7, where 1 is Monday

# Check if it's the first of the month
if [ "$CURRENT_DAY" = "01" ]; then
    python3 loor_funding.py --schedule monthly
fi

# Check if it's Monday
if [ "$CURRENT_DOW" = "1" ]; then
    python3 loor_funding.py --schedule weekly
fi 