#!/usr/bin/env bash
# Create the feature branches listed in CONTEXT.md §7 from 3d-visualization (dc59952).
# Safe to re-run: existing branches are left alone. Does not switch your checkout or push.
set -euo pipefail
cd "$(dirname "$0")/.."
BASE="${1:-3d-visualization}"
branches=(
  m1/final-journey-rerun
  m2/flag-parking-and-crossing
  m2/climate-energy-balance
  m3/enablers-and-risk-register
  m5/benchmarks-hardening
  m1/conservation-record
  m4/openspace-renditions
  m4/dashboard-and-export
  m1/live-demo-presets
  m3/octo-earth-audit
  m5/technical-report
  m5/pitch-and-video
  m1/energy-bonus-study
)
for b in "${branches[@]}"; do
  if git show-ref --verify --quiet "refs/heads/$b"; then
    echo "exists  $b"
  else
    git branch "$b" "$BASE" && echo "created $b <- $BASE"
  fi
done
echo "Push one when you start on it:  git push -u origin <branch>"
