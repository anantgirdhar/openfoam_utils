#!/usr/bin/python3
import argparse
import os
import sys
import collections
from pprint import pprint

# Check if a directory is specified
# If it is, use it. Otherwise, use the 0/ directory
if len(sys.argv) > 1:
    dirname = sys.argv[1]
else:
    dirname = '0'

parser = argparse.ArgumentParser(
        prog='getMinMax',
        description='Get the min and max of a variable',
        )
parser.add_argument('var')
parser.add_argument('-t', '--time', type=float)
parser.add_argument('-s', '--start', type=float, help='Ignored if time is specified')
parser.add_argument('-e', '--end', type=float, help='Ignored if time is specified')
args = parser.parse_args()

var = args.var

if args.time:
    start_time = args.time
    end_time = args.time
elif args.start and args.end:
    start_time = args.start
    end_time = args.end
else:
    raise ValueError('Need to specify at least one time.')

if start_time > end_time:
    raise ValueError(f'Start time {start_time} > End time {end_time}')

min_value = {}
max_value = {}

for t in sorted(os.listdir('.')):
    try:
        if float(t) < start_time or float(t) > end_time:
            continue
    except ValueError:
        continue
    current_min = None
    current_max = None
    with open(t + '/' + var, 'r') as infile:
        #TODO: This only gets the internalField. Maybe expand this to also read the boundary fields.
        found_internal_field = False
        inside_internal_field = False
        for line in infile:
            line = line.strip()  # Remove all whitespace
            if not line:
                # Skip blank lines
                continue
            # print(f'{line} <{BCs_started} | {in_patch} | {current_patch}>')
            if line.startswith('internalField'):
                found_internal_field = True
                # Skip over the next two lines
                continue
            if found_internal_field and not inside_internal_field and line == '(':
                inside_internal_field = True
                continue
            if inside_internal_field:
                if line == ')':
                    break
                if current_min is None:
                    current_min = float(line)
                    current_max = float(line)
                else:
                    value = float(line)
                    if value < current_min:
                        current_min = value
                    if value > current_max:
                        current_max = value
    min_value[t] = current_min
    max_value[t] = current_max
    print(f'{t:<8s}: {min_value[t]:8.2f}  -  {max_value[t]:8.2f}')

overall_min_value = min(min_value.values())
overall_max_value = max(max_value.values())

print('Final statistics:')
print(f'Overall min value: {overall_min_value}')
print(f'Overall max value: {overall_max_value}')
