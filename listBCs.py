#!/usr/bin/python3
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

# Read all files in the specified) directory and store the BC info in a dict
bcs = {}
KEYWORD_LIST = ['type', 'value', 'freestreamValue', 'inletValue', 'referenceField', 'fluctuationScale']

for var in os.listdir(dirname):
    with open(dirname + '/' + var, 'r') as infile:
        BCs_started = False  # flag to indicate if we're reading the BCs
        in_patch = False  # flag to indicate if we're inside the patch
        current_patch = None  # which patch is being processed
        for line in infile:
            line = line.strip()  # Remove all whitespace
            if not line:
                # Skip blank lines
                continue
            # print(f'{line} <{BCs_started} | {in_patch} | {current_patch}>')
            if line == 'boundaryField':
                # Found the start of the BCs
                BCs_started = True
                # line = next(infile)
                # if line == '{':
                #     # Skip the opening brace
                #     continue
                continue
            if not BCs_started:
                continue
            elif line == '{':
                if current_patch is not None:
                    # This is the start of a specific patch
                    in_patch = True
                else:
                    # This is probably from the start of boundaryField
                    # Skip it
                    pass
                continue
            elif line == '}':
                if in_patch:
                    # This is the end of a specific patch
                    in_patch = False
                    current_patch = None
                else:
                    # We're not in a patch so we need to close boundaryField
                    BCs_started = False
                continue
            if not in_patch and current_patch is None:
                # This is a new patch
                current_patch = line
                if current_patch not in bcs:
                    bcs[current_patch] = {}
                continue
            elif in_patch and current_patch is None:
                raise ValueError("Something went wrong: we're in a patch but the current_patch is None.")
            elif in_patch and current_patch is not None:
                if var not in bcs[current_patch]:
                    bcs[current_patch][var] = collections.OrderedDict()
                # Ignore the information if it is not a keyword we care about
                if (keyword := line.split(' ')[0].strip()) not in KEYWORD_LIST:
                    continue
                value = ' '.join([word.strip() for word in line.split(' ')[1:] if word])
                bcs[current_patch][var][keyword] = value
                continue
            elif not in_patch and current_patch is not None:
                raise ValueError("Something went wrong: we're not in a patch but the current_patch is not None.")
pprint(bcs)
