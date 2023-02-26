# coding: utf-8
import numpy as np
import matplotlib.pyplot as plt

# Read the file
d = []
with open('points', 'r') as f:
    for line in f:
        if line.startswith('('):
            d.append(line)
d = [line.strip() for line in d]

# Extract the coordinates into separate lists
X = []
Y = []
Z = []
for line in d:
    line = line.replace('(', '').replace(')', '')
    try:
        x, y, z = line.split()
    except ValueError:
        # If there aren't enough values to unpack, then skip the line
        continue
    X.append(float(x))
    Y.append(float(y))
    Z.append(float(z))

# Plot the coordinates
fig = plt.figure()
ax = fig.add_subplot(projection='3d')
ax.scatter(X, Y, Z, marker='.')
ax.set_xlabel('X')
ax.set_ylabel('Y')
ax.set_zlabel('Z')
plt.show()
