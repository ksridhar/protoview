#!/usr/bin/env bash
set -euo pipefail

cwd="$(pwd)"

gnome-terminal \
  --tab \
  --working-directory="$cwd" \
  -- bash -i -c 'echo "in new terminal"; exec bash'

