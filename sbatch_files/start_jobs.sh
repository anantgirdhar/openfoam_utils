#!/bin/sh

# Start a sequential set of jobs
# This is if it keeps timing out, this will keep it going by creating a chain

set -e

Usage() {
  echo "Usage: $0 <num_jobs> <sfile> [<prev_job_id>]"
}

[ -z $1 ] && Usage && exit 1
[ -z $2 ] && Usage && exit 1

NUMJOBS=$1
SFILE=$2
PREVJOB=$3

if [ -z $PREVJOB ]; then
  echo -n "No previous job provided. Continue? [y|N]: "
  read response
  if [ -z "$response" ] || [ "$response" != "y" ]; then
    exit 2
  fi
fi

echo "Starting jobs after JOBID: $PREVJOB"
for i in `seq 1 $NUMJOBS`; do
  if [ $i -eq 1 ] && [ -z $PREVJOB ]; then
    PREVJOB=$(sbatch --parsable $SFILE)
  else
    PREVJOB=$(sbatch --parsable -d afterany:$PREVJOB $SFILE)
  fi
  echo "Started job $PREVJOB"
done
