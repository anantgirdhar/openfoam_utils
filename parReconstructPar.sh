#!/bin/bash

set -e

echo "
      K. Wardle 6/22/09, modified by H. Stadler Dec. 2013, minor fix Will Bateman Sep 2014.
      Further modified by Anant Girdhar December 2023.
      bash script to run reconstructPar in pseudo-parallel mode
      by breaking time directories into multiple ranges
     "

USAGE="
USAGE: $(basename $0) -n NP [-t tstart:tstop] [-f fields] [-o logfile] [-A]
  -n (Number of processors)
  -t (Times) is optional, times given in the form tstart:tstop
  -f (Fields) is optional, fields given in the form T,U,p; option is passed on to reconstructPar
  -A (force All) is optional, forces reconstruction even if the reconstructed directory already exists
  -o (Output) is optional, creates a log file
"

#TODO: add flag to trigger deletion of original processorX directories after successful reconstruction

# At first check whether any flag is set at all, if not exit with error message
if [ $# == 0 ]; then
    echo "$USAGE"
    exit 1
fi

# Use getopts to pass the flags to variables
while getopts ":n:t:f:o:A" opt; do
  case $opt in
    n) [ -n "$OPTARG" ] && NPROCS=$OPTARG ;;
    t)
      if [ -n "$OPTARG" ]; then
        tLowUser=$(echo $OPTARG | cut -d ':' -f1)
        tHighUser=$(echo $OPTARG | cut -d ':' -f2)
      fi
      ;;
    f) [ -n "$OPTARG" ] && FIELDS=$(echo "$OPTARG" | sed 's/,/ /g') ;;
    o) [ -n "$OPTARG" ] && LOGFILE="$OPTARG" ;;
    A) FORCE="yes" ;;
    :) echo "Option $OPTARG requires an argument." >&2 && echo "$USAGE" >&2 && exit 1 ;;
    \?) echo "$USAGE" >&2 && exit 1 ;;
  esac
done

# check whether the number of jobs has been passed over, if not exit with error message
[ -z $NPROCS ] && echo "Number of processors not specified." && echo "$USAGE" && exit 1

APPNAME="reconstructPar"

# Figure out what times are available
tLowReconstructed=$(ls -d [0-9]* | sort -g | head -1)
tHighReconstructed=$(ls -d [0-9]* | sort -gr | head -1)
tLowDecomposed=$(ls processor0 -1v | sed '/constant/d' | sort -g | head -1)
tHighDecomposed=$(ls processor0 -1v | sed '/constant/d' | sort -gr | head -1)

# Now figure out what times should be reconstructed

# Start by assuming that we're going to reconstruct all times in the decomposed directories and then adjust from there
tLow=$tLowDecomposed
tHigh=$tHighDecomposed
nTimes=$(ls -d processor0/[0-9]*/ | wc -l)
nLow=1
nHigh=$nTimes

# Start adjusting based on user input if available
if [ -n $tLowUser ] || [ -n $tHighUser ]; then
  # Make sure that we have both low and high values
  [ -z $tLowUser ] && tLowUser=$tLowDecomposed
  [ -z $tHighUser ] && tHighUser=$tHighDecomposed
  # Now sanity check the values
  if [ $(echo "$tLowUser > $tHighDecomposed" | bc) -eq 1 ]; then
    echo "Error: tstart ($tLowUser) > tMax ($tHighDecomposed)"
    echo "$USAGE"
    exit 2
  elif [ $(echo "$tHighUser < $tLowDecomposed" | bc) -eq 1 ]; then
    echo "Error: tstop ($tHighUser) < tMin ($tLowDecomposed)"
    echo "$USAGE"
    exit 2
  elif [ $(echo "$tLowUser > $tHighUser" | bc) -eq 1 ]; then
    echo "Error: tstart ($tLowUser) > tstop ($tHighUser)"
    echo "$USAGE"
    exit 2
  fi
  # Now adjust the values until the user specs are satisfied
  while [ $(echo "$tLow < $tLowUser" | bc) == 1 ]; do
    let nLow=$nLow+1
    tLow=$(ls processor0 -1v | sed '/constant/d' | sort -g | sed -n "$nLow"p)
    [ -z "$tLow" ] && echo "Unfortunate error because tLow became too high." && exit 5
  done
  while [ $(echo "$tHigh > $tHighUser" | bc) == 1 ]; do
    let nHigh=$nHigh-1
    tHigh=$(ls processor0 -1v | sed '/constant/d' | sort -g | sed -n "$nHigh"p)
    [ -z "$tHigh" ] && echo "Unfortunate error because tHigh became too small." && exit 5
  done
