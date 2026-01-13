#!/usr/bin/env bash
set -euo pipefail
#set -x

usage() {
  cat <<'USAGE'
Usage: pvcap.sh <port> [port...]

Capture TCP traffic for one or more ports using dumpcap.

Options:
  -h, --help              Show this help
USAGE
}

# Parse arguments with getopt
PARSED_ARGS=$(getopt -o h --long help -- "$@")
if [ $? -ne 0 ]; then
  usage
  exit 2
fi

# Safe eval of getopt output
# shellcheck disable=SC2086
eval set -- "$PARSED_ARGS"

while true; do
  case "$1" in
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      usage
      exit 2
      ;;
  esac
done

if [ $# -lt 1 ]; then
  usage
  exit 2
fi

FILTER=""
for port in "$@"; do
  if [ -z "$FILTER" ]; then
    FILTER="tcp port $port"
  else
    FILTER="$FILTER or tcp port $port"
  fi
done

DUMPCAP_PID=""

cleanup() {
  if [ -n "$DUMPCAP_PID" ] && kill -0 "$DUMPCAP_PID" 2>/dev/null; then
    kill -INT "$DUMPCAP_PID" 2>/dev/null || true
    wait "$DUMPCAP_PID" 2>/dev/null || true
  fi
}

trap cleanup INT TERM EXIT

dumpcap -i lo -f "$FILTER" -w - &

DUMPCAP_PID=$!
wait "$DUMPCAP_PID"
