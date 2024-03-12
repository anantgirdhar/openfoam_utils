#!/bin/sh

for f in "$@"; do
  tar -xvf $f  && rm $f
done
