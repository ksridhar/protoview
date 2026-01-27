import sys
import json
import csv
import argparse
import os

# Hardcoded filenames as per requirements
JSONRPC_MAP_FILE = "jsonrpc-specmap.csv"
A2UI_MAP_FILE = "a2ui-specmap.csv"
SCHEMA_FILE = "annotated-json-schema.json"

def log_error(msg):
    """Prints errors to stderr."""
    print(f"ERROR: {msg}", file=sys.stderr)

def log_verbose(msg, verbose):
    """Prints verbose info to stderr if flag is set."""
    if verbose:
        print(f"VERBOSE: {msg}", file=sys.stderr)

def load_csv_map(filename):
    """Loads CSV spec map into a dictionary: {symbol: description}."""
    spec_map = {}
    try:
        if not os.path.exists(filename):
            log_error(f"Missing specification map: {filename}")
            sys.exit(1)
        with open(filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_map[row['Symbol']] = row['Description']
        return spec_map
    except Exception as e:
        log_error(f"Could not read {filename}: {e}")
        sys.exit(1)

def get_smart_description(key, protocol, path, rpc_map, a2ui_map):
    """Determines description based on maps or high-fidelity contextual fallbacks."""
    current_map = rpc_map if protocol == "jsonrpc" else a2ui_map
    
    # 1. Exact match from CSV
    if key in current_map:
        return current_map[key]
    
    # 2. High-Fidelity Contextual Fallbacks
    if protocol == "a2ui":
        if ".props" in path:
            return f"Component Property: A configuration attribute specific to the '{key}' property of this widget."
        if ".data" in path:
            return f"Dynamic State: A data-bound value or variable used to update this component's content."
        if ".events" in path:
            return f"Interaction Handler: Defines the action taken when the '{key}' event is triggered."
        if ".children" in path:
            return "Component Reference: An ID link to a nested UI element."
        return f"A2UI Structure: A structural element of the declarative UI tree ({key})."
    
    if protocol == "jsonrpc":
        if key.startswith("["):
            return "Batch Member: An individual RPC unit within a bulk transmission array."
        if ".params" in path:
            return f"Method Parameter: A custom argument ('{key}') passed to the remote procedure."
        if ".error" in path:
            return f"Error Detail: Extended diagnostic information regarding the '{key}' error state."
        if path == "root" or path == "root.":
            return f"RPC Extension: A non-standard top-level member ('{key}') used for metadata or proprietary extensions."
        
    return f"Custom Field: An application-specific member found within the {protocol} context."

def annotate_node(key, value, path, protocol, rpc_map, a2ui_map):
    """Recursively transforms a standard JSON node into an Annotated Node."""
    
    # GATEWAY LOGIC: Check for transition from JSON-RPC to A2UI
    next_protocol = protocol
    if protocol == "jsonrpc":
        # Check if the value is an object containing A2UI triggers
        if isinstance(value, dict) and ("surfaces" in value or "components" in value):
            next_protocol = "a2ui"
        # Also check inside lists (for Batch requests containing A2UI)
        elif isinstance(value, list) and len(value) > 0:
            if isinstance(value[0], dict) and ("surfaces" in value[0] or "components" in value[0]):
                next_protocol = "a2ui"

    # Get description using the smart fallback logic
    description = get_smart_description(key, next_protocol, path, rpc_map, a2ui_map)
    
    node = {
        "protocol": next_protocol,
        "path": path,
        "key": key,
        "description": description,
        "category": "Terminal" if not isinstance(value, (dict, list)) else "Non-Terminal",
        "value": None
    }

    if isinstance(value, dict):
        node["value"] = [
            annotate_node(k, v, f"{path}.{k}", next_protocol, rpc_map, a2ui_map)
            for k, v in value.items()
        ]
    elif isinstance(value, list):
        node["value"] = [
            annotate_node(f"[{i}]", v, f"{path}[{i}]", next_protocol, rpc_map, a2ui_map)
            for i, v in enumerate(value)
        ]
    else:
        node["value"] = value
        
    return node

def main():
    parser = argparse.ArgumentParser(
        description="pvappprotocolparser: Context-aware JSON-RPC and A2UI annotator."
    )
    parser.add_argument("input_file", help="The JSON protocol file to process.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Log process details to stderr.")
    parser.add_argument("--validate", action="store_true", help="Validate output against annotated-json-schema.json.")
    
    args = parser.parse_args()

    # 1. Sniffing Phase
    if not os.path.exists(args.input_file):
        log_error(f"Input file missing: {args.input_file}")
        sys.exit(1)

    if os.path.getsize(args.input_file) == 0:
        log_verbose("Empty file. Ignoring.", args.verbose)
        return

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except json.JSONDecodeError:
        log_verbose("Input is not valid JSON. Ignoring.", args.verbose)
        return

    # 2. Resource Loading
    rpc_map = load_csv_map(JSONRPC_MAP_FILE)
    a2ui_map = load_csv_map(A2UI_MAP_FILE)

    # 3. Traversal and Annotation
    log_verbose(f"Annotating {args.input_file}...", args.verbose)
    # Start root at jsonrpc context
    annotated_output = annotate_node("root", raw_data, "root", "jsonrpc", rpc_map, a2ui_map)

    # 4. Schema Validation (Optional)
    if args.validate:
        if not os.path.exists(SCHEMA_FILE):
            log_error(f"Schema file missing: {SCHEMA_FILE}")
            sys.exit(1)
            
        try:
            import jsonschema
            with open(SCHEMA_FILE, 'r') as s:
                schema = json.load(s)
            jsonschema.validate(instance=annotated_output, schema=schema)
            log_verbose("Schema validation passed.", args.verbose)
        except ImportError:
            log_error("Python 'jsonschema' library not found. Skipping validation.")
        except Exception as e:
            log_error(f"Validation failed: {e}")
            sys.exit(1)

    # 5. Output result to stdout
    print(json.dumps(annotated_output, indent=2))

if __name__ == "__main__":
    main()
