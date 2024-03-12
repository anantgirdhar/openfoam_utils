#!/bin/sh

# dirs="$(ls -d processor* `ls -d 0.* | head -n-1`)"
# echo "dirs:"
# echo "$dirs"
# echo
# rm -rfI $dirs

set -e
set -x

# Get the last time
lastTime=$(basename "$(ls -d processor0/0.* | tail -n1)")
# Save the last time directory
for dir in $(ls -d processor*); do
  mv "$dir/$lastTime" "$dir/$lastTime".bk
done
# Remove all six digit directories
rm -rf processor*/0.0?????
# Restore the last time directory
for dir in $(ls -d processor*); do
  mv "$dir/$lastTime".bk "$dir/$lastTime"
done
