#!/bin/sh
# Re-pull the shipping numbers with your own gh login and push the refreshed cards. Runs on your machine only.
set -e
cd "$(dirname "$0")/.."
python3 scripts/build.py --collect
git add -A && git commit -q -m "Refresh shipping log" && git push -q && echo pushed
