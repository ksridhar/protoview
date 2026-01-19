#!/bin/bash

# Default variables
PUML_SOURCE=""
TEMPLATE_HTML=""

# Help function
usage() {
    echo "Usage: $0 --puml-source {filepath.puml} --template-html {template.filepath.html}" >&2
    echo "Example: $0 --puml-source my.puml --template-html template.html > final.html" >&2
    exit 1
}

# Parse arguments
PARSED_ARGUMENTS=$(getopt -o p:t:h --long puml-source:,template-html:,help -- "$@")
VALID_ARGUMENTS=$?
if [ "$VALID_ARGUMENTS" != "0" ]; then
  usage
fi

eval set -- "$PARSED_ARGUMENTS"

while :
do
  case "$1" in
    -p | --puml-source)  PUML_SOURCE="$2"   ; shift 2 ;;
    -t | --template-html) TEMPLATE_HTML="$2" ; shift 2 ;;
    -h | --help)          usage ;;
    --) shift; break ;;
    *) echo "Unexpected option: $1" >&2 ; usage ;;
  esac
done

# Check for mandatory options
if [ -z "$PUML_SOURCE" ] || [ -z "$TEMPLATE_HTML" ]; then
    echo "Error: Both --puml-source and --template-html are mandatory." >&2
    usage
fi

# Validate file existence
if [ ! -f "$PUML_SOURCE" ]; then
    echo "Error: PUML source file '$PUML_SOURCE' not found." >&2
    exit 1
fi

if [ ! -f "$TEMPLATE_HTML" ]; then
    echo "Error: Template HTML file '$TEMPLATE_HTML' not found." >&2
    exit 1
fi

# Perform the injection
# sed finds the %SPEC% marker and reads the source file into that position
sed -e "/%SPEC%/ {" -e "r $PUML_SOURCE" -e "d" -e "}" "$TEMPLATE_HTML"

