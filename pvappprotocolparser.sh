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
        with open(filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_map[row['Symbol']] = row['Description']
        return spec_map
    except Exception as e:
        log_error(f"Could not read {filename}: {e}")
        sys.exit(1)

def annotate_node(key, value, path, protocol, rpc_map, a2ui_map):
    """
    Recursively transforms a standard JSON node into an Annotated Node.
    """
    # Determine current description
    current_map = rpc_map if protocol == "jsonrpc" else a2ui_map
    description = current_map.get(key, f"Field defined within the {protocol} protocol context.")
    
    # Check for Gateway transition
    # Logic: If we are in jsonrpc and key is params/result, check if child looks like A2UI
    next_protocol = protocol
    if protocol == "jsonrpc" and key in ["params", "result"]:
        v_str = str(value)
        if '"surfaces"' in v_str or '"components"' in v_str:
            next_protocol = "a2ui"

    # Prepare the Annotated Node structure
    node = {
        "protocol": protocol,
        "path": path,
        "key": key,
        "description": description,
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
        description="Protocol Parser: Annotates JSON files with JSON-RPC and A2UI specifications."
    )
    parser.add_argument("input_file", help="Path to the file to be processed (empty/text files are ignored).")
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity to stderr.")
    parser.add_argument("--validate", action="store_true", help="Validate final output against the annotated-json-schema.json.")
    
    args = parser.parse_args()

    # 1. Sniffing Phase
    if not os.path.exists(args.input_file):
        log_error(f"File not found: {args.input_file}")
        sys.exit(1)

    if os.path.getsize(args.input_file) == 0:
        log_verbose("Input file is empty. Ignoring.", args.verbose)
        return

    try:
        with open(args.input_file, 'r') as f:
            raw_data = json.load(f)
    except json.JSONDecodeError:
        log_verbose("Input is not valid JSON (Text file). Ignoring.", args.verbose)
        return

    # 2. Loading Resources
    log_verbose("Loading specification maps...", args.verbose)
    rpc_map = load_csv_map(JSONRPC_MAP_FILE)
    a2ui_map = load_csv_map(A2UI_MAP_FILE)

    # 3. Traversal Phase
    log_verbose("Starting recursive annotation...", args.verbose)
    annotated_output = annotate_node("root", raw_data, "root", "jsonrpc", rpc_map, a2ui_map)

    # 4. Optional Validation Phase
    if args.validate:
        log_verbose("Validating output against schema...", args.verbose)
        try:
            import jsonschema
            with open(SCHEMA_FILE, 'r') as s:
                schema = json.load(s)
            jsonschema.validate(instance=annotated_output, schema=schema)
            log_verbose("Validation successful.", args.verbose)
        except ImportError:
            log_error("jsonschema library not found. Skipping validation.")
        except Exception as e:
            log_error(f"Schema Validation Failed: {e}")
            sys.exit(1)

    # 5. Output
    print(json.dumps(annotated_output, indent=2))

if __name__ == "__main__":
    main()
