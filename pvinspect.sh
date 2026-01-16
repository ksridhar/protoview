#!/usr/bin/env bash

set -euo pipefail
#set -x

usage() {
  cat <<'USAGE'
Usage: pvinspect.sh [OPTIONS] <capture.pcapng>

Parses HTTP from a pcapng file and emits JSONL/ndjson to stdout.

Options:
  -h, --help : Show this help. optional.
  -p, --port {portnum} : select only those messages sent or received on tcp {portnum}. mandatory.

Example:
   pvinspect -p 10002 10002.pcapng

TODO:
   Multiple {portnum}
USAGE
}

PORT_NUM=""

# Parse arguments with getopt
PARSED_ARGS=$(getopt -o hp: --long help -- "$@")
if [ $? -ne 0 ]; then
  usage
  exit 2
fi

# Safe eval of getopt output
# shellcheck disable=SC2086
eval set -- "$PARSED_ARGS"

while true; do
  case "$1" in
    -p|--port)
      PORT_NUM="$2"
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

if [[ -z $PORT_NUM ]]
then
    usage
    exit 2
fi

PCAP_FILE="$1"

if [ ! -f "$PCAP_FILE" ]; then
  echo "Error: file not found: $PCAP_FILE" >&2
  exit 1
fi

TMP_FILE="$(mktemp -t pvinspect.XXXXXX)"
trap 'rm -f "$TMP_FILE"' EXIT


PCAP_DIRNAME=$(dirname $PCAP_FILE)
PCAP_BASENAME=$(basename $PCAP_FILE)
PCAP_BARENAME=${PCAP_BASENAME%.*}
PCAP_BAREPATHNAME=${PCAP_DIRNAME}/${PCAP_BARENAME}

# The temp file is kept for potential future expansion; no data is written to it now.
#
# tshark options:
# -r: input capture file
# -2: two-pass analysis for better reassembly context
# -o tcp.desegment_tcp_streams:TRUE: reassemble TCP streams to avoid HTTP truncation
# -o http.desegment_headers:TRUE: allow HTTP headers to span multiple TCP segments
# -o http.desegment_body:TRUE: allow HTTP body to span multiple TCP segments
# -Y: include only HTTP with textual content types
# -T ek: emit JSONL/ndjson (ElasticSearch bulk format)
# -e: emit selected HTTP fields

if ((0))
then
  # var.1
output_filepath=${PCAP_BAREPATHNAME}.var.01.jsonl
rm -f $output_filepath
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -Y 'http and (http.content_type contains "text" or http.content_type contains "json" or http.content_type contains "xml" or http.content_type contains "ndjson" or http.content_type contains "jsonl")' \
  -e http.request.method \
  -e http.request.uri \
  -e http.request.full_uri \
  -e http.host \
  -e http.response.code \
  -e http.response.phrase \
  -e http.user_agent \
  -e http.content_type \
  -e http.content_length \
  -e http.file_data \
  -T ek \
  -- |\
jq '.' > $output_filepath
echo "dumped $output_filepath" >&2
fi

if ((0))
then
  # var.2
output_filepath=${PCAP_BAREPATHNAME}.var.02.jsonl
rm -f $output_filepath
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -Y 'http' \
  -e http.request.method \
  -e http.request.uri \
  -e http.request.full_uri \
  -e http.host \
  -e http.response.code \
  -e http.response.phrase \
  -e http.user_agent \
  -e http.content_type \
  -e http.content_length \
  -e http.file_data \
  -T ek \
  -- |\
jq '.' > $output_filepath
echo "dumped $output_filepath" >&2
fi

if ((0))
then
  # var.3
output_filepath=${PCAP_BAREPATHNAME}.var.03.jsonl
rm -f $output_filepath
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -Y 'http' \
  -T ek \
  -- |\
jq '.' > $output_filepath
echo "dumped $output_filepath" >&2
fi

if ((0))
then
  # var.4
output_filepath=${PCAP_BAREPATHNAME}.var.04.jsonl
rm -f $output_filepath
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -R "http" \
  -J "http" \
  -Y "http" \
  -T ek \
  -- |\
jq '.' > $output_filepath
echo "dumped $output_filepath" >&2
fi

if ((0))
then
  # var.5
output_filepath=${PCAP_BAREPATHNAME}.var.05.jsonl
rm -f $output_filepath
rm -rf ./var.5
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -R "http" \
  -J "http" \
  -Y "http" \
  --export-objects "http,./${PCAP_BARENAME}" \
  -T ek \
  -- |\
jq '.' > $output_filepath
echo "dumped $output_filepath" >&2
fi

# https://www.wireshark.org/docs/dfref/h/http.html

if ((1))
then
  # var.6
#output_filepath=${PCAP_BAREPATHNAME}.var.06.jsonl
#rm -f $output_filepath
#set -x
exec tshark \
  -r "$PCAP_FILE" \
  -2 \
  -o tcp.desegment_tcp_streams:TRUE \
  -o http.desegment_headers:TRUE \
  -o http.desegment_body:TRUE \
  -Y "http and (tcp.srcport == $PORT_NUM or tcp.dstport == $PORT_NUM)" \
  -e frame.number \
  -e ip.src \
  -e ip.dst \
  -e tcp.srcport \
  -e tcp.dstport \
  -e tcp.stream \
  -e http.accept \
  -e http.accept_encoding \
  -e http.accept_language \
  -e http.connection \
  -e http.content_encoding \
  -e http.content_length \
  -e http.content_length_header \
  -e http.content_type \
  -e http.date \
  -e http.file_data \
  -e http.host \
  -e http.prev_request_in \
  -e http.prev_response_in \
  -e http.referer \
  -e http.request \
  -e http.request.full_uri \
  -e http.request.line \
  -e http.request.method \
  -e http.request.uri \
  -e http.request.uri.path \
  -e http.request.uri.query \
  -e http.request.uri.query.parameter \
  -e http.request.version \
  -e http.request_in \
  -e http.request_number \
  -e http.response \
  -e http.response.code \
  -e http.response.code.desc \
  -e http.response.line \
  -e http.response.phrase \
  -e http.response.version \
  -e http.response_for.uri \
  -e http.response_in \
  -e http.response_number \
  -e http.server \
  -e http.user_agent \
  -T ek \
  -- |\
jq '.' # > $output_filepath
#echo "dumped $output_filepath" >&2
fi

# NOTES:
#
# - request.http_response_in == response.frame_number and
# - response.http_request_in = request.frame_number 
#
