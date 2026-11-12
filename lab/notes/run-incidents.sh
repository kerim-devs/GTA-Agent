#!/bin/sh
# Incidents of the eleven recordings of 11 November into lab/notes/out, then the summary.
cd "$(dirname "$0")/../../pilot" || exit 1
R=/Users/kerim/recordings/kerim
env -u PS5_HOST .venv/bin/python tools/incidents.py \
  $R/20261111-164039 $R/20261111-165543 $R/20261111-171046 $R/20261111-172549 $R/20261111-175312 \
  $R/20261111-180814 $R/20261111-182316 $R/20261111-183820 $R/20261111-185323 $R/20261111-190825 \
  $R/20261111-192328 --out ../lab/notes/out --sections-root ../lab/notes/sections &&
  env -u PS5_HOST .venv/bin/python tools/incidents.py --summary ../lab/notes/out
