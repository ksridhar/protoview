#!/usr/bin/env bash

set -euo pipefail
#set -x

usage() {
  cat <<'USAGE'
Usage: pvrrdump.sh [OPTIONS] <inspect_output.jsonl>

Read the output of the pvinspect.sh command and create request
response files.

Options:
  -h, --help : Show this help. optional.
  -P, --prefix {file_prefix} : a string that is used as the
      prefix for the generated file. default is 'http.'.

Example:
   pvrrdump.sh -P foo. 10002.jsonl
USAGE
}

PREFIX="http."

# Parse arguments with getopt
PARSED_ARGS=$(getopt -o hP: --long help -- "$@")
if [ $? -ne 0 ]; then
  usage
  exit 2
fi

# Safe eval of getopt output
# shellcheck disable=SC2086
eval set -- "$PARSED_ARGS"

while true; do
  case "$1" in
    -P|--prefix)
      PREFIX="$2"
      shift 2
        ;;
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

if [ $# -ne 1 ]; then
  usage
  exit 2
fi

INSPECTED_FILE="$1"

if [ ! -f "$INSPECTED_FILE" ]; then
  echo "Error: file not found: $INSPECTED_FILE" >&2
  exit 1
fi

TMP_FILE="$(mktemp -t reqrspdump.XXXXXX)"   
trap 'rm -f "$TMP_FILE"' EXIT

## Thanks to chatGPT
## Each json line with a frame number is written to
## a file. 
## If its a request  the format is ${PREFIX}.req.{a}.rsp.{b}.json
## where {a} is the frame_number and {b} is response_in
##
## If its a response the format is ${PREFIX}.rsp.{c}.req.{d}.json
## where {c} is the frame_number and {d} is request_in

echo "REQFILENAME,RSPFILENAME"

jq -cr '
  # keep only real packet records with a frame number
  select(.layers? and .layers.frame_number?[0]?)

  | (.layers.frame_number[0] | tostring) as $fn

  | if (.layers.http_request?[0]? == "1") then
        # request → points to response via http_response_in
        select(.layers.http_response_in?[0]?)
        | "req.\($fn).rsp.\(.layers.http_response_in[0]).json"

    elif (.layers.http_response?[0]? == "1") then
        # response → points to request via http_request_in
        select(.layers.http_request_in?[0]?)
        | "rsp.\($fn).req.\(.layers.http_request_in[0]).json"

    else
        # empty
        "unknown.\($fn).json"
    end

  + "\t" + (@json)
' $INSPECTED_FILE \
| \
while IFS=$'\t' read -r fname json; do

    read -r reqkw reqnum rspkw rspnum jsonkw <<< "${fname//./ }"
    reqfilename="$PREFIX.$reqkw.$reqnum.$rspkw.$rspnum.$jsonkw"
    rspfilename="$PREFIX.$rspkw.$rspnum.$reqkw.$reqnum.$jsonkw"
    echo $reqfilename,$rspfilename

    printf '%s\n' "$json" | jq '.' > "${PREFIX}.${fname}"
done

