import sys
import json
import csv
import argparse
import os
import html

# Hardcoded filenames for spec maps
JSONRPC_MAP_FILE = "jsonrpc-specmap.csv"
A2UI_MAP_FILE = "a2ui-specmap.csv"

def log_err(msg):
    """Logs errors to stderr to keep stdout clean for HTML."""
    print(f"LOG: {msg}", file=sys.stderr)

def load_spec_map(filename):
    """Loads CSV spec map into a dictionary."""
    spec_map = {}
    if not os.path.exists(filename):
        log_err(f"Warning: {filename} not found. Tooltips will be limited.")
        return spec_map
    try:
        with open(filename, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                spec_map[row['Symbol']] = row.get('Description', '')
        return spec_map
    except Exception as e:
        log_err(f"Error reading {filename}: {e}")
        return spec_map

class Protocolorizer:
    def __init__(self, rpc_color, a2ui_color, rpc_map, a2ui_map):
        self.rpc_color = rpc_color
        self.a2ui_color = a2ui_color
        self.rpc_map = rpc_map
        self.a2ui_map = a2ui_map

    def get_html_tree(self, data, protocol="jsonrpc", indent=0):
        """Recursively builds the HTML string for the JSON tree."""
        html_out = ""
        
        # Check for Gateway transition to A2UI
        current_protocol = protocol
        if protocol == "jsonrpc":
            if isinstance(data, dict) and ("surfaces" in data or "components" in data):
                current_protocol = "a2ui"
            elif isinstance(data, list) and len(data) > 0:
                # Peek for batch items containing A2UI
                if isinstance(data[0], dict) and ("surfaces" in data[0] or "components" in data[0]):
                    current_protocol = "a2ui"

        color = self.rpc_color if current_protocol == "jsonrpc" else self.a2ui_color
        spec_map = self.rpc_map if current_protocol == "jsonrpc" else self.a2ui_map

        if isinstance(data, dict):
            html_out += '<span class="toggle">▼</span><span style="color: grey;">{</span><div class="collapsible">'
            items = list(data.items())
            for i, (k, v) in enumerate(items):
                desc = html.escape(spec_map.get(k, f"Key in {current_protocol} context"))
                comma = "," if i < len(items) - 1 else ""
                
                html_out += f'<div class="line" style="margin-left: 20px;">'
                html_out += f'<span class="key" style="color: {color};" title="{desc}">"{html.escape(k)}"</span>: '
                html_out += self.get_html_tree(v, current_protocol, indent + 1)
                html_out += f'{comma}</div>'
            html_out += '</div><span style="color: grey;">}</span>'
            
        elif isinstance(data, list):
            html_out += '<span class="toggle">▼</span><span style="color: grey;">[</span><div class="collapsible">'
            for i, item in enumerate(data):
                comma = "," if i < len(data) - 1 else ""
                html_out += f'<div class="line" style="margin-left: 20px;">'
                html_out += self.get_html_tree(item, current_protocol, indent + 1)
                html_out += f'{comma}</div>'
            html_out += '</div><span style="color: grey;">]</span>'
            
        else:
            # Terminal values
            val_str = json.dumps(data)
            html_out += f'<span class="val" style="color: #b5cea8;">{html.escape(val_str)}</span>'
            
        return html_out

def main():
    parser = argparse.ArgumentParser(description="pvprotocolorizer: Protocol-aware JSON visualizer.")
    parser.add_argument("input_file", help="Path to JSON file.")
    parser.add_argument("--rpc-color", default="#569cd6", help="Hex color for JSON-RPC.")
    parser.add_argument("--a2ui-color", default="#ce9178", help="Hex color for A2UI.")
    args = parser.parse_args()

    # Sniffing logic
    if not os.path.exists(args.input_file) or os.path.getsize(args.input_file) == 0:
        return # Ignore empty

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
    except Exception:
        return # Ignore text/invalid JSON

    # Load maps
    rpc_map = load_spec_map(JSONRPC_MAP_FILE)
    a2ui_map = load_spec_map(A2UI_MAP_FILE)

    # Generate content
    engine = Protocolorizer(args.rpc_color, args.a2ui_color, rpc_map, a2ui_map)
    tree_content = engine.get_html_tree(raw_data)

    # HTML Boilerplate
    html_page = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>pvprotocolorizer - {os.path.basename(args.input_file)}</title>
    <style>
        body {{ background-color: #1e1e1e; color: #d4d4d4; font-family: 'Consolas', monospace; font-size: 14px; padding: 20px; }}
        .line {{ margin-top: 2px; }}
        .key {{ cursor: help; font-weight: bold; }}
        .toggle {{ cursor: pointer; color: #858585; margin-right: 5px; user-select: none; display: inline-block; width: 10px; }}
        .collapsible {{ display: block; border-left: 1px solid #333; margin-left: 5px; }}
        .collapsed {{ display: none; }}
    </style>
</head>
<body>
    <div id="tree">{tree_content}</div>
    <script>
        document.addEventListener('click', function(e) {{
            if (e.target.classList.contains('toggle')) {{
                const content = e.target.nextElementSibling.nextElementSibling;
                if (content.classList.contains('collapsed')) {{
                    content.classList.remove('collapsed');
                    e.target.innerText = '▼';
                }} else {{
                    content.classList.add('collapsed');
                    e.target.innerText = '▶';
                }}
            }}
        }});
    </script>
</body>
</html>"""

    sys.stdout.write(html_page)

if __name__ == "__main__":
    main()
