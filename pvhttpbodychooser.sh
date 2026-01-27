#!/bin/bash

# --- CONFIGURATION ---
FILE_PATTERN="*.httpbody.json"

# --- USER DEFINED FUNCTION ---
process_protocol_file() {
    local target_file="$1"
    # TODO: Logic for pvprotocolorizer.py goes here
    cat $target_file | fx
}

usage() {
    echo "Usage: $0 [OPTION] [INDEX]"
    echo "Options:"
    echo "  -l          List all available protocol files grouped by conversation."
    echo "  -h          Show this help message."
    echo ""
    echo "Arguments:"
    echo "  INDEX       The index number of the file to process (from the -l list)."
    exit 1
}

# 1. Array Construction and Logical Sorting
# Groups req.X.rsp.Y and rsp.Y.req.X together
raw_files=( $(ls $FILE_PATTERN 2>/dev/null | perl -e '
    print sort {
        my ($an1, $an2) = $a =~ /(\d+).+?(\d+)/;
        my ($bn1, $bn2) = $b =~ /(\d+).+?(\d+)/;
        my $keyA = join(".", sort { $a <=> $b } ($an1, $an2));
        my $keyB = join(".", sort { $a <=> $b } ($bn1, $bn2));
        $keyA cmp $keyB || $a cmp $b
    } <>;
') )

# 2. Parse Options using getopt
OPTS=$(getopt -o lh -- "$@")
if [ $? != 0 ]; then usage; fi
eval set -- "$OPTS"

LIST_ONLY=false

while true; do
    case "$1" in
        -l) LIST_ONLY=true; shift ;;
        -h) usage; shift ;;
        --) shift; break ;;
        *) break ;;
    esac
done

# 3. Handle Listing Logic (-l)
if [ "$LIST_ONLY" = true ]; then
    echo "--- Grouped HTTP Conversations ---"
    echo ""
    for i in "${!raw_files[@]}"; do
        if [ $((i % 2)) -eq 0 ] && [ $i -gt 0 ]; then
            echo "--------------------------------------"
        fi
        printf "[%2d] %s\n" "$i" "${raw_files[$i]}"
    done
    exit 0
fi

# 4. Handle Positional Argument (INDEX)
CHOICE=$1

if [ -z "$CHOICE" ]; then
    usage
fi

if [[ "$CHOICE" =~ ^[0-9]+$ ]] && [ "$CHOICE" -lt "${#raw_files[@]}" ]; then
    selected_file="${raw_files[$CHOICE]}"
    process_protocol_file "$selected_file"
else
    echo "Error: Invalid index '$CHOICE'. Use -l to see available indices."
    exit 1
fi
