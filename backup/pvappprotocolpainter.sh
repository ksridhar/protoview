import sys
import json
import argparse
import html

# HTML/JS/CSS Template
TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Protocol Annotation Inspector</title>
    <style>
        :root {{
            --bg: #121212; --panel: #1e1e1e; --text: #e0e0e0;
            --rpc-color: #569cd6; --a2ui-color: #ce9178; --str-color: #b5cea8;
        }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: var(--bg); color: var(--text); display: flex; height: 100vh; margin: 0; overflow: hidden; }}
        #tree-pane {{ flex: 1.5; padding: 20px; overflow-y: auto; border-right: 1px solid #333; line-height: 1.6; }}
        #doc-pane {{ flex: 1; background: var(--panel); padding: 0; display: flex; flex-direction: column; }}
        iframe {{ border: none; flex: 1; width: 100%; height: 100%; background: var(--panel); }}
        
        .node {{ margin-left: 20px; border-left: 1px solid #333; padding-left: 10px; }}
        .key {{ cursor: pointer; font-weight: bold; padding: 2px 5px; border-radius: 3px; transition: background 0.2s; }}
        .key:hover {{ background: #333; }}
        .rpc {{ color: var(--rpc-color); border-bottom: 1px solid rgba(86, 156, 214, 0.3); }}
        .a2ui {{ color: var(--a2ui-color); border-bottom: 1px solid rgba(206, 145, 120, 0.3); }}
        .val {{ color: var(--str-color); font-family: 'Consolas', monospace; }}
        h2 {{ padding-left: 20px; color: #888; font-size: 1.2em; }}
    </style>
</head>
<body>
    <div id="tree-pane">
        <h2>Protocol Tree</h2>
        {tree_content}
    </div>
    <div id="doc-pane">
        <iframe name="doc-frame" id="doc-frame"></iframe>
    </div>

    <script>
        function updateDoc(protocol, key, path, desc) {{
            const color = protocol === 'jsonrpc' ? '#569cd6' : '#ce9178';
            const docHTML = `
                <body style="font-family:sans-serif; background:#1e1e1e; color:#e0e0e0; padding:30px;">
                    <div style="border-left: 5px solid ${{color}}; padding-left: 15px;">
                        <small style="color:${{color}}; text-transform:uppercase; font-weight:bold;">${{protocol}} Context</small>
                        <h1 style="margin: 10px 0;">${{key}}</h1>
                        <code style="color:#888;">${{path}}</code>
                        <hr style="border:0; border-top:1px solid #333; margin: 20px 0;">
                        <p style="font-size:1.1em; line-height:1.6;">${{desc}}</p>
                    </div>
                </body>
            `;
            const blob = new Blob([docHTML], {{ type: 'text/html' }});
            document.getElementById('doc-frame').src = URL.createObjectURL(blob);
        }}
    </script>
</body>
</html>
"""

def render_node(node):
    """Recursive function to turn an annotated node into HTML."""
    key = html.escape(str(node.get("key", "")))
    path = html.escape(node.get("path", ""))
    protocol = node.get("protocol", "unknown")
    desc = html.escape(node.get("description", ""))
    value = node.get("value")
    
    js_desc = desc.replace("'", "\\'")
    p_class = "rpc" if protocol == "jsonrpc" else "a2ui"
    
    html_out = f'<div class="node">'
    html_out += f'<span class="key {p_class}" onclick="updateDoc(\'{protocol}\', \'{key}\', \'{path}\', \'{js_desc}\')">"{key}"</span>: '

    if isinstance(value, list): 
        # Detect if it's an object or array based on path naming
        opener = "[" if key.startswith("[") or (isinstance(value, list) and len(value) > 0 and value[0].get("key", "").startswith("[")) else "{"
        closer = "]" if opener == "[" else "}"
        
        html_out += f'<span>{opener}</span>'
        for child in value:
            html_out += render_node(child)
        html_out += f'<div>{closer}</div>'
    else:
        display_val = f'"{html.escape(str(value))}"' if isinstance(value, str) else value
        html_out += f'<span class="val">{display_val}</span>'
    
    html_out += "</div>"
    return html_out

def main():
    parser = argparse.ArgumentParser(
        description="pvappprotocolpainter: Generates an interactive HTML visualization from annotated protocol JSON."
    )
    parser.add_argument("input_file", help="The annotated JSON file to visualize.")
    
    args = parser.parse_args()

    # Load the annotated JSON
    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Could not read or parse {args.input_file}: {e}", file=sys.stderr)
        sys.exit(1)

    # Process into HTML
    try:
        tree_html = render_node(data)
        final_output = TEMPLATE.format(tree_content=tree_html)
        
        # Output directly to stdout
        sys.stdout.write(final_output)
        
        # Log status to stderr
        print(f"SUCCESS: Visualization generated from {args.input_file}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: Failed to generate visualization: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