fi


# Next adjust based on the time directories that have already been reconstructed if we're not forcing all
if ! [ "$FORCE" == "yes" ]; then
  while [ $(echo "$tLow <= $tHighReconstructed" | bc) == 1 ]; do
    let nLow=$nLow+1
    tLow=$(ls processor0 -1v | sed '/constant/d' | sort -g | sed -n "$nLow"p)
    [ -z "$tLow" ] && echo "Unfortunate error because tLow became too high." && exit 5
  done
fi

# Now it's possible that there is nothing left to reconstruct
# If there isn't, then we're done
if [ $(echo "$tLow > $tHigh" | bc) == 1 ]; then
  echo "
  Error: No times left to reconstruct based on the provided values.
  tstart, tstop: $tLowUser, $tHighUser
  Decomposed dirs tlow, thigh: $tLowDecomposed, $tHighDecomposed
  Reconstructed dirs tlow, thigh: $tLowReconstructed, $tHighReconstructed
  "
  exit 10
fi

# Figure out how many time directories we need to reconstruct
nTimes=$(( $nHigh - $nLow + 1 ))

# If we have too many processors, then reduce them
if [ $(echo "$nTimes < $NPROCS" | bc) == 1 ]; then
  NPROCS=$nTimes
fi

# Now split these among the processors
echo "running $APPNAME in pseudo-parallel mode on $NPROCS processors"
timesPerProc=$(( $nTimes / $NPROCS ))
extraTimes=$(( $nTimes % $NPROCS ))
tLowProc=$tLow
nLowProc=$nLow

echo
echo "*** Stats: ***"
echo "> Start time: $tLow"
echo "> End time: $tHigh"
echo "> Total number of times: $nTimes"
echo "> Number of times per processor: $timesPerProc"
echo

TEMPDIR="temp.parReconstructPar"
echo "Making temp dir at $TEMPDIR"
mkdir $TEMPDIR

PIDS=""
for i in $(seq $NPROCS); do
  if [ $extraTimes -ge 1 ]; then
    nHighProc=$(( $nLowProc + $timesPerProc ))
    extraTimes=$(( $extraTimes - 1 ))
  else
    nHighProc=$(( $nLowProc + $timesPerProc - 1 ))
  fi
  tHighProc=$(ls processor0 -1v | sed '/constant/d' | sort -g | sed -n "$nHighProc"p)
  echo "Starting job $i: from $tLowProc to $tHighProc"
  if [ -n "$FIELDS" ]; then
    $($APPNAME -fields "($FIELDS)" -time $tLowProc:$tHighProc > $TEMPDIR/output-$i &)
  else
    $($APPNAME -time $tLowProc:$tHighProc > $TEMPDIR/output-$i &)
  fi
  PIDS="$PIDS $(pgrep -n -x $APPNAME)"  # Get the PID of the latest (-n) job exactly matching (-x) $APPNAME
  nLowProc=$(( $nHighProc + 1 ))
  tLowProc=$(ls processor0 -1v | sed '/constant/d' | sort -g | sed -n "$nLowProc"p)
done

echo "PIDS: $PIDS"

# Sleep until jobs finish and provide progress
until [ $(ps -p $PIDS | wc -l) -eq 1 ]; do
  nTimeDirsCreated=$(ls -d [0-9]* | sort -g | sed -n "/$tLow/,/$tHigh/p" | wc -l)
  # Update the last line with the current status so as to not flood the terminal
  # The \033[K escape sequence clears the line before writing
  # Taken from https://stackoverflow.com/questions/2388090/how-to-delete-and-replace-last-line-in-the-terminal-using-bash
  printf "\033[KDirectories: $nTimeDirsCreated created / $nTimes total\r"
  sleep 1
done

# Consolidate and clean the logs
if [ -n "$LOGFILE" ]; then
  if [ -e "$LOGFILE" ]; then
    newLogFile="$LOGFILE$(date +%y%m%d_%H%M%S)"
    echo "Output file $LOGFILE exists."
    echo "Moving to $newLogFile"
    mv "$LOGFILE" "$newLogFile"
  fi
  for i in $TEMPDIR/*; do
    cat $i >> $LOGFILE
  done
fi
rm -rf $TEMPDIR

echo "Done!"
exit 0
