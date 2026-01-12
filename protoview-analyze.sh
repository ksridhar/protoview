#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: protoview-analyze.sh [OPTIONS] <capture.pcapng>

Parses HTTP from a pcapng file and emits JSONL/ndjson to stdout.

Options:
  -h, --help    Show this help
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
set -- $PARSED_ARGS

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

if [ $# -ne 1 ]; then
  usage
  exit 2
fi

PCAP_FILE="$1"

if [ ! -f "$PCAP_FILE" ]; then
  echo "Error: file not found: $PCAP_FILE" >&2
  exit 1
fi

TMP_FILE="$(mktemp -t protoview-analyze.XXXXXX)"
trap 'rm -f "$TMP_FILE"' EXIT

# The temp file is kept for potential future expansion; no data is written to it now.

exec tshark \
  -r "$PCAP_FILE" \\ # input capture file
  -2 \\ # two-pass analysis for better reassembly context
  -o tcp.desegment_tcp_streams:TRUE \\ # reassemble TCP streams to avoid HTTP truncation
  -o http.desegment_headers:TRUE \\ # allow HTTP headers to span multiple TCP segments
  -o http.desegment_body:TRUE \\ # allow HTTP body to span multiple TCP segments
  -Y 'http and (http.content_type contains "text" or http.content_type contains "json" or http.content_type contains "xml")' \\ # include only HTTP with textual content types
  -T ek \\ # emit JSONL/ndjson (ElasticSearch bulk format)
  -e http.request.method \\ # HTTP request method
  -e http.request.uri \\ # HTTP request URI
  -e http.request.full_uri \\ # full URI if available
  -e http.host \\ # Host header
  -e http.response.code \\ # HTTP response code
  -e http.response.phrase \\ # HTTP response phrase
  -e http.user_agent \\ # User-Agent header
  -e http.content_type \\ # Content-Type header
  -e http.content_length \\ # Content-Length header
  -e http.file_data \\ # HTTP body (only when filtered as text)
  --
