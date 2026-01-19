#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: pvrrenumi.sh [OPTIONS] <dump_output.csv>

Options:
  -h, --help         : Show this help.
  --destringjson     : Destringify the http_file_data JSON payload if possible.

Example:
   pvrrenumi.sh --destringjson pvrrdump_map.csv
USAGE
}

DESTRING=false
PARSED_ARGS=$(getopt -o h --long help,destringjson -- "$@")
if [ $? -ne 0 ]; then
  usage
  exit 2
fi

eval set -- "$PARSED_ARGS"

while true; do
  case "$1" in
    --destringjson)
      DESTRING=true
      shift
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

# Print Header
echo "MSGTYPE,FROMIP,FROMPORT,TOIP,TOPORT,METHOD,URI,RESPCODE,RESPPHRASE,FILENAME,HTTPBODYFILENAME"

# Skip CSV header and iterate
sed '1d' "$RR_FILE" | while IFS=',' read -r reqfilename rspfilename
do
    # Process both Request and Response
    for FILENAME in "$reqfilename" "$rspfilename"; do
        # Strip quotes from CSV values
        FILENAME=$(echo "$FILENAME" | tr -d '"')
        
        if [ ! -f "$FILENAME" ]; then continue; fi

        BODYFILE="${FILENAME%.json}.httpbody.json"

        # 1. Extract the raw payload
        RAW_PAYLOAD=$(jq -r '.layers.http_file_data[0] // ""' "$FILENAME")

        # 2. Write the Body File
        if [ -n "$RAW_PAYLOAD" ]; then
            if [ "$DESTRING" = true ]; then
                # Attempt to destringify. If it fails, cat the raw payload instead.
                # 'fromjson' is used to decode the string.
                if ! echo "$RAW_PAYLOAD" | jq -e 'fromjson' > "$BODYFILE" 2>/dev/null; then
                    echo "$RAW_PAYLOAD" > "$BODYFILE"
                fi
            else
                echo "$RAW_PAYLOAD" > "$BODYFILE"
            fi
        else
            : > "$BODYFILE"
        fi

        # 3. Output CSV Row
        jq -r --arg fname "$FILENAME" --arg bname "$BODYFILE" '
            if .layers.http_request_method then
                ["REQ", .layers.ip_src[0], .layers.tcp_srcport[0], .layers.ip_dst[0], .layers.tcp_dstport[0], .layers.http_request_method[0], .layers.http_request_uri[0], "", "", $fname, $bname]
            else
                ["RSP", .layers.ip_src[0], .layers.tcp_srcport[0], .layers.ip_dst[0], .layers.tcp_dstport[0], "", "", .layers.http_response_code[0], .layers.http_response_phrase[0], $fname, $bname]
            end | @csv' "$FILENAME"
    done
done
