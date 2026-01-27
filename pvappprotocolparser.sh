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
    print(f"ERROR: {msg}", file=sys.stderr)

def log_verbose(msg, verbose):
    if verbose:
        print(f"VERBOSE: {msg}", file=sys.stderr)

def load_csv_map(filename):
    spec_map = {}
    try:
        with open(filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_map[row['Symbol']] = row['Description']
        return spec_map
    except Exception as e:
        log_error(f"Could not read {filename}: {e}")
        sys.exit(1)

def get_smart_description(key, protocol, path, rpc_map, a2ui_map):
    # Select the map based on current protocol context
    current_map = rpc_map if protocol == "jsonrpc" else a2ui_map
    
    # 1. Check the specific CSV map
    if key in current_map:
        return current_map[key]
    
    # 2. Contextual Fallbacks
    if protocol == "a2ui":
        if ".props" in path:
            return "A2UI Property: A configuration attribute for this component."
        if ".data" in path:
            return "A2UI Data: A dynamic state variable for this component."
        if ".children" in path:
            return "A2UI Child: Reference to a nested component ID."
        return f"A2UI Structure: Part of the declarative UI tree ({key})."
    
    if protocol == "jsonrpc":
        if ".params" in path:
            return "Method Parameter: Input data required by the remote method."
        return f"JSON-RPC Envelope: Structural member of the RPC protocol."

    return f"Field in {protocol} context."

def annotate_node(key, value, path, protocol, rpc_map, a2ui_map):
    # --- GATEWAY LOGIC ---
    # If we are currently in jsonrpc, check if we should switch to a2ui
    next_protocol = protocol
    if protocol == "jsonrpc":
        # If the value is a dict and contains A2UI root keys, switch context
        if isinstance(value, dict) and ("surfaces" in value or "components" in value):
            next_protocol = "a2ui"
    
    # Get the description based on the protocol we just determined
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
        description="pvappprotocolparser: Context-aware JSON-RPC to A2UI converter."
    )
    parser.add_argument("input_file", help="The file to process.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output to stderr.")
    parser.add_argument("--validate", action="store_true", help="Validate vs annotated-json-schema.json.")
    
    args = parser.parse_args()

    if not os.path.exists(args.input_file) or os.path.getsize(args.input_file) == 0:
        return

    try:
        with open(args.input_file, 'r') as f:
            raw_data = json.load(f)
    except:
        return

    rpc_map = load_csv_map(JSONRPC_MAP_FILE)
    a2ui_map = load_csv_map(A2UI_MAP_FILE)

    # Start recursion
    annotated_output = annotate_node("root", raw_data, "root", "jsonrpc", rpc_map, a2ui_map)

    if args.validate:
        try:
            import jsonschema
            with open(SCHEMA_FILE, 'r') as s:
                schema = json.load(s)
            jsonschema.validate(instance=annotated_output, schema=schema)
        except Exception as e:
            log_error(f"Validation Error: {e}")
            sys.exit(1)

    print(json.dumps(annotated_output, indent=2))

if __name__ == "__main__":
    main()
