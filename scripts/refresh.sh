#!/bin/sh
# Re-pull the numbers with your own gh login and push the refreshed cards to the profile repo and the org README repo. Runs on your machine only.
set -e
cd "$(dirname "$0")/.."
python3 scripts/build.py --collect
git add -A && git commit -q -m "Refresh cards" && git push -q && echo "profile pushed"
ORG=../getparalo-dotgithub
if [ -d "$ORG/.git" ]; then
  mkdir -p "$ORG/profile/assets/stills"
  cp assets/header-org-*.svg assets/shipping-org-*.svg assets/languages-*.svg "$ORG/profile/assets/"
  cp assets/stills/*.jpg "$ORG/profile/assets/stills/"
  git -C "$ORG" add -A && git -C "$ORG" commit -q -m "Refresh cards" && git -C "$ORG" push -q && echo "org pushed"
fi
