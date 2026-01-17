#!/usr/bin/env bash

set -euo pipefail
#set -x

usage() {
  cat <<'USAGE'
Usage: pvrrdisp.sh [OPTIONS] <dump_output.csv>

Read the output (csv) of the pvrrdump.sh command and output
a csv that describes the interactions.

Options:
  -h, --help : Show this help. optional.

Example:
   pvrrdisp.sh pvrrdump_map.csv
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

RR_FILE="$1"

if [ ! -f "$RR_FILE" ]; then
  echo "Error: file not found: $RR_FILE" >&2
  exit 1
fi

TMP_FILE="$(mktemp -t reqrspdump.XXXXXX)"   
trap 'rm -f "$TMP_FILE"' EXIT

echo "MSGTYPE,FROMIP,FROMPORT,TOIP,TOPORT,METHOD,URI,RESPCODE,RESPPHRASE,FILENAME"

cat $RR_FILE | sed '1d' |\
while IFS=',' read -r reqfilename rspfilename
do
    #echo "reqfilename=$reqfilename"
    #echo "rspfilename=$rspfilename"

    # request

    jq -r "[
        \"REQ\",
        .layers.ip_src[0],
        .layers.tcp_srcport[0],
        .layers.ip_dst[0],
        .layers.tcp_dstport[0],
        .layers.http_request_method[0],
        .layers.http_request_uri[0],
        \"\",
        \"\",
        \"$reqfilename\"
        ] | @csv" $reqfilename

    # response

    jq -r "[
        \"RSP\",
        .layers.ip_src[0],
        .layers.tcp_srcport[0],
        .layers.ip_dst[0],
        .layers.tcp_dstport[0],
        \"\",
        \"\",
        .layers.http_response_code[0],
        .layers.http_response_phrase[0],
        \"$rspfilename\"
        ] | @csv" $rspfilename

done

